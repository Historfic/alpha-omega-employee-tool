# The clock-in / clock-out workflow

The thing that actually records a shift does not live in this repo, or in the
dashboard repo. It is an **n8n workflow named `clock-in-out`**, and for a long
time it was invisible: the QR codes this tool prints encode a bare
`employee_id`, so nothing in the code says what reads them.

A sanitized export lives here so the logic is version-controlled and readable
without n8n access. It is a copy for reference — **n8n remains the source of
truth**, and editing this file changes nothing.

## How a scan becomes a row

```
QR scan
   │
   ▼
Webhook  ──▶  Edit Fields  ──▶  If (valid id + action?)
                                   │            │
                                   │            └──▶  Respond Error
                                   ▼
                            Read All Rows  ──▶  Decide  ──▶  Switch
                                                                │
                        ┌───────────────────────────────────────┤
                        ▼                                       ▼
                   Append row                              Update row
                   (clock IN)                              (clock OUT)
                        │                                       │
                        └──────────────┬────────────────────────┘
                                       ▼
                          Read Pivot Dates ─▶ Build Pivot Cells ─▶ Write Pivot
```

`Decide` is the brain. It matches the employee, finds any open shift, works out
the hours, and builds the HTML the worker sees on their phone.

## How hours are counted

The sheet does **not** record how long a shift ran. It records whether the
shift was completed:

| Condition | `Total_hours` |
|---|---|
| Worked 4h30m or more | **5** — the full shift, however long it actually ran |
| Shorter than that | rounded to the hour, up only at 40+ min past, capped at 5 |
| Clocked out after midnight | overtime: actual rounded hours, uncapped |

This matters for anything reading the sheet. Comparing `Total_hours` against
the raw clock span will disagree on every shift longer than five hours — not
because the sheet is wrong, but because it is recording something else. The
dashboard's cross-check mirrors the rule above rather than the span.

## Emergency hours are gone

The workflow used to classify any shift starting outside 4–11 PM as an
emergency, leave `Total_hours` blank, and write the hours to an
`Emergency_Log` column instead. When that column was deleted from the sheet,
the branch kept firing — and because the Google Sheets node silently drops
unknown columns, it did not error. It recorded a worked shift as no hours at
all before anyone noticed.

Every emergency feature has been removed: the classification, the blank-total
branch, the column mappings on both Sheets nodes, and the pivot column. Every
shift now totals the same way, so no path can leave hours unrecorded.

## Known limits

- **No authentication.** The webhook takes `employee_id` and `action` from the
  query string, so anyone holding the URL can record a scan for anyone. This
  is why the webhook path is redacted below.
- **Whole-sheet read per scan.** `Read All Rows` pulls the entire log on every
  scan. Fine at this size; it will drag as the log grows.

## Managing the roster

There is no admin screen. The roster is the **`Employees` tab** of the same
spreadsheet, and the workflow reads it on every scan:

```
      A            B       C                   D     E
1     employee_id  name    daily_target_hours  pin   active
2     001          Ivan    5                         TRUE
3     002          Daniel  5                         FALSE
```

| To | Do |
|---|---|
| Add someone | Append a row. The next scan picks it up — no deploy |
| Remove someone | Set `active` to `FALSE` |

**Deactivate leavers, never delete them.** `Time_Log` joins to the roster by
**name**, so removing a row orphans every shift ever filed under it. `FALSE`
takes someone off the clock while their history stays readable.

**A blank `active` cell means active.** Only an explicit `false`, `no`, `n`,
`0`, `inactive` or `left` deactivates. Reading a missing column as "not
active" would take the whole team off the clock at once.

An id that is absent or deactivated is refused outright — the scan returns
"not on the roster" and writes nothing. That matters: it used to write
`Unknown (003)` into the payroll sheet, which looks like a real shift and
gets paid.

The `pin` column is unused here and kept blank. It exists so the layout
matches the El Bethel sibling project, whose kiosk needs one.

## What is redacted

Placeholders replace anything that grants access or names a live resource:

| Placeholder | What it was |
|---|---|
| `YOUR_WEBHOOK_PATH`, `YOUR_WEBHOOK_ID` | the live clock-in endpoint |
| `YOUR_SPREADSHEET_ID` | the time log spreadsheet |
| `YOUR_CREDENTIAL_ID`, `YOUR_CREDENTIAL_NAME` | n8n Google credential refs |

Importing this file will not work until those are filled in. That is deliberate
— this repo is public, and the webhook path is enough on its own to write to
your payroll sheet.

## Re-exporting after a change

In n8n: open the workflow → **⋯** → **Download**. Or through the public API:

```bash
curl -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$N8N_BASE_URL/api/v1/workflows/$N8N_WORKFLOW_ID"
```

Both variables are in `.env.example`. Redact the four values above before
committing the result.
