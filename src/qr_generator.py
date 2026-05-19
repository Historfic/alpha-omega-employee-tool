"""Generate a printable PDF of per-employee QR codes.

Reads employees from either `data/employees.csv` or a Google Sheet
(via `SheetsClient`) and writes a grid of QR codes to `output/qr_codes.pdf`.
Each QR encodes the employee_id; the caption underneath shows the employee's
name and ID for human reference.

Input columns expected (header row in either source):
    employee_id, first_name, last_name, email
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import sys
from pathlib import Path
from typing import Iterable, Sequence

import qrcode
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

DEFAULT_CSV = "data/employees.csv"
DEFAULT_PDF = "output/qr_codes.pdf"

log = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BAD_INPUT = 2

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


def load_employees_sheet(
    client, spreadsheet_id: str, gid: int | None = None
) -> list[Employee]:
    """Fetch employees from a Google Sheet via SheetsClient.

    `client` is a `SheetsClient` instance (imported lazily in `main` so the
    CSV path stays usable without Google deps configured).
    """
    if gid is None:
        rows = client.read_sheet(spreadsheet_id)
    else:
        title = client.get_worksheet_title(spreadsheet_id, gid)
        log.debug("resolved gid=%s to worksheet title %r", gid, title)
        rows = client.read_sheet(spreadsheet_id, title)
    return [Employee({k: str(v) for k, v in row.items()}) for row in rows]


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qr_generator",
        description=(
            "Generate a printable PDF of per-employee QR codes. "
            "Reads employees from a CSV (default) or a Google Sheet (--sheet-id)."
        ),
    )
    parser.add_argument(
        "--csv",
        default=os.environ.get("EMPLOYEES_CSV", DEFAULT_CSV),
        help=f"Path to employees CSV (default: {DEFAULT_CSV} or $EMPLOYEES_CSV).",
    )
    parser.add_argument(
        "--sheet-id",
        default=os.environ.get("EMPLOYEE_SHEET_ID"),
        help=(
            "Google Sheet ID (overrides --csv). "
            "Defaults to $EMPLOYEE_SHEET_ID if set."
        ),
    )
    parser.add_argument(
        "--sheet-gid",
        type=int,
        default=int(os.environ["EMPLOYEE_SHEET_GID"])
        if os.environ.get("EMPLOYEE_SHEET_GID")
        else None,
        help=(
            "Worksheet gid within the sheet (from the URL after `#gid=`). "
            "Defaults to $EMPLOYEE_SHEET_GID, or the first worksheet."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        default=os.environ.get("QR_PDF_OUTPUT", DEFAULT_PDF),
        help=f"PDF output path (default: {DEFAULT_PDF} or $QR_PDF_OUTPUT).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # Pick up EMPLOYEE_SHEET_ID etc. before the parser reads its defaults.
    from dotenv import load_dotenv

    load_dotenv()

    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    # PIL/PNG codec is chatty at DEBUG — keep our own debug output readable.
    logging.getLogger("PIL").setLevel(logging.INFO)

    source_label: str
    if args.sheet_id:
        try:
            from src.sheets_client import SheetsAuthError, SheetsClient, SheetsClientError
        except ImportError as exc:
            print(f"error: Google Sheets deps not installed: {exc}", file=sys.stderr)
            return EXIT_ERROR

        source_label = f"sheet {args.sheet_id} (gid={args.sheet_gid})"
        log.debug("loading employees from %s", source_label)
        try:
            client = SheetsClient()
            employees = load_employees_sheet(client, args.sheet_id, args.sheet_gid)
        except SheetsAuthError as exc:
            print(f"error: Google Sheets auth failed: {exc}", file=sys.stderr)
            return EXIT_BAD_INPUT
        except SheetsClientError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_BAD_INPUT
    else:
        source_label = args.csv
        log.debug("loading employees from %s", source_label)
        try:
            employees = load_employees_csv(args.csv)
        except FileNotFoundError:
            print(f"error: employees CSV not found: {args.csv}", file=sys.stderr)
            return EXIT_BAD_INPUT

    if not employees:
        print(f"error: no employees found in {source_label}", file=sys.stderr)
        return EXIT_BAD_INPUT

    log.debug("rendering %d QR codes to %s", len(employees), args.output)
    try:
        build_pdf(employees, args.output)
    except OSError as exc:
        print(f"error: failed to write PDF: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(f"Wrote {len(employees)} QR codes to {args.output}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
