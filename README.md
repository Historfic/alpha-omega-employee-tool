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

## Secrets

`n8n_api.txt` (the n8n API key) is gitignored and lives only on the original machine. To set up on a new device, ask the workflow owner for the API key and recreate that file locally.
