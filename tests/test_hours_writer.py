"""Tests for the Total_hours write-back.

This module edits a payroll record, so the tests lean hardest on what it must
NOT do: never touch an open shift, never overwrite a figure a human typed
unless explicitly asked, never invent a number from clock times it can't read.
"""
from __future__ import annotations

import pytest

from src import hours_writer
from src.hours_writer import build_plan, parse_time_of_day, payable_hours

HEADER = ["Date", "Employee", "Time_in", "Time_out", "Total_hours"]


class TestParseTimeOfDay:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("7:00 AM", 7 * 60),
            ("11:00:00 AM", 11 * 60),
            ("6:15 PM", 18 * 60 + 15),
            ("20:00", 20 * 60),
            ("12:00 AM", 0),
            ("12:00 PM", 12 * 60),
            ("12:04:00 AM", 4),
            ("  6:30 pm  ", 18 * 60 + 30),
        ],
    )
    def test_parses(self, value, expected):
        assert parse_time_of_day(value) == expected

    @pytest.mark.parametrize("value", ["", "   ", "not a time", "25:00", "10:99"])
    def test_rejects(self, value):
        assert parse_time_of_day(value) is None

    def test_bare_time_is_24_hour(self):
        # The trap behind the original bug: an evening clock-out typed without
        # its marker reads as morning.
        assert parse_time_of_day("10:00") == 10 * 60


class TestPayableHours:
    """Every clocked hour, rounded to the hour, up from 40 minutes past.

    This must match `computeTotalHours` in the n8n Decide node and
    `expectedShiftHours` in the dashboard. Three copies of one rule; if these
    tests and those disagree, the sheet and the screen disagree about pay.
    """

    def test_pays_the_hours_on_the_clock(self):
        assert payable_hours("6:00 PM", "11:00 PM") == 5.0
        assert payable_hours("3:00 PM", "11:00 PM") == 8.0

    def test_rounds_down_under_40_minutes_past(self):
        assert payable_hours("6:00 PM", "9:39 PM") == 3.0

    def test_rounds_up_from_40_minutes_past(self):
        assert payable_hours("6:00 PM", "9:40 PM") == 4.0

    def test_pays_early_arrival(self):
        # Hours are flexible against a five-hour target: in early, out early.
        assert payable_hours("3:18 PM", "8:18 PM") == 5.0
        assert payable_hours("4:30 PM", "11:03 PM") == 6.0

    def test_counts_through_midnight(self):
        assert payable_hours("8:00 PM", "3:00 AM") == 7.0
        # Minutes apart, and no cliff between them.
        assert payable_hours("6:00 PM", "11:59 PM") == 6.0
        assert payable_hours("6:00 PM", "12:03 AM") == 6.0

    def test_refuses_an_implausible_span(self):
        # 6 AM -> 5 AM becomes 23 h after the midnight adjustment: bad data.
        assert payable_hours("6:00 AM", "5:00 AM") is None

    def test_none_when_times_unreadable(self):
        assert payable_hours("", "11:00 PM") is None
        assert payable_hours("6:00 PM", "garbage") is None


class TestBuildPlan:
    def test_fills_a_blank_total(self):
        rows = [HEADER, ["2026-08-14", "Ivan", "12:39 PM", "8:02 PM", ""]]
        updates, _ = build_plan(rows)
        assert len(updates) == 1
        assert updates[0].a1 == "E2"  # header is row 1
        assert updates[0].proposed == 7.0  # 7h23m on the clock

    def test_row_numbers_track_the_sheet(self):
        rows = [
            HEADER,
            ["2026-08-12", "Ivan", "6:00 PM", "11:00 PM", "5"],
            ["2026-08-13", "Ivan", "6:00 PM", "11:00 PM", ""],
        ]
        updates, _ = build_plan(rows)
        assert [u.a1 for u in updates] == ["E3"]

    def test_leaves_an_open_shift_alone(self):
        # Still clocked in — there is no total to write yet.
        rows = [HEADER, ["2026-08-14", "Ivan", "6:00 PM", "", ""]]
        updates, _ = build_plan(rows)
        assert updates == []

    def test_leaves_an_existing_figure_alone_by_default(self):
        # A typed figure is a human decision and outranks anything computed.
        rows = [HEADER, ["2026-08-14", "Ivan", "12:39 PM", "8:02 PM", "5"]]
        updates, _ = build_plan(rows)
        assert updates == []

    def test_overwrite_corrects_a_disagreement(self):
        rows = [HEADER, ["2026-08-14", "Ivan", "12:39 PM", "8:02 PM", "5"]]
        updates, _ = build_plan(rows, overwrite=True)
        assert len(updates) == 1
        assert updates[0].current == "5"
        assert updates[0].proposed == 7.0

    def test_overwrite_leaves_an_agreeing_row_alone(self):
        # 5 h on the clock, and the cell already says 5.
        rows = [HEADER, ["2026-08-12", "Ivan", "6:00 PM", "11:00 PM", "5"]]
        updates, _ = build_plan(rows, overwrite=True)
        assert updates == []

    def test_skips_and_reports_unreadable_clock_times(self):
        rows = [HEADER, ["2026-08-14", "Ivan", "", "8:02 PM", ""]]
        updates, skipped = build_plan(rows)
        assert updates == []
        assert len(skipped) == 1
        assert "can't read clock times" in skipped[0]

    def test_ignores_blank_spacer_rows(self):
        # Header is sheet row 1, the spacer is row 2, so the data row is row 3.
        # A spacer must still consume its row number or every write below it
        # would land one row off.
        rows = [HEADER, ["", "", "", "", ""], ["2026-08-14", "Ivan", "6:00 PM", "11:00 PM", ""]]
        updates, _ = build_plan(rows)
        assert [u.a1 for u in updates] == ["E3"]

    def test_tolerates_rows_truncated_by_the_api(self):
        # gspread drops trailing empty cells, so a blank Total_hours can mean
        # a 4-element row rather than a 5-element one.
        rows = [HEADER, ["2026-08-14", "Ivan", "6:00 PM", "11:00 PM"]]
        updates, _ = build_plan(rows)
        assert len(updates) == 1
        assert updates[0].proposed == 5.0

    def test_leaves_a_non_numeric_total_alone(self):
        rows = [HEADER, ["2026-08-14", "Ivan", "6:00 PM", "11:00 PM", "n/a"]]
        updates, skipped = build_plan(rows, overwrite=True)
        assert updates == []
        assert "isn't a number" in skipped[0]

    def test_fills_with_the_clocked_hours(self):
        rows = [HEADER, ["2026-08-14", "Ivan", "6:00 PM", "11:00 PM", ""]]
        updates, _ = build_plan(rows)
        assert updates[0].proposed == 5.0


class TestCli:
    @pytest.fixture(autouse=True)
    def _isolate_env(self, monkeypatch, tmp_path):
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
        for var in (
            "TIME_LOG_SHEET_ID",
            "TIME_LOG_SHEET_GID",
            "GOOGLE_APPLICATION_CREDENTIALS",
        ):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.chdir(tmp_path)

    def test_missing_sheet_id_is_bad_input(self, capsys):
        rc = hours_writer.main([])
        assert rc == hours_writer.EXIT_BAD_INPUT
        assert "no sheet id" in capsys.readouterr().err

    def test_dry_run_is_the_default(self, monkeypatch, capsys):
        """No --apply means read, report, and touch nothing."""
        written: list = []

        class FakeClient:
            def get_worksheet_title(self, *a, **k):
                return "Sheet1"

            def read_range(self, *a, **k):
                return [HEADER, ["2026-08-14", "Ivan", "6:00 PM", "11:00 PM", ""]]

            def update_cells(self, *a, **k):  # pragma: no cover - must not run
                written.append(a)
                return 0

        monkeypatch.setattr(hours_writer, "__name__", hours_writer.__name__)
        import src.sheets_client as sc

        monkeypatch.setattr(sc, "SheetsClient", lambda *a, **k: FakeClient())

        rc = hours_writer.main(["--time-log-sheet-id", "abc"])
        out = capsys.readouterr().out
        assert rc == hours_writer.EXIT_OK
        assert written == [], "dry run must not write"
        assert "Dry run" in out
        assert "E2" in out

    def test_apply_writes(self, monkeypatch, capsys):
        calls: list = []

        class FakeClient:
            def get_worksheet_title(self, *a, **k):
                return "Sheet1"

            def read_range(self, *a, **k):
                return [HEADER, ["2026-08-14", "Ivan", "6:00 PM", "11:00 PM", ""]]

            def update_cells(self, _id, updates, _ws):
                calls.append(updates)
                return len(updates)

        import src.sheets_client as sc

        monkeypatch.setattr(sc, "SheetsClient", lambda *a, **k: FakeClient())

        rc = hours_writer.main(["--time-log-sheet-id", "abc", "--apply"])
        assert rc == hours_writer.EXIT_OK
        assert calls == [[("E2", 5.0)]]
        assert "Wrote 1 cell" in capsys.readouterr().out

    def test_refuses_to_exceed_max_writes(self, monkeypatch, capsys):
        rows = [HEADER] + [
            [f"2026-08-{d:02d}", "Ivan", "6:00 PM", "11:00 PM", ""] for d in range(1, 6)
        ]

        class FakeClient:
            def get_worksheet_title(self, *a, **k):
                return "Sheet1"

            def read_range(self, *a, **k):
                return rows

            def update_cells(self, *a, **k):  # pragma: no cover - must not run
                raise AssertionError("must not write past the cap")

        import src.sheets_client as sc

        monkeypatch.setattr(sc, "SheetsClient", lambda *a, **k: FakeClient())

        rc = hours_writer.main(
            ["--time-log-sheet-id", "abc", "--apply", "--max-writes", "2"]
        )
        assert rc == hours_writer.EXIT_BAD_INPUT
        assert "exceeds --max-writes" in capsys.readouterr().err
