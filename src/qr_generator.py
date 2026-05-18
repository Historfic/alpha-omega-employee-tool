"""Generate a printable PDF of per-employee QR codes.

Reads employees from `data/employees.csv` (CSV columns: employee_id,
first_name, last_name, email) and writes a grid of QR codes to
`output/qr_codes.pdf`. Each QR encodes the employee_id; the caption
underneath shows the employee's name and ID for human reference.
"""
from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Iterable

import qrcode
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

DEFAULT_CSV = "data/employees.csv"
DEFAULT_PDF = "output/qr_codes.pdf"

# Grid layout (Letter = 8.5 x 11 in).
COLUMNS = 3
CELL_W = 2.5 * inch
CELL_H = 3.0 * inch
MARGIN_X = 0.5 * inch
MARGIN_Y = 0.5 * inch
QR_PX = 1.8 * inch  # QR image size inside each cell


class Employee(dict):
    """Just a typed-ish row; we keep it as dict so CSV/Sheets sources match."""


def load_employees_csv(path: str | os.PathLike[str]) -> list[Employee]:
    with open(path, newline="", encoding="utf-8") as f:
        return [Employee(row) for row in csv.DictReader(f)]


def make_qr_png(payload: str) -> bytes:
    """Return a PNG byte-stream of a QR code encoding `payload`."""
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build_pdf(employees: Iterable[Employee], output_path: str | os.PathLike[str]) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    page_w, page_h = LETTER
    cols = COLUMNS
    rows_per_page = int((page_h - 2 * MARGIN_Y) // CELL_H)

    pdf = canvas.Canvas(str(out), pagesize=LETTER)

    for index, emp in enumerate(employees):
        slot = index % (cols * rows_per_page)
        if index and slot == 0:
            pdf.showPage()

        col = slot % cols
        row = slot // cols

        # Cell origin (top-left of the cell).
        x0 = MARGIN_X + col * CELL_W
        y0 = page_h - MARGIN_Y - row * CELL_H

        # QR image — centered horizontally in the cell, near the top.
        qr_x = x0 + (CELL_W - QR_PX) / 2
        qr_y = y0 - QR_PX - 0.1 * inch
        from reportlab.lib.utils import ImageReader

        pdf.drawImage(
            ImageReader(io.BytesIO(make_qr_png(str(emp["employee_id"])))),
            qr_x,
            qr_y,
            width=QR_PX,
            height=QR_PX,
        )

        # Caption — name and id, centered under the QR.
        caption_y = qr_y - 0.25 * inch
        name = f"{emp.get('first_name', '')} {emp.get('last_name', '')}".strip()
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawCentredString(x0 + CELL_W / 2, caption_y, name)
        pdf.setFont("Helvetica", 8)
        pdf.drawCentredString(x0 + CELL_W / 2, caption_y - 0.18 * inch, f"ID: {emp['employee_id']}")

    pdf.save()


def main() -> None:
    csv_path = os.environ.get("EMPLOYEES_CSV", DEFAULT_CSV)
    pdf_path = os.environ.get("QR_PDF_OUTPUT", DEFAULT_PDF)

    employees = load_employees_csv(csv_path)
    if not employees:
        raise SystemExit(f"No employees found in {csv_path}")

    build_pdf(employees, pdf_path)
    print(f"Wrote {len(employees)} QR codes to {pdf_path}")


if __name__ == "__main__":
    main()
