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

> _TODO: finalize once dependencies are pinned._

```bash
git clone https://github.com/Historfic/alpha-omega-employee-tool.git
cd alpha-omega-employee-tool
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in real values
```

See [docs/setup.md](docs/setup.md) for the Google Cloud / service-account walkthrough, and [config/README.md](config/README.md) for where `credentials.json` belongs.

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

Common flags:

| Flag | Purpose |
|---|---|
| `--csv` / `--time-log` / `--employees` | Override the input CSV path |
| `--sheet-id` / `--sheet-gid` *(qr only)* | Read employees from a Google Sheet instead of CSV. `--sheet-gid` is the worksheet ID from `#gid=` in the sheet URL. |
| `-o` / `--output` | Override the output path |
| `-v` / `--verbose` | Debug-level logging |
| `-h` / `--help` | Show usage and exit |

For `python main.py qr`, the source defaults to **Sheets** if
`EMPLOYEE_SHEET_ID` is set in `.env` (or the environment); otherwise it falls
back to the CSV at `data/employees.csv`. To force CSV when the env var is set,
pass `--sheet-id ""`.

Defaults read from env vars (`EMPLOYEES_CSV`, `TIME_LOG_CSV`,
`QR_PDF_OUTPUT`, `REPORT_HTML_OUTPUT`) if set, otherwise from the paths
documented in `.env.example`.

Outputs land in [output/](output/) (gitignored).

**Exit codes**: `0` success, `1` unexpected runtime error, `2` bad input
(missing/empty file).

## Project Layout

```
alpha-omega-employee-tool/
├── src/            # application code
├── config/         # credential placement instructions
├── data/           # sample inputs (employees.csv)
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
