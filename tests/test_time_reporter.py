"""Unit tests for the pure functions in src.time_reporter."""
from __future__ import annotations

import pytest

from src.time_reporter import (
    _hours_between,
    _normalize_date,
    _normalize_time,
    daily_totals,
    load_time_log_sheet,
    summarize,
)


# ---------------------------------------------------------------- _hours_between

class TestHoursBetween:
    def test_basic_full_hours(self):
        assert _hours_between("09:00", "17:00") == 8.0

    def test_includes_minutes(self):
        assert _hours_between("08:55", "17:05") == pytest.approx(8.17, abs=0.01)

    def test_zero_when_same(self):
        assert _hours_between("10:30", "10:30") == 0.0

    def test_short_shift(self):
        assert _hours_between("12:00", "12:30") == 0.5


# ---------------------------------------------------------------- _normalize_date

class TestNormalizeDate:
    def test_iso_passes_through(self):
        assert _normalize_date("2026-05-11") == "2026-05-11"

    def test_us_format_converted(self):
        assert _normalize_date("05/11/2026") == "2026-05-11"

    def test_strips_whitespace(self):
        assert _normalize_date("  2026-05-11  ") == "2026-05-11"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="unrecognized date format"):
            _normalize_date("not a date")

    def test_ambiguous_dot_format_raises(self):
        # We deliberately don't accept 2026.05.11 — keep the surface small.
        with pytest.raises(ValueError):
            _normalize_date("2026.05.11")


# ---------------------------------------------------------------- _normalize_time

class TestNormalizeTime:
    def test_24h_passes_through(self):
        assert _normalize_time("17:05") == "17:05"

    def test_12h_am(self):
        assert _normalize_time("08:55 AM") == "08:55"

    def test_12h_pm(self):
        assert _normalize_time("05:05 PM") == "17:05"

    def test_12h_no_space(self):
        assert _normalize_time("10:40AM") == "10:40"

    def test_12h_with_periods(self):
        # Tolerate A.M. / P.M. notation
        assert _normalize_time("10:40 A.M.") == "10:40"
        assert _normalize_time("3:15 P.M.") == "15:15"

    def test_case_insensitive(self):
        assert _normalize_time("10:40 am") == "10:40"
        assert _normalize_time("10:40 pm") == "22:40"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="unrecognized time format"):
            _normalize_time("noon")


# ---------------------------------------------------------------- summarize

class TestSummarize:
    def _row(self, **kwargs):
        return {
            "employee_id": "001",
            "date": "2026-05-11",
            "clock_in": "09:00",
            "clock_out": "17:00",
            **kwargs,
        }

    def test_groups_by_employee_id(self):
        time_log = [
            self._row(employee_id="001", date="2026-05-11"),
            self._row(employee_id="001", date="2026-05-12"),
            self._row(employee_id="002", date="2026-05-11"),
        ]
        result = summarize(time_log, employees=[])
        assert len(result) == 2
        by_id = {s["employee_id"]: s for s in result}
        assert by_id["001"]["days_worked"] == 2
        assert by_id["002"]["days_worked"] == 1

    def test_sorts_by_total_hours_desc(self):
        time_log = [
            self._row(employee_id="001", clock_in="09:00", clock_out="11:00"),  # 2h
            self._row(employee_id="002", clock_in="09:00", clock_out="17:00"),  # 8h
            self._row(employee_id="003", clock_in="09:00", clock_out="14:00"),  # 5h
        ]
        result = summarize(time_log, employees=[])
        assert [s["employee_id"] for s in result] == ["002", "003", "001"]

    def test_resolves_employee_name_from_master(self):
        employees = [
            {"employee_id": "001", "first_name": "Ada", "last_name": "Lovelace"}
        ]
        result = summarize([self._row(employee_id="001")], employees)
        assert result[0]["name"] == "Ada Lovelace"

    def test_unmatched_employee_falls_back_to_id(self):
        # When emp_id has no master entry, name should equal the id itself
        # (so Sheets-source rows keyed by name display the name, not "Unknown").
        result = summarize([self._row(employee_id="Ivan")], employees=[])
        assert result[0]["name"] == "Ivan"

    def test_computes_avg_per_day(self):
        time_log = [
            self._row(date="2026-05-11", clock_in="09:00", clock_out="17:00"),  # 8
            self._row(date="2026-05-12", clock_in="09:00", clock_out="13:00"),  # 4
        ]
        result = summarize(time_log, employees=[])
        s = result[0]
        assert s["total_hours"] == 12.0
        assert s["days_worked"] == 2
        assert s["avg_hours"] == 6.0

    def test_empty_input(self):
        assert summarize([], employees=[]) == []

    def test_entries_sorted_chronologically(self):
        time_log = [
            self._row(date="2026-05-15"),
            self._row(date="2026-05-11"),
            self._row(date="2026-05-13"),
        ]
        result = summarize(time_log, employees=[])
        dates = [e["date"] for e in result[0]["entries"]]
        assert dates == ["2026-05-11", "2026-05-13", "2026-05-15"]


# ---------------------------------------------------------------- daily_totals

class TestDailyTotals:
    def test_empty_input(self):
        assert daily_totals([]) == []

    def test_single_day(self):
        time_log = [
            {"employee_id": "001", "date": "2026-05-11", "clock_in": "09:00", "clock_out": "17:00"},
        ]
        result = daily_totals(time_log)
        assert result == [{"date": "2026-05-11", "hours": 8.0}]

    def test_aggregates_across_employees_same_day(self):
        time_log = [
            {"employee_id": "001", "date": "2026-05-11", "clock_in": "09:00", "clock_out": "17:00"},
            {"employee_id": "002", "date": "2026-05-11", "clock_in": "10:00", "clock_out": "14:00"},
        ]
        result = daily_totals(time_log)
        assert result == [{"date": "2026-05-11", "hours": 12.0}]

    def test_fills_date_gaps_with_zero(self):
        # Mon and Wed only — Tue should be filled with 0.
        time_log = [
            {"employee_id": "001", "date": "2026-05-11", "clock_in": "09:00", "clock_out": "17:00"},
            {"employee_id": "001", "date": "2026-05-13", "clock_in": "09:00", "clock_out": "17:00"},
        ]
        result = daily_totals(time_log)
        assert result == [
            {"date": "2026-05-11", "hours": 8.0},
            {"date": "2026-05-12", "hours": 0.0},
            {"date": "2026-05-13", "hours": 8.0},
        ]

    def test_sorted_chronologically(self):
        time_log = [
            {"employee_id": "001", "date": "2026-05-13", "clock_in": "09:00", "clock_out": "17:00"},
            {"employee_id": "001", "date": "2026-05-11", "clock_in": "09:00", "clock_out": "17:00"},
        ]
        result = daily_totals(time_log)
        assert [d["date"] for d in result] == ["2026-05-11", "2026-05-12", "2026-05-13"]


# ---------------------------------------------------------------- load_time_log_sheet adapter

class _StubClient:
    """Stand-in for SheetsClient — returns canned rows / titles, no network."""

    def __init__(self, rows, worksheet_title="Sheet1"):
        self.rows = rows
        self._title = worksheet_title

    def get_worksheet_title(self, spreadsheet_id, gid):
        return self._title

    def read_sheet(self, spreadsheet_id, worksheet=None):
        return self.rows


class TestLoadTimeLogSheet:
    def test_normalizes_practice1_shape(self):
        client = _StubClient(rows=[
            {"Date": "05/11/2026", "Employee": "Ivan", "Time_in": "08:30 AM",
             "Time_out": "05:00 PM", "Total_hours": ""},
        ])
        employees = [{"employee_id": "001", "first_name": "Ivan", "last_name": "Quinola"}]
        rows, skipped = load_time_log_sheet(client, "sid", 0, employees)
        assert skipped == 0
        assert len(rows) == 1
        assert rows[0] == {
            "employee_id": "001",
            "date": "2026-05-11",
            "clock_in": "08:30",
            "clock_out": "17:00",
        }

    def test_skips_rows_missing_time_out(self):
        client = _StubClient(rows=[
            {"Date": "05/11/2026", "Employee": "Ivan", "Time_in": "08:30 AM", "Time_out": ""},
            {"Date": "05/11/2026", "Employee": "Daniel", "Time_in": "", "Time_out": "05:00 PM"},
            {"Date": "05/11/2026", "Employee": "Ivan", "Time_in": "08:30 AM", "Time_out": "05:00 PM"},
        ])
        rows, skipped = load_time_log_sheet(client, "sid", 0, employees=[])
        assert skipped == 2
        assert len(rows) == 1

    def test_unmatched_employee_name_passes_through(self):
        # No match in employees -> use the raw name as employee_id.
        client = _StubClient(rows=[
            {"Date": "05/11/2026", "Employee": "Mystery", "Time_in": "09:00 AM",
             "Time_out": "05:00 PM"},
        ])
        rows, _ = load_time_log_sheet(client, "sid", 0, employees=[])
        assert rows[0]["employee_id"] == "Mystery"

    def test_employee_name_match_is_case_insensitive(self):
        client = _StubClient(rows=[
            {"Date": "05/11/2026", "Employee": "IVAN", "Time_in": "09:00 AM",
             "Time_out": "05:00 PM"},
        ])
        employees = [{"employee_id": "001", "first_name": "Ivan", "last_name": "Q"}]
        rows, _ = load_time_log_sheet(client, "sid", 0, employees)
        assert rows[0]["employee_id"] == "001"

    def test_empty_sheet_returns_empty(self):
        client = _StubClient(rows=[])
        rows, skipped = load_time_log_sheet(client, "sid", 0, employees=[])
        assert rows == []
        assert skipped == 0
