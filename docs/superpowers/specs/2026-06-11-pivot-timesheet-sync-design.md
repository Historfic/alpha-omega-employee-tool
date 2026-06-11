# Pivot Timesheet Sync — Design

**Date:** 2026-06-11
**Status:** Approved (pending written-spec review)
**Author:** Claude + rafael@mcgendigital.com

## Goal

Whenever the live time-log system records a clock-in or clock-out, mirror that
data into the human-readable **pivot timesheet** automatically, in real time,
without changing how the existing system behaves and without touching the
columns a human maintains by hand.

## Context

The whole system already exists as an n8n workflow named **`clock-in-out`**
(id `gpThnM5QjdMrkjP1`, active) on `https://gogreen.app.n8n.cloud`.

Flow today:

```
QR scan -> Webhook -> Edit Fields -> If -> Read All Rows (Sheet1)
        -> Decide (code) -> Switch
             -> Append row (Sheet1)  -> Respond IN     (clock-in)
             -> Update row (Sheet1)  -> Respond OUT    (clock-out)
             -> Respond No Clock-in / No Clock-out / Error
```

### Both sheets are tabs in ONE spreadsheet

Spreadsheet: **Alpha Omega Time Log**
(`1yms8rFDnPo-QRENrdSY6PJ2i11Shdd7RAc14jktCj9E`).

- **Source — Sheet1** (gid `0`): the transactional log, ~one row per employee
  per day. Columns: `Date | Employee | Time_in | Time_out | Total_hours |
  Emergency_Log`.
- **Destination — pivot tab** (gid `1545975491`): one row per calendar date,
  employees side-by-side. Header in row 1, data from row 2. Row 2 = `06/01/2026`,
  one contiguous row per day through `10/20/2026`.

### Pivot tab columns (0-based index in parentheses)

| Col | Index | Header                  |
|-----|-------|-------------------------|
| A   | 0     | Date                    |
| B   | 1     | Ivan In                 |
| C   | 2     | Out (Ivan)              |
| D   | 3     | Daniel In               |
| E   | 4     | Out (Daniel)            |
| F   | 5     | Nae In        *(manual)*|
| G   | 6     | Out (Nae)     *(manual)*|
| H   | 7     | Total Hours of Ivan     |
| I   | 8     | Total Hours of Daniel   |
| J   | 9     | Total Hours of Nae *(manual)* |
| K   | 10    | Emergency Logs of Ivan  |
| L   | 11    | Emergency Logs of Daniel|
| M   | 12    | Emergency Logs of Nae *(manual)* |

Note: columns B, D, F carry the employee name in the header; C, E, G are all
literally named **"Out"** (duplicate headers — see Decisions).

### Known facts from the live workflow

- `employee_id` is zero-padded to 3 digits: `001 -> Ivan`, `002 -> Daniel`
  (the QR labels "kaz"/"david" are cosmetic; the webhook param is 001/002).
- Dates are formatted `MM/dd/yyyy` in **both** tabs.
- Times are strings like `6:02 PM`.
- `Total_hours` and emergency hours are **numbers** (so `=SUM` works).
- Google Sheets credential on the existing nodes:
  `googleSheetsOAuth2Api`, id `y7Nn8fmXcH1bKw37`, name **"Atutor"**
  (full spreadsheets scope — reused as-is, no new auth).

### Scope

- **In scope:** mirror Ivan (`001`) and Daniel (`002`) only.
- **Out of scope / never written:** Nae's columns (F, G, J, M) and any other
  cell. Nae is maintained manually.

## Approach (chosen)

Do the mirror **inside the existing `clock-in-out` workflow** as a parallel,
non-blocking branch that writes to the pivot tab via the Google Sheets REST
API, addressing cells by **gid + row/column index**.

Alternatives considered and rejected:

- **Google Apps Script (time-trigger poll):** decoupled and needs no n8n key,
  but not real-time and lives outside the workflow. Rejected: user wants n8n /
  real-time.
- **Live IMPORTRANGE/QUERY formulas:** brittle against the fixed merged-header
  template; hard to confine to just Ivan/Daniel without disturbing Nae.
  Rejected.
- **n8n Google Sheets "update row" node (write by header name):** cannot target
  the right "Out" column because three columns share the header "Out".
  Rejected in favor of index-addressed REST writes.

## Changes (three, all within `clock-in-out`)

### 1. Patch the `Decide` code node (OUT branch only)

The clock-out branch currently emits `row_number, Time_out, Total_hours,
Emergency_Log`. Add two fields so the pivot write can target the correct
**IN-date** row (critical for cross-midnight shifts) and employee:

- `Date`  = the open IN row's `Date` (i.e. `row.Date`)
- `Employee` = `employeeName`

No other logic in `Decide` changes. The IN branch already emits `Date` and
`Employee`.

### 2. New Code node `Build Pivot Cells`

Inputs: items from `Append row` (IN) and `Update row` (OUT).

Logic:

1. Read `display_employee` (present on both paths; "Ivan" / "Daniel"). If it is
   not Ivan or Daniel, output nothing (skip).
2. Column map (0-based):
   - Ivan:   In=1 (B), Out=2 (C), Total=7 (H), Emergency=10 (K)
   - Daniel: In=3 (D), Out=4 (E), Total=8 (I), Emergency=11 (L)
3. Compute the target row from `Date` (deterministic):
   `rowIndex = 1 + daysBetween(2026-06-01, eventDate)` (0-based API index; row 2
   of the sheet = rowIndex 1 = `06/01/2026`). So `06/11/2026` ->
   `1 + 10 = rowIndex 11` = sheet row 12. Parse the `MM/dd/yyyy` date with luxon
   in `Asia/Manila`. If `rowIndex < 1` or the date is outside Jun 1 - Oct 20
   2026, output nothing (guard against writing past the template).
4. Build a Google Sheets `batchUpdate` body with one `updateCells` request per
   cell to write (cells are non-adjacent, so one request each):
   - `operation: "append"` (IN)  -> write **In** cell = `Time_in` (stringValue).
   - `operation: "update"` (OUT) -> write **Out** = `Time_out` (stringValue),
     **Total** = `Total_hours` (numberValue, only if non-empty),
     **Emergency** = `Emergency_Log` (numberValue, only if non-empty).
   - Empty values are skipped (cell left untouched, not blanked).
5. Output a single item carrying the `batchUpdate` body for the HTTP node.

`updateCells` request shape (one cell):

```json
{ "updateCells": {
    "range": { "sheetId": 1545975491,
               "startRowIndex": <rowIndex>, "endRowIndex": <rowIndex + 1>,
               "startColumnIndex": <colIndex>, "endColumnIndex": <colIndex + 1> },
    "rows": [ { "values": [ { "userEnteredValue": { "stringValue": "6:02 PM" } } ] } ],
    "fields": "userEnteredValue" } }
```

(`numberValue` instead of `stringValue` for Total/Emergency.)

### 3. New HTTP Request node `Write Pivot`

- Method: `POST`
- URL: `https://sheets.googleapis.com/v4/spreadsheets/1yms8rFDnPo-QRENrdSY6PJ2i11Shdd7RAc14jktCj9E:batchUpdate`
- Auth: **Predefined Credential Type -> Google Sheets OAuth2 API ->
  "Atutor"** (`y7Nn8fmXcH1bKw37`).
- Body: JSON = the `{ "requests": [ ... ] }` built by `Build Pivot Cells`.
- **On error: Continue** — a pivot failure must never error the run or block
  the employee's clock response.

### Wiring (parallel, non-blocking)

```
Append row -+-> Respond IN          (unchanged)
            +-> Build Pivot Cells -> Write Pivot
Update row -+-> Respond OUT         (unchanged)
            +-> Build Pivot Cells -> Write Pivot
```

The Respond nodes keep their existing single connection so the employee always
gets their confirmation page immediately; the pivot branch runs alongside.

## Data flow example (cross-midnight)

1. Daniel scans IN, 6:02 PM, 06/11/2026.
   - Sheet1: append `06/11/2026 | Daniel | 6:02 PM | | |`.
   - Pivot: `D12 = "6:02 PM"` (rowIndex 11 -> sheet row 12; Daniel In = col D).
2. Daniel scans OUT, 12:30 AM, 06/12/2026.
   - `Decide` finds the open IN row, uses its date `06/11/2026`.
   - Sheet1: update that row with `Time_out=12:30 AM, Total_hours=6`.
   - Pivot (still row 12, the IN date): `E12 = "12:30 AM"`, `I12 = 6`
     (number). Emergency empty -> skipped.

## Design properties

- **Idempotent per cell:** each write overwrites specific cells; re-running an
  event reasserts the same values. No duplicates.
- **Real-time:** writes at scan moment.
- **Non-blocking & fault-isolated:** employee response never waits on or breaks
  from the pivot write.
- **Nae-safe:** only columns B/C/H/K and D/E/I/L are ever written.
- **Numeric-safe:** Total/Emergency written as numbers for payroll formulas.
- **No new credentials, no new workflow.**

## Decisions

- **Address cells by gid + index, not header name** — the three duplicate
  "Out" headers make name-based writes ambiguous; index addressing is exact and
  permits explicit per-value typing.
- **Row resolution = deterministic** (date math), not lookup. The pivot is a
  fixed, machine-owned, one-row-per-day template that nothing else writes to,
  so the inserted/reordered-row fragility that a lookup guards against does not
  apply. Trade-off accepted for simplicity and zero extra API calls.

## Risks & mitigations

- **Pivot rows get inserted/reordered** -> deterministic mapping writes the
  wrong row silently. Mitigation: documented assumption; out-of-range guard
  prevents writing past the template; switchable to lookup later if needed.
- **Date outside Jun 1 - Oct 20 2026** -> guard skips the write. When the
  timesheet is extended for a new period, the date window in `Build Pivot
  Cells` must be widened (or made dynamic).
- **Pivot write fails** -> continue-on-error keeps the clock working; the next
  event for that employee reasserts values; the existing
  `clock-in-out error alerts` workflow remains the channel for genuine
  failures.

## Out of scope

- Backfilling pivot rows for clock events recorded before this ships.
- Any change to QR codes, response pages, schedule buckets, or hours math.
- Nae automation.
