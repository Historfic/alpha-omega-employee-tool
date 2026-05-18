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

> _TODO: fill in once CLI is wired up._

```bash
# Generate QR code PDF
python -m src.qr_generator

# Generate weekly time report
python -m src.time_reporter
```

Outputs land in [output/](output/) (gitignored).

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
