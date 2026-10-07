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
                         Read Pivot Layout ─▶ Build Pivot Cells ─▶ Write Pivot
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

## Clocking in with a PIN

The same webhook also opens with a PIN, so one shared code can serve everyone
and a new hire can clock in without a printed card. That shared QR is on the
dashboard's Employees page, with a printable sheet at `/employees/qr` — both
behind the page's password, since the code is the bare webhook link:

| Request | What happens |
|---|---|
| no `employee_id`, no `pin` | `Decide` returns `ask_pin` → **Respond Ask PIN**, a form that resubmits as `?pin=NNNN` |
| `?pin=NNNN` | the person whose `Employees` column D holds that PIN, then the usual choose page |
| `?employee_id=001` | unchanged — the per-person QR codes already printed keep working |

The confirm taps carry whatever opened the page (`display_ident`), so a PIN
scan stays a PIN scan. A PIN shared by two people opens **neither** account,
and a wrong PIN, a leaver's PIN and a shared PIN all get the same "That PIN
did not match" answer, so the page tells a guesser nothing.

PINs may start with 0. Sheets keeps a typed `0482` as the number 482, so the
roster workflow writes PINs as text and `Decide` pads a short stored value back
to four digits. A blank cell never matches.

## Known limits

- **The id path has no authentication.** The webhook takes `employee_id` and
  `action` from the query string, so anyone holding the URL can record a scan
  for anyone. This is why the webhook path is redacted below. A PIN scan puts
  the PIN in the URL too — it lands in the phone's history and in n8n's
  execution log.
- **Whole-sheet read per scan.** `Read All Rows` pulls the entire log on every
  scan. Fine at this size; it will drag as the log grows.

## Managing the roster

The roster is the **`Employees` tab** of the same spreadsheet, and the clock
reads it on every scan:

```
      A            B       C                   D     E
1     employee_id  name    daily_target_hours  pin   active
2     001          Ivan    5                   ••••  TRUE
3     002          Daniel  5                         FALSE
4     003          Jeremy  5                   ••••  TRUE
```

Change it from the dashboard's **Employees** page (password-protected): add
someone, change a name or PIN, deactivate or reactivate. The dashboard reads
the sheet only, so the page posts to a second workflow, **`A&O Roster`**
(`POST /webhook/ao-roster`, refused without the `x-roster-token` header that
matches `ROSTER_TOKEN` in `.env`). It re-reads the tab, checks what only the
sheet can know — is that PIN taken, did somebody take that id a second ago —
and writes. Redacted copy: `roster.workflow.json`.

| To | Do |
|---|---|
| Add someone | Employees page → **Add to the roster**. They can clock in by PIN at once |
| Remove someone | **Deactivate** — their row and shifts stay |
| Rename someone | Edit the name. Every `Sheet1` row and their `Sheet2` pivot headers move with it, in one batched write — the clock matches names exactly, so leaving them would strand an open shift |

**Ids are never reused.** A new person gets one past the highest id ever
issued, because the printed QR codes carry the id: a recycled number would
clock the new person in whenever the old card was scanned.

## The `Sheet2` pivot

One row per date, and per person an In/Out pair plus a total. No names are
listed in the workflow: `Read Pivot Layout` reads column A and header rows 1–2
in one `batchGet`, and `Build Pivot Cells` finds each person's columns by
header — their name over the In/Out pair in row 1 (merged across both), and
`Total Hours of <name>` in row 2.

```
row 1         | Ivan    | Daniel  | Nae     |                         …  | Jeremy  |
row 2   Date  | In  Out | In  Out | In  Out | Total Hours of Ivan …   …  | In  Out | Total Hours of Jeremy
```

A name list in that node once left everybody added after it out of the pivot.
Now somebody with no columns gets a block on their first scan, **appended past
the last used column** with the same header formatting. Appending rather than
inserting beside the others is deliberate: nothing existing moves, so no
historical cell and no hand-written formula in the tab (there are weekly
`=SUM(...)` cells) ever shifts. Renaming somebody on the Employees page renames
their pivot headers in the same batched write, so their history stays theirs.

If the header rows cannot be read — or row 2 no longer starts with `Date` — the
node writes nothing rather than guess at columns. The punch itself is never at
risk: this branch runs after the scan has been recorded and answered.

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

## What is redacted

Placeholders replace anything that grants access or names a live resource:

| Placeholder | What it was |
|---|---|
| `YOUR_WEBHOOK_PATH`, `YOUR_WEBHOOK_ID` | the live clock-in endpoint |
| `YOUR_SPREADSHEET_ID` | the time log spreadsheet |
| `YOUR_CREDENTIAL_ID`, `YOUR_CREDENTIAL_NAME` | n8n Google credential refs |
| `YOUR_ROSTER_TOKEN` | the roster webhook's shared secret (`ROSTER_TOKEN`) |

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
