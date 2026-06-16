# Alpha Omega Time Log

QR-code-driven clock-in/out logging to a Google Sheet, powered by an n8n workflow on `gogreen.app.n8n.cloud`.

## What's in this repo

- `qr/` — 4 QR code PNGs (Ivan IN/OUT, Daniel IN/OUT). Each encodes the webhook URL with the right `employee_id` and `action`. Color-coded: green = clock IN, red/blue = clock OUT.
- `preview/` — Standalone HTML mockups of every response page (Clock In, Clock Out, Already Clocked In, No Clock-in, Scan Failed, plus shift-type variants). Open in any browser to preview the page styling.
- `Daniel.txt` — Original confirmation page template (kept for reference).

## Schedule (Asia/Manila, PM)

| IN time | Bucket |
|---|---|
| 4:00–5:59 PM | early |
| 6:00–6:05 PM | on time |
| 6:06–6:29 PM | late |
| 6:30–7:00 PM | adjusted (effective start 7:00 PM) |
| 7:01–10:59 PM | brutally late |
| 11:00 PM+ or midnight–3:59 PM | emergency |

| OUT time | Bucket |
|---|---|
| <10:30 PM | early |
| 10:30–11:59 PM | on time |
| 12:00 AM+ | overtime (no cap) |

## Total_hours rules

- **regular** (early / on time / late IN): rounded actual hours (IN → OUT)
- **adjusted**: rounded actual from 7:00 PM effective start
- **brutally late**: rounded actual (no contract protection)
- **emergency**: blank; rounded actual goes to `Emergency_Log` column instead

Hours are stored as numbers so `=SUM()`, `=SUMIF()`, and pay-calc formulas work directly.

## Sheet columns

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| Date | Employee | Time_in | Time_out | Total_hours | Emergency_Log |

Cross-midnight shifts keep the IN date in column A.

## Pivot timesheet sync

A second tab in the same spreadsheet (gid `1545975491`) is a human-readable
monthly timesheet: one row per date, with Ivan and Daniel side-by-side in
columns. The `clock-in-out` workflow mirrors each scan into it in real time:

The pivot tab is **"Sheet2"** (gid `1545975491`) and has **two header rows**
(row 1 = employee names, row 2 = Date/In/Out labels), so data starts on row 3.
Live-sync pipeline added after the existing sheet write:

- `Read Pivot Dates` (HTTP) reads pivot column A (`Sheet2!A1:A1000`).
- `Build Pivot Cells` (Code; logic mirrored in `tools/pivot_cells.js`) takes the
  canonical event from the `Decide` node, **looks up the matching date row** in
  column A (appending a new dated row if the date is absent), and builds Google
  Sheets `updateCells` requests addressed by **gid + row/column index** (the
  pivot has three columns all titled "Out", so header-name writes are ambiguous).
- `Write Pivot` (HTTP) POSTs them to `spreadsheets:batchUpdate` with the existing
  `Atutor` credential, in parallel with the Respond nodes and continue-on-error,
  so it never blocks or breaks an employee's clock-in/out.

Mapping: `kaz`/`001` -> Ivan (cols B/C/H/K), `david`/`002` -> Daniel
(cols D/E/I/L). **Nae's columns (F/G/J/M) are manual and never written.**

Tooling (all require `n8n_api.txt`; Windows curl needs `--ssl-no-revoke`):
- `tools/patch_workflow.py` — add/refresh the live-sync nodes in the workflow.
- `tools/backfill_pivot.py` — rebuild the pivot from a Sheet1 CSV export.
- `tools/reconcile_pivot.py` — diff the pivot against Sheet1 and fix only the
  wrong cells (set/clear), with a `MIN_ROW` floor to protect finalized rows.
- `node tools/pivot_cells.test.js` — unit-test the cell builder.

## Secrets

`n8n_api.txt` (the n8n API key) is gitignored and lives only on the original machine. To set up on a new device, ask the workflow owner for the API key and recreate that file locally.
