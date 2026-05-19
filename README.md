# Alpha Omega Employee Tool

Internal tooling for Alpha Omega: generate employee QR codes and weekly time-tracking reports from a Google Sheets source of truth.

## Features

- **QR code generation** — produce a printable PDF of per-employee QR codes from `employees.csv` or a Google Sheet.
- **Time reporting** — pull the weekly time log from Google Sheets and render an HTML summary report.
- **Sheets client** — shared Google Sheets API wrapper used by both tools.

## Architecture

```
employees.csv / Master Sheet ──► qr_generator.py    ──► output/qr_codes.pdf
Time Log Sheet (Practice 1)  ──► time_reporter.py   ──► output/weekly_report.html
                                       ▲
                                       │
                                sheets_client.py ◄── .env credentials
```

## Installation

The repo ships with sample data in [data/](data/), so you can run both
tools end-to-end immediately after `pip install` — no Google credentials
or `.env` required for the CSV path.

### 1. Clone and create a venv

```bash
git clone https://github.com/Historfic/alpha-omega-employee-tool.git
cd alpha-omega-employee-tool
python -m venv venv
```

### 2. Activate the venv

**Windows (PowerShell):**
```powershell
venv\Scripts\Activate.ps1
```
If you see `running scripts is disabled on this system`, either run this
once to allow local scripts:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
…or skip activation entirely and just call `venv\Scripts\python.exe` directly
in any later command — both work.

**Windows (cmd):**
```cmd
venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. (Optional) Configure `.env` for the Google Sheets path

`.env` is **only required if you want to read from Google Sheets** — the
CSV path needs no configuration. To opt in:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```
**macOS / Linux:**
```bash
cp .env.example .env
```

Then edit `.env` and fill in your sheet IDs / credentials path. See
[docs/setup.md](docs/setup.md) for the Google Cloud / service-account
walkthrough, and [config/README.md](config/README.md) for where
`credentials.json` belongs.

## Usage

Two entry points — pick whichever you prefer. They accept the same flags.

```bash
# Top-level dispatcher
python main.py qr [--csv PATH] [-o OUT] [-v]
python main.py report [--time-log PATH] [--employees PATH] [-o OUT] [-v]

# Or run each module directly
python -m src.qr_generator --help
python -m src.time_reporter --help
```

Out of the box, with no configuration, you should see:

```
$ python main.py qr
Wrote 5 QR codes to output/qr_codes.pdf

$ python main.py report
Wrote report for 5 employee(s), 22 entries -> output/weekly_report.html
```

Open `output/qr_codes.pdf` and `output/weekly_report.html` to view the artifacts.

Common flags:

| Flag | Purpose |
|---|---|
| `--csv` / `--time-log` / `--employees` | Override the input CSV path |
| `--sheet-id` / `--sheet-gid` *(qr only)* | Read employees from a Google Sheet instead of CSV. `--sheet-gid` is the worksheet ID from `#gid=` in the sheet URL. |
| `--time-log-sheet-id` / `--time-log-sheet-gid` *(report only)* | Read the Practice 1 time log from a Google Sheet. Columns expected: `Date \| Employee \| Time_in \| Time_out \| Total_hours`. Rows with empty `Time_out` (active sessions) are skipped. |
| `-o` / `--output` | Override the output path |
| `-v` / `--verbose` | Debug-level logging |
| `-h` / `--help` | Show usage and exit |

For both tools, the source defaults to **Sheets** if the relevant `*_SHEET_ID`
env var is set in `.env` (or the environment); otherwise it falls back to the
CSV at `data/employees.csv` / `data/time_log.csv`. To force CSV when the env
var is set, pass `--sheet-id ""` (or `--time-log-sheet-id ""`).

Defaults read from env vars (`EMPLOYEES_CSV`, `TIME_LOG_CSV`,
`QR_PDF_OUTPUT`, `REPORT_HTML_OUTPUT`) if set, otherwise from the paths
documented in `.env.example`.

Outputs land in [output/](output/) (gitignored).

**Exit codes**: `0` success, `1` unexpected runtime error, `2` bad input
(missing/empty file).

## Project Layout

```
alpha-omega-employee-tool/
├── main.py         # CLI dispatcher (python main.py qr | report)
├── src/            # application code (qr_generator, time_reporter, sheets_client)
├── config/         # credential placement instructions (credentials.json goes here, gitignored)
├── data/           # sample inputs (employees.csv, time_log.csv)
├── output/         # generated PDFs / HTML (gitignored)
├── tests/          # pytest suite
└── docs/           # setup + reference docs
```

## Development

```bash
pip install -r requirements.txt
pytest
```

## License

MIT — see [LICENSE](LICENSE).
