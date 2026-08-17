"""Fill the time log's Total_hours column from the recorded clock times.

The dashboard authenticates read-only against the sheet, so it can flag a row
whose Total_hours was never written but it cannot fix one. This repo's
`SheetsClient` holds read/write credentials, so the write-back lives here.

What it writes is *payable* hours, not raw clock time. Looking at the live
sheet, the recorded figure is consistently the clock span minus a break and
then rounded down -- a 5 h 51 m shift is written as "5". Writing the raw span
instead would overpay every row it touched, so the break and rounding are
explicit flags with the observed policy as the default.

Nothing is written unless `--apply` is passed. The default is a dry run that
prints exactly what it would do, because this edits a payroll record.
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import re
import sys
from typing import Iterable, Sequence

log = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BAD_INPUT = 2

# Columns: Date | Employee | Time_in | Time_out | Total_hours
COL_DATE, COL_EMPLOYEE, COL_TIME_IN, COL_TIME_OUT, COL_TOTAL = range(5)
TOTAL_COLUMN_LETTER = "E"
SHEET_RANGE = "A:E"

DEFAULT_BREAK_HOURS = 1.0
DEFAULT_ROUNDING = "floor"
ROUNDING_CHOICES = ("floor", "nearest", "none")

# No shift here runs longer than this. A computed span beyond it means the
# clock times are unusable, not that somebody worked sixteen hours.
MAX_SHIFT_HOURS = 16

# A cap so a misconfigured run can't rewrite the whole sheet in one go.
DEFAULT_MAX_WRITES = 200

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?$")


def parse_time_of_day(value: str) -> int | None:
    """Minutes since midnight, or None if the cell can't be read.

    Mirrors the dashboard's parser exactly, including the trap that a bare
    '10:00' is 24-hour time (10 AM) rather than an evening clock-out.
    """
    match = _TIME_RE.match(str(value).strip())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if minute > 59:
        return None
    meridiem = (match.group(3) or "").upper()
    if meridiem == "AM":
        if hour == 12:
            hour = 0
        elif not 1 <= hour <= 12:
            return None
    elif meridiem == "PM":
        if hour != 12:
            hour += 12
        if not 12 <= hour <= 23:
            return None
    elif not 0 <= hour <= 23:
        return None
    return hour * 60 + minute


def payable_hours(
    time_in: str,
    time_out: str,
    *,
    break_hours: float = DEFAULT_BREAK_HOURS,
    rounding: str = DEFAULT_ROUNDING,
) -> float | None:
    """What Total_hours should say for a shift, or None if it can't be derived."""
    start = parse_time_of_day(time_in)
    end = parse_time_of_day(time_out)
    if start is None or end is None:
        return None

    minutes = end - start
    # Both cells carry the same date, so a shift past midnight reads negative.
    if minutes <= 0:
        minutes += 24 * 60
    hours = minutes / 60.0
    if hours <= 0 or hours > MAX_SHIFT_HOURS:
        return None

    net = hours - break_hours
    if net <= 0:
        return 0.0
    if rounding == "floor":
        return float(math.floor(net))
    if rounding == "nearest":
        # floor(x + 0.5), not Python's round(), which rounds halves to even
        # and would disagree with the dashboard on exact .5 values.
        return float(math.floor(net + 0.5))
    return round(net, 2)


def _cell(row: Sequence[str], index: int) -> str:
    """Read a cell, tolerating rows the API truncated at the last value."""
    return str(row[index]).strip() if index < len(row) else ""


class Update:
    """One proposed edit to a Total_hours cell."""

    __slots__ = ("sheet_row", "date", "employee", "current", "proposed")

    def __init__(
        self,
        sheet_row: int,
        date: str,
        employee: str,
        current: str,
        proposed: float,
    ) -> None:
        self.sheet_row = sheet_row
        self.date = date
        self.employee = employee
        self.current = current
        self.proposed = proposed

    @property
    def a1(self) -> str:
        return f"{TOTAL_COLUMN_LETTER}{self.sheet_row}"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Update {self.a1} {self.current!r}->{self.proposed}>"


def build_plan(
    rows: Iterable[Sequence[str]],
    *,
    break_hours: float = DEFAULT_BREAK_HOURS,
    rounding: str = DEFAULT_ROUNDING,
    overwrite: bool = False,
) -> tuple[list[Update], list[str]]:
    """Work out which Total_hours cells to fill.

    `rows` includes the header row, so the first data row is sheet row 2.

    By default only blank cells are filled -- a figure someone typed is a
    human decision and outranks anything computed here. `overwrite` also
    proposes corrections where the existing value disagrees, which is a much
    bigger claim and stays opt-in.

    Returns (updates, skip messages).
    """
    updates: list[Update] = []
    skipped: list[str] = []

    for offset, row in enumerate(rows):
        if offset == 0:
            continue  # header
        sheet_row = offset + 1  # sheet rows are 1-based

        date = _cell(row, COL_DATE)
        employee = _cell(row, COL_EMPLOYEE)
        if not date or not employee:
            continue  # blank spacer row

        time_in = _cell(row, COL_TIME_IN)
        time_out = _cell(row, COL_TIME_OUT)
        current = _cell(row, COL_TOTAL)

        if not time_out:
            continue  # still clocked in; nothing to total yet

        computed = payable_hours(
            time_in, time_out, break_hours=break_hours, rounding=rounding
        )
        if computed is None:
            if not current:
                skipped.append(
                    f"row {sheet_row}: {date} {employee} — "
                    f"can't read clock times ({time_in!r} → {time_out!r})"
                )
            continue

        if current:
            if not overwrite:
                continue
            try:
                if abs(float(current) - computed) < 0.005:
                    continue  # already agrees
            except ValueError:
                skipped.append(
                    f"row {sheet_row}: {date} {employee} — "
                    f"existing Total_hours {current!r} isn't a number, left alone"
                )
                continue

        updates.append(Update(sheet_row, date, employee, current, computed))

    return updates, skipped


def format_plan(updates: Sequence[Update], skipped: Sequence[str]) -> str:
    lines: list[str] = []
    if updates:
        lines.append(f"{'CELL':>6}  {'DATE':<12} {'EMPLOYEE':<12} {'NOW':>8}  {'WRITE':>6}")
        for u in updates:
            now = u.current if u.current else "(blank)"
            lines.append(
                f"{u.a1:>6}  {u.date:<12} {u.employee:<12} {now:>8}  {u.proposed:>6g}"
            )
    if skipped:
        lines.append("")
        lines.append("Skipped:")
        lines.extend(f"  {s}" for s in skipped)
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hours_writer",
        description=(
            "Fill the time log's Total_hours column from the recorded clock "
            "times. Dry run by default — pass --apply to write."
        ),
    )
    parser.add_argument(
        "--time-log-sheet-id",
        default=os.environ.get("TIME_LOG_SHEET_ID"),
        help="Google Sheet ID for the time log. Defaults to $TIME_LOG_SHEET_ID.",
    )
    parser.add_argument(
        "--time-log-sheet-gid",
        type=int,
        default=int(os.environ["TIME_LOG_SHEET_GID"])
        if os.environ.get("TIME_LOG_SHEET_GID")
        else None,
        help=(
            "Worksheet gid (from the URL after `#gid=`). "
            "Defaults to $TIME_LOG_SHEET_GID, or the first worksheet."
        ),
    )
    parser.add_argument(
        "--break-hours",
        type=float,
        default=DEFAULT_BREAK_HOURS,
        help=(
            "Hours deducted from the clock span before rounding "
            f"(default: {DEFAULT_BREAK_HOURS}). Pass 0 to write the raw span."
        ),
    )
    parser.add_argument(
        "--rounding",
        choices=ROUNDING_CHOICES,
        default=DEFAULT_ROUNDING,
        help=f"How to round the deducted figure (default: {DEFAULT_ROUNDING}).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Also correct cells that already hold a value and disagree. "
            "Off by default: a typed figure is a human decision."
        ),
    )
    parser.add_argument(
        "--max-writes",
        type=int,
        default=DEFAULT_MAX_WRITES,
        help=f"Refuse to write more than this many cells (default: {DEFAULT_MAX_WRITES}).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to the sheet. Without it, nothing is changed.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    from dotenv import load_dotenv

    load_dotenv()

    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if not args.time_log_sheet_id:
        print(
            "error: no sheet id — pass --time-log-sheet-id or set TIME_LOG_SHEET_ID",
            file=sys.stderr,
        )
        return EXIT_BAD_INPUT
    if args.break_hours < 0:
        print("error: --break-hours cannot be negative", file=sys.stderr)
        return EXIT_BAD_INPUT

    try:
        from src.sheets_client import SheetsAuthError, SheetsClient, SheetsClientError
    except ImportError as exc:
        print(f"error: Google Sheets deps not installed: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        client = SheetsClient()
        worksheet: int | str = 0
        if args.time_log_sheet_gid is not None:
            worksheet = client.get_worksheet_title(
                args.time_log_sheet_id, args.time_log_sheet_gid
            )
            log.debug("resolved gid=%s to %r", args.time_log_sheet_gid, worksheet)
        rows = client.read_range(args.time_log_sheet_id, SHEET_RANGE, worksheet)
    except SheetsAuthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT
    except SheetsClientError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if len(rows) <= 1:
        print("Sheet has no data rows — nothing to do.")
        return EXIT_OK

    updates, skipped = build_plan(
        rows,
        break_hours=args.break_hours,
        rounding=args.rounding,
        overwrite=args.overwrite,
    )

    policy = (
        f"clock span − {args.break_hours:g} h break, rounded {args.rounding}"
        if args.break_hours
        else f"raw clock span, rounded {args.rounding}"
    )
    print(f"Rule: {policy}")
    print(f"Mode: {'blank cells and disagreements' if args.overwrite else 'blank cells only'}")
    print()

    if not updates:
        print("Nothing to write — every row already has a total.")
        if skipped:
            print()
            print(format_plan(updates, skipped))
        return EXIT_OK

    print(format_plan(updates, skipped))
    print()

    if len(updates) > args.max_writes:
        print(
            f"error: {len(updates)} cells to write exceeds --max-writes "
            f"({args.max_writes}). Raise it deliberately if that's expected.",
            file=sys.stderr,
        )
        return EXIT_BAD_INPUT

    if not args.apply:
        print(f"Dry run — nothing written. Re-run with --apply to write {len(updates)} cell(s).")
        return EXIT_OK

    try:
        written = client.update_cells(
            args.time_log_sheet_id,
            [(u.a1, u.proposed) for u in updates],
            worksheet,
        )
    except SheetsAuthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT
    except SheetsClientError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(f"Wrote {written} cell(s) to Total_hours.")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
