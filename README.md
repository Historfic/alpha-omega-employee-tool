# Alpha Omega Master Dashboard

Executive dashboard for Alpha Omega time-clock data. Pulls scan data from the shared Google Sheet and surfaces KPIs, trends, employee status, and anomalies.

## Stack

- Streamlit (UI)
- gspread (Google Sheets access)
- pandas (data processing)
- Deployed on Streamlit Cloud

## Quick start (local)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run dashboard.py
```

Then open the URL printed in the terminal (typically http://localhost:8501).

## Status

Phase 1 — Hello World scaffolding. Sheets integration, KPIs, and charts arrive in later phases.
