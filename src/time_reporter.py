"""Generate the weekly time-tracking HTML report.

Reads a time-log CSV (columns: employee_id, date, clock_in, clock_out) and an
employees CSV (columns: employee_id, first_name, last_name, email), then
renders a per-employee summary to `output/weekly_report.html`.
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, time
from pathlib import Path
from typing import Iterable, Sequence

from jinja2 import Template

DEFAULT_TIME_LOG_CSV = "data/time_log.csv"
DEFAULT_EMPLOYEES_CSV = "data/employees.csv"
DEFAULT_HTML = "output/weekly_report.html"

log = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BAD_INPUT = 2


def load_csv(path: str | os.PathLike[str]) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _parse_time(value: str) -> time:
    return datetime.strptime(value.strip(), "%H:%M").time()


def _hours_between(clock_in: str, clock_out: str) -> float:
    in_t = _parse_time(clock_in)
    out_t = _parse_time(clock_out)
    delta_min = (out_t.hour * 60 + out_t.minute) - (in_t.hour * 60 + in_t.minute)
    return round(delta_min / 60.0, 2)


def summarize(
    time_log: Iterable[dict[str, str]],
    employees: Iterable[dict[str, str]],
) -> list[dict]:
    """Aggregate entries by employee and return rows for the report."""
    by_id: dict[str, dict[str, str]] = {e["employee_id"]: e for e in employees}

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in time_log:
        hours = _hours_between(row["clock_in"], row["clock_out"])
        grouped[row["employee_id"]].append(
            {
                "date": row["date"],
                "clock_in": row["clock_in"],
                "clock_out": row["clock_out"],
                "hours": hours,
            }
        )

    summaries = []
    for emp_id, entries in grouped.items():
        emp = by_id.get(emp_id, {})
        total = round(sum(e["hours"] for e in entries), 2)
        entries.sort(key=lambda e: e["date"])
        summaries.append(
            {
                "employee_id": emp_id,
                "name": f"{emp.get('first_name', '')} {emp.get('last_name', '')}".strip()
                or f"Unknown (#{emp_id})",
                "email": emp.get("email", ""),
                "days_worked": len(entries),
                "total_hours": total,
                "avg_hours": round(total / len(entries), 2) if entries else 0.0,
                "entries": entries,
            }
        )

    summaries.sort(key=lambda s: s["employee_id"])
    return summaries


REPORT_TEMPLATE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Weekly Time Report</title>
<style>
  body { font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; margin: 2rem; color: #222; }
  h1 { margin-bottom: 0.2rem; }
  .meta { color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }
  .employee { border: 1px solid #ddd; border-radius: 6px; padding: 1rem 1.25rem; margin-bottom: 1.25rem; }
  .header { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; flex-wrap: wrap; }
  .header h2 { margin: 0; font-size: 1.1rem; }
  .header .id { color: #888; font-weight: normal; font-size: 0.9rem; }
  .stats { font-size: 0.9rem; color: #444; }
  .stats strong { color: #111; }
  table { border-collapse: collapse; margin-top: 0.75rem; width: 100%; max-width: 600px; }
  th, td { text-align: left; padding: 0.35rem 0.6rem; border-bottom: 1px solid #eee; font-size: 0.9rem; }
  th { background: #f7f7f7; font-weight: 600; }
  td.hours { text-align: right; font-variant-numeric: tabular-nums; }
</style>
</head>
<body>
<h1>Weekly Time Report</h1>
<p class="meta">
  Generated {{ generated_at }} &middot;
  {{ summaries|length }} employee(s) &middot;
  {{ "%.2f"|format(grand_total) }} total hours
</p>

{% for s in summaries %}
<section class="employee">
  <div class="header">
    <h2>{{ s.name }} <span class="id">#{{ s.employee_id }}</span></h2>
    <div class="stats">
      <strong>{{ "%.2f"|format(s.total_hours) }} h</strong> across
      {{ s.days_worked }} day(s) &middot;
      avg {{ "%.2f"|format(s.avg_hours) }} h/day
    </div>
  </div>
  <table>
    <thead><tr><th>Date</th><th>In</th><th>Out</th><th class="hours">Hours</th></tr></thead>
    <tbody>
    {% for e in s.entries %}
      <tr>
        <td>{{ e.date }}</td>
        <td>{{ e.clock_in }}</td>
        <td>{{ e.clock_out }}</td>
        <td class="hours">{{ "%.2f"|format(e.hours) }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</section>
{% endfor %}
</body>
</html>
""")


def render_report(summaries: list[dict], output_path: str | os.PathLike[str]) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    html = REPORT_TEMPLATE.render(
        summaries=summaries,
        grand_total=sum(s["total_hours"] for s in summaries),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    out.write_text(html, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="time_reporter",
        description="Generate a weekly HTML time-tracking report from CSV inputs.",
    )
    parser.add_argument(
        "--time-log",
        default=os.environ.get("TIME_LOG_CSV", DEFAULT_TIME_LOG_CSV),
        help=f"Path to time log CSV (default: {DEFAULT_TIME_LOG_CSV} or $TIME_LOG_CSV).",
    )
    parser.add_argument(
        "--employees",
        default=os.environ.get("EMPLOYEES_CSV", DEFAULT_EMPLOYEES_CSV),
        help=f"Path to employees CSV (default: {DEFAULT_EMPLOYEES_CSV} or $EMPLOYEES_CSV).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=os.environ.get("REPORT_HTML_OUTPUT", DEFAULT_HTML),
        help=f"HTML output path (default: {DEFAULT_HTML} or $REPORT_HTML_OUTPUT).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    log.debug("loading time log from %s", args.time_log)
    log.debug("loading employees from %s", args.employees)
    try:
        time_log = load_csv(args.time_log)
        employees = load_csv(args.employees)
    except FileNotFoundError as exc:
        print(f"error: input CSV not found: {exc.filename}", file=sys.stderr)
        return EXIT_BAD_INPUT

    if not time_log:
        print(f"error: no entries found in {args.time_log}", file=sys.stderr)
        return EXIT_BAD_INPUT

    try:
        summaries = summarize(time_log, employees)
        render_report(summaries, args.output)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    total_entries = sum(s["days_worked"] for s in summaries)
    print(
        f"Wrote report for {len(summaries)} employee(s), "
        f"{total_entries} entries -> {args.output}"
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
