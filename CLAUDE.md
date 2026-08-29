# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

## Commands

```bash
venv/Scripts/python.exe -m pytest        # the whole suite (Windows)
python -m pytest                         # elsewhere

python main.py qr           [--csv PATH] [-o OUT] [-v]
python main.py report       [--time-log PATH] [--employees PATH] [-o OUT]
python main.py fill-hours   [--overwrite] [--max-writes N] [--apply] [-v]
```

`fill-hours` is a **dry run unless `--apply` is passed**. It edits a payroll
record, so it prints every cell it would change and writes nothing by default.

## Architecture

Three parts over one Google Sheet. The sheet is the source of truth.

```
QR scan → n8n webhook → Google Sheet ← alpha-omega-dashboard-v2 (read-only)
                             ↑
                        this repo (fill-hours, read-write)
```

This repo holds the QR generator, an HTML reporter, and the `fill-hours`
write-back. The dashboard lives in the sibling repo `alpha-omega-dashboard-v2`
and authenticates read-only — most of the shared rules are documented in its
`CLAUDE.md`.

The clock workflow itself is **not in any repo**. It is an n8n workflow named
`A&O Clock Log`, edited live through the n8n public API. A redacted export and
its documentation are in `docs/n8n/`; that copy is for reading, n8n is the
source of truth.

### The sheet

```
Sheet1      A Date | B Employee | C Time_in | D Time_out | E Total_hours
Employees   A employee_id | B name | C daily_target_hours | D pin | E active
```

`Sheet1` joins to `Employees` **by name**, so nobody is deleted from the
roster — removing a row orphans every shift filed under that name. Leavers get
`active` = `FALSE`. A blank `active` cell means active.

## Rules the code depends on

**The pay rule exists in three places** — `payable_hours` here,
`computeTotalHours` in the workflow's `Decide` node, and `expectedShiftHours`
in the dashboard. Change one and you must change all three. This copy was left
behind once: it went on deducting a one-hour break long after the other two
stopped, and would have written figures the dashboard immediately flags as
wrong.

The rule: **every clocked hour, rounded to the hour, rounding up from 40
minutes past.** No fixed shift length, no cap. Hours are flexible against a
five-hour target, so clocking in early and out early is a normal day.

**A bare `10:00` is 24-hour time**, not an evening clock-out. `parse_time_of_day`
reads it as 10 AM, which against an evening clock-in gives a negative span and
returns `None` rather than a guess. This is the trap behind the original
double-billing bug.

**A shift crossing midnight reads as a negative span**, because both clock
times carry the same sheet date. Add a day, capped at `MAX_SHIFT_HOURS` —
beyond that it is bad data, not a long shift.

**A spacer row still consumes its sheet row number.** `build_plan` counts rows
positionally; skipping a blank one would land every write below it a row off.

## What `fill-hours` must never do

The tests are weighted toward the refusals, and they are the point of the
command:

- **Never write without `--apply`.** Dry run is the default.
- **Never touch an open shift.** No `Time_out` means there is nothing to total.
- **Never overwrite a typed figure** unless `--overwrite` is passed. A number
  someone entered is a human decision and outranks anything computed.
- **Never guess** at unreadable clock times — report and skip.
- **Never exceed `--max-writes`** (default 200), so a misconfigured run cannot
  rewrite the sheet.

Writes go out as one batched request rather than a call per cell: a hundred
individual writes would burn the per-minute quota and could leave the sheet
half-updated.

## Writing code here

Comments explain **why**, usually by naming the failure the code prevents.
Tests carry the same weight — `tests/` records policy decisions, so when
behaviour changes, update the reasoning rather than just the assertion.
