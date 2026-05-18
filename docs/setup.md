# Google Cloud Setup

End-to-end walkthrough for wiring up a Google service account so this tool
can read (and optionally write) the employee master sheet and the weekly
time log.

## 1. Create / select a Google Cloud project

1. Go to <https://console.cloud.google.com/>.
2. Top bar → project picker → **New Project**.
3. Name it (e.g. `alpha-omega-tools`) and create.

## 2. Enable the required APIs

In the project, open **APIs & Services → Library** and enable:

- **Google Sheets API**
- **Google Drive API** (needed by `gspread` to list/open sheets)

## 3. Create a service account

1. **APIs & Services → Credentials → Create credentials → Service account**.
2. Give it a name (e.g. `alpha-omega-sheets-reader`).
3. Role: leave blank (project-level role isn't required — we'll share each
   sheet directly).
4. Finish.

## 4. Generate a JSON key

1. Open the new service account → **Keys** tab → **Add key → Create new key**.
2. Choose **JSON**, download the file.
3. Save it as `config/credentials.json` in this repo (see
   [../config/README.md](../config/README.md)). **Never commit it.**

## 5. Share the target spreadsheets with the service account

The service account has an email like
`alpha-omega-sheets-reader@<project>.iam.gserviceaccount.com`.

For each sheet (`EMPLOYEE_SHEET_ID`, `TIME_LOG_SHEET_ID`):

1. Open the sheet in Google Sheets.
2. **Share** → paste the service-account email.
3. Grant **Viewer** (or **Editor** if writing is needed).

## 6. Fill in `.env`

Copy `.env.example` → `.env` and set:

- `GOOGLE_APPLICATION_CREDENTIALS` (defaults to `config/credentials.json`)
- `EMPLOYEE_SHEET_ID` and `EMPLOYEE_SHEET_RANGE`
- `TIME_LOG_SHEET_ID` and `TIME_LOG_SHEET_RANGE`

## 7. Verify

Once `requirements.txt` is installed and `.env` is populated:

```bash
python -m src.qr_generator
python -m src.time_reporter
```

Outputs land in [../output/](../output/).
