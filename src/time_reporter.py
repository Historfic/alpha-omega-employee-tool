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
from datetime import datetime, time, timedelta
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

    summaries.sort(key=lambda s: s["total_hours"], reverse=True)
    return summaries


def daily_totals(time_log: Iterable[dict[str, str]]) -> list[dict]:
    """Aggregate total hours across all employees, per calendar day.

    Fills any gaps in the date range with 0 so the line chart doesn't skip days.
    """
    by_date: dict[str, float] = defaultdict(float)
    for row in time_log:
        by_date[row["date"]] += _hours_between(row["clock_in"], row["clock_out"])

    if not by_date:
        return []

    dates = sorted(by_date.keys())
    start = datetime.strptime(dates[0], "%Y-%m-%d").date()
    end = datetime.strptime(dates[-1], "%Y-%m-%d").date()

    result: list[dict] = []
    current = start
    while current <= end:
        key = current.isoformat()
        result.append({"date": key, "hours": round(by_date.get(key, 0.0), 2)})
        current += timedelta(days=1)
    return result


REPORT_TEMPLATE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Weekly Time Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #f5f7fa;
    --card: #ffffff;
    --border: #e3e7ec;
    --text: #1f2933;
    --muted: #5f6b7a;
    --accent: #3b82f6;
    --accent-soft: rgba(59, 130, 246, 0.12);
    --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.04);
    --shadow-md: 0 4px 12px rgba(15, 23, 42, 0.08);
    --row-hover: rgba(59, 130, 246, 0.05);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0b1220;
      --card: #131c2e;
      --border: #243046;
      --text: #e6edf6;
      --muted: #94a3b8;
      --accent: #60a5fa;
      --accent-soft: rgba(96, 165, 250, 0.18);
      --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4);
      --shadow-md: 0 4px 14px rgba(0, 0, 0, 0.5);
      --row-hover: rgba(96, 165, 250, 0.08);
    }
  }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif;
    margin: 0; padding: 2rem; background: var(--bg); color: var(--text);
    -webkit-font-smoothing: antialiased;
  }
  header { margin-bottom: 1.5rem; }
  header h1 { margin: 0 0 0.25rem; font-size: 1.5rem; letter-spacing: -0.01em; }
  header .meta { color: var(--muted); font-size: 0.9rem; }

  .kpis {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
  }
  .kpi {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 1rem 1.25rem;
    box-shadow: var(--shadow-sm);
    transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
  }
  .kpi:hover {
    transform: translateY(-2px); box-shadow: var(--shadow-md);
    border-color: var(--accent-soft);
  }
  .kpi .label { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; }
  .kpi .value { font-size: 1.7rem; font-weight: 600; margin-top: 0.3rem; font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
  .kpi .sub { color: var(--muted); font-size: 0.8rem; margin-top: 0.15rem; }

  .card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1.25rem;
    box-shadow: var(--shadow-sm);
  }
  .card h2 { margin: 0 0 0.75rem; font-size: 0.85rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; }

  .chart-wrap { position: relative; height: 260px; }

  details.employee { border-top: 1px solid var(--border); padding: 0.85rem 0; }
  details.employee:first-of-type { border-top: none; padding-top: 0.25rem; }
  details.employee:last-of-type { padding-bottom: 0.25rem; }
  details.employee > summary {
    list-style: none; cursor: pointer; outline: none;
    display: flex; justify-content: space-between; align-items: baseline;
    gap: 1rem; flex-wrap: wrap; padding: 0.25rem 0;
    border-radius: 6px; transition: background 0.12s ease;
  }
  details.employee > summary::-webkit-details-marker { display: none; }
  details.employee > summary::before {
    content: "▸"; color: var(--muted); margin-right: 0.5rem;
    display: inline-block; transition: transform 0.15s ease;
    font-size: 0.85rem;
  }
  details.employee[open] > summary::before { transform: rotate(90deg); }
  details.employee > summary:hover { background: var(--row-hover); }
  details.employee .name { font-size: 1.05rem; font-weight: 600; }
  details.employee .id { color: var(--muted); font-weight: normal; font-size: 0.85rem; margin-left: 0.4rem; }
  details.employee .stats { color: var(--muted); font-size: 0.9rem; }
  details.employee .stats strong { color: var(--text); }
  details.employee table { margin-top: 0.75rem; margin-left: 1.5rem; }

  table { border-collapse: collapse; width: calc(100% - 1.5rem); max-width: 640px; }
  th, td { text-align: left; padding: 0.4rem 0.7rem; border-bottom: 1px solid var(--border); font-size: 0.9rem; }
  th { background: transparent; font-weight: 600; color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
  tr { transition: background 0.1s ease; }
  tbody tr:hover { background: var(--row-hover); }
  td.hours { text-align: right; font-variant-numeric: tabular-nums; }
</style>
</head>
<body>
<header>
  <h1>Weekly Time Dashboard</h1>
  <div class="meta">
    Generated {{ generated_at }}
    {% if date_range %} &middot; {{ date_range }}{% endif %}
  </div>
</header>

<section class="kpis">
  <div class="kpi">
    <div class="label">Total hours</div>
    <div class="value">{{ "%.2f"|format(grand_total) }}</div>
    <div class="sub">across {{ summaries|length }} employee(s)</div>
  </div>
  <div class="kpi">
    <div class="label">Avg hours / employee</div>
    <div class="value">{{ "%.2f"|format(avg_per_employee) }}</div>
    <div class="sub">{{ total_entries }} entries logged</div>
  </div>
  <div class="kpi">
    <div class="label">Busiest day</div>
    <div class="value">{{ "%.2f"|format(busiest.hours) }}</div>
    <div class="sub">{{ busiest.date or "—" }}</div>
  </div>
  <div class="kpi">
    <div class="label">Top performer</div>
    <div class="value">{{ summaries[0].name if summaries else "—" }}</div>
    <div class="sub">{{ "%.2f"|format(summaries[0].total_hours) if summaries else 0 }} h</div>
  </div>
</section>

<section class="card">
  <h2>Hours per day</h2>
  <div class="chart-wrap"><canvas id="dailyChart"></canvas></div>
</section>

<section class="card">
  <h2>Per-employee breakdown</h2>
  {% for s in summaries %}
  <details class="employee"{% if loop.first %} open{% endif %}>
    <summary>
      <div><span class="name">{{ s.name }}</span><span class="id">#{{ s.employee_id }}</span></div>
      <div class="stats">
        <strong>{{ "%.2f"|format(s.total_hours) }} h</strong> &middot;
        {{ s.days_worked }} day(s) &middot;
        avg {{ "%.2f"|format(s.avg_hours) }} h/day
      </div>
    </summary>
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
  </details>
  {% endfor %}
</section>

<script>
  const dailyLabels = {{ daily_dates|tojson }};
  const dailyHours = {{ daily_hours|tojson }};

  const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const accent = isDark ? '#60a5fa' : '#3b82f6';
  const textColor = isDark ? '#94a3b8' : '#5f6b7a';
  const gridColor = isDark ? 'rgba(148, 163, 184, 0.12)' : 'rgba(15, 23, 42, 0.06)';

  const canvas = document.getElementById('dailyChart');
  const ctx = canvas.getContext('2d');
  const gradient = ctx.createLinearGradient(0, 0, 0, 260);
  gradient.addColorStop(0, isDark ? 'rgba(96, 165, 250, 0.45)' : 'rgba(59, 130, 246, 0.35)');
  gradient.addColorStop(1, isDark ? 'rgba(96, 165, 250, 0)' : 'rgba(59, 130, 246, 0)');

  new Chart(canvas, {
    type: 'line',
    data: {
      labels: dailyLabels,
      datasets: [{
        label: 'Total hours',
        data: dailyHours,
        borderColor: accent,
        backgroundColor: gradient,
        borderWidth: 2,
        fill: true,
        tension: 0.35,
        pointRadius: 4,
        pointHoverRadius: 6,
        pointBackgroundColor: accent,
        pointBorderColor: isDark ? '#0b1220' : '#ffffff',
        pointBorderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      animation: { duration: 600, easing: 'easeOutQuart' },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: isDark ? '#1e293b' : '#1f2933',
          padding: 10, cornerRadius: 6, displayColors: false,
          callbacks: { label: (c) => c.parsed.y.toFixed(2) + ' hours' },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { color: textColor, precision: 0 },
          grid: { color: gridColor, drawBorder: false },
        },
        x: {
          ticks: { color: textColor },
          grid: { display: false },
        },
      },
    }
  });
</script>
</body>
</html>
""")


def render_report(
    summaries: list[dict],
    daily: list[dict],
    output_path: str | os.PathLike[str],
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    grand_total = sum(s["total_hours"] for s in summaries)
    total_entries = sum(s["days_worked"] for s in summaries)
    avg_per_employee = grand_total / len(summaries) if summaries else 0.0
    busiest = max(daily, key=lambda d: d["hours"]) if daily else {"date": "", "hours": 0.0}
    date_range = f"{daily[0]['date']} → {daily[-1]['date']}" if daily else ""

    html = REPORT_TEMPLATE.render(
        summaries=summaries,
        daily_dates=[d["date"] for d in daily],
        daily_hours=[d["hours"] for d in daily],
        grand_total=grand_total,
        total_entries=total_entries,
        avg_per_employee=avg_per_employee,
        busiest=busiest,
        date_range=date_range,
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
        daily = daily_totals(time_log)
        render_report(summaries, daily, args.output)
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
