"""CLI integration tests: exit codes and error messages from each entry point.

These call the module `main()` functions directly with argv lists, so they
don't spawn subprocesses — they're fast and don't depend on having a venv
shim on PATH.
"""
from __future__ import annotations

import pytest

from src import qr_generator, time_reporter


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """Clear sheet-related env vars, neutralize load_dotenv, chdir to clean dir.

    The module main() functions call load_dotenv(); without the patch they'd
    walk up from src/*.py and load the developer's real .env, which would
    set TIME_LOG_SHEET_ID and route the test into the Sheets code path.
    """
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    for var in (
        "EMPLOYEE_SHEET_ID", "EMPLOYEE_SHEET_GID",
        "TIME_LOG_SHEET_ID", "TIME_LOG_SHEET_GID",
        "EMPLOYEES_CSV", "TIME_LOG_CSV",
        "QR_PDF_OUTPUT", "REPORT_HTML_OUTPUT",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)


def _write_csv(path, header, rows):
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- qr_generator

class TestQrGeneratorCli:
    def test_missing_csv_returns_bad_input(self, capsys):
        rc = qr_generator.main(["--csv", "nope.csv"])
        assert rc == qr_generator.EXIT_BAD_INPUT
        assert "not found" in capsys.readouterr().err

    def test_empty_csv_returns_bad_input(self, tmp_path, capsys):
        csv_path = tmp_path / "empty.csv"
        _write_csv(csv_path, "employee_id,first_name,last_name,email", [])
        rc = qr_generator.main(["--csv", str(csv_path)])
        assert rc == qr_generator.EXIT_BAD_INPUT
        assert "no employees" in capsys.readouterr().err

    def test_happy_path_returns_ok_and_writes_pdf(self, tmp_path, capsys):
        csv_path = tmp_path / "emp.csv"
        _write_csv(
            csv_path,
            "employee_id,first_name,last_name,email",
            ["001,Ivan,Quinola,ivan@example.com"],
        )
        out_path = tmp_path / "out.pdf"
        rc = qr_generator.main(["--csv", str(csv_path), "-o", str(out_path)])
        assert rc == qr_generator.EXIT_OK
        assert out_path.exists() and out_path.stat().st_size > 0
        assert "Wrote 1 QR codes" in capsys.readouterr().out


# ---------------------------------------------------------------- time_reporter

class TestTimeReporterCli:
    def test_missing_csv_returns_bad_input(self, capsys):
        rc = time_reporter.main(["--time-log", "nope.csv", "--employees", "also-nope.csv"])
        assert rc == time_reporter.EXIT_BAD_INPUT
        assert "not found" in capsys.readouterr().err

    def test_empty_time_log_returns_bad_input(self, tmp_path, capsys):
        emp = tmp_path / "emp.csv"
        _write_csv(emp, "employee_id,first_name,last_name,email", ["001,Ivan,Q,i@e.com"])
        tl = tmp_path / "log.csv"
        _write_csv(tl, "employee_id,date,clock_in,clock_out", [])
        rc = time_reporter.main(["--time-log", str(tl), "--employees", str(emp)])
        assert rc == time_reporter.EXIT_BAD_INPUT
        assert "no complete entries" in capsys.readouterr().err

    def test_happy_path_returns_ok_and_writes_html(self, tmp_path, capsys):
        emp = tmp_path / "emp.csv"
        _write_csv(
            emp,
            "employee_id,first_name,last_name,email",
            ["001,Ivan,Q,i@e.com"],
        )
        tl = tmp_path / "log.csv"
        _write_csv(
            tl,
            "employee_id,date,clock_in,clock_out",
            ["001,2026-05-11,09:00,17:00"],
        )
        out = tmp_path / "out.html"
        rc = time_reporter.main([
            "--time-log", str(tl),
            "--employees", str(emp),
            "-o", str(out),
        ])
        assert rc == time_reporter.EXIT_OK
        assert out.exists()
        html = out.read_text(encoding="utf-8")
        assert "Ivan Q" in html
        assert "8.00" in html  # total hours
