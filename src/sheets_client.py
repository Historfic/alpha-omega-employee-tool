"""Thin wrapper around the Google Sheets API via `gspread`.

Loads service-account credentials from the path in
`GOOGLE_APPLICATION_CREDENTIALS` (or an explicit constructor argument) and
exposes read/append helpers used by both `qr_generator` and `time_reporter`.
"""
from __future__ import annotations

import os
import time
from typing import Union

import gspread
from google.auth.exceptions import GoogleAuthError
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

WorksheetRef = Union[int, str]


class SheetsClientError(Exception):
    """Base error for SheetsClient."""


class SheetsAuthError(SheetsClientError):
    """Credentials are missing, malformed, or rejected by Google."""


class SheetsRateLimitError(SheetsClientError):
    """Google returned 429 after the configured retry budget was exhausted."""


class SheetsClient:
    """Minimal wrapper around `gspread` with retry-on-rate-limit.

    Parameters
    ----------
    credentials_path:
        Path to a service-account JSON key. Defaults to the value of the
        `GOOGLE_APPLICATION_CREDENTIALS` environment variable.
    max_retries:
        How many times to retry a single API call on 429 before giving up.
    backoff_base:
        Base seconds for exponential backoff (`backoff_base * 2**attempt`).
    """

    def __init__(
        self,
        credentials_path: str | None = None,
        *,
        max_retries: int = 5,
        backoff_base: float = 1.0,
    ) -> None:
        path = credentials_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not path:
            raise SheetsAuthError(
                "No credentials path provided and GOOGLE_APPLICATION_CREDENTIALS is unset."
            )
        if not os.path.isfile(path):
            raise SheetsAuthError(f"Credentials file not found: {path}")

        try:
            creds = Credentials.from_service_account_file(path, scopes=SCOPES)
            self._client = gspread.authorize(creds)
        except (GoogleAuthError, ValueError, OSError) as exc:
            raise SheetsAuthError(f"Failed to load service-account credentials: {exc}") from exc

        self._max_retries = max_retries
        self._backoff_base = backoff_base

    # ------------------------------------------------------------------ public

    def read_sheet(
        self, spreadsheet_id: str, worksheet: WorksheetRef = 0
    ) -> list[dict[str, object]]:
        """Return every row as a dict keyed by the header row."""
        ws = self._open_worksheet(spreadsheet_id, worksheet)
        return self._call(ws.get_all_records)

    def read_range(
        self, spreadsheet_id: str, range_a1: str, worksheet: WorksheetRef = 0
    ) -> list[list[str]]:
        """Return the cells in an A1-notation range as a list of rows."""
        ws = self._open_worksheet(spreadsheet_id, worksheet)
        return self._call(ws.get, range_a1)

    def append_row(
        self,
        spreadsheet_id: str,
        row: list[object],
        worksheet: WorksheetRef = 0,
        *,
        value_input_option: str = "USER_ENTERED",
    ) -> None:
        """Append a single row to the end of the sheet."""
        ws = self._open_worksheet(spreadsheet_id, worksheet)
        self._call(ws.append_row, row, value_input_option=value_input_option)

    def update_cells(
        self,
        spreadsheet_id: str,
        updates: list[tuple[str, object]],
        worksheet: WorksheetRef = 0,
        *,
        value_input_option: str = "USER_ENTERED",
    ) -> int:
        """Write values into specific cells. `updates` is [(A1 range, value)].

        Sent as one batched request rather than a call per cell: a hundred
        individual writes would burn the per-minute quota and leave the sheet
        half-updated if it tripped partway through.

        Returns the number of cells written.
        """
        if not updates:
            return 0
        ws = self._open_worksheet(spreadsheet_id, worksheet)
        payload = [{"range": rng, "values": [[value]]} for rng, value in updates]
        self._call(ws.batch_update, payload, value_input_option=value_input_option)
        return len(updates)

    def get_worksheet_title(self, spreadsheet_id: str, gid: int) -> str:
        """Resolve a worksheet `gid` (from a sheet URL) to its title.

        Useful when the caller has a Google Sheets URL — the `gid` query param
        identifies the worksheet but the public read/append methods address it
        by title or index.
        """
        sheet = self._open_spreadsheet(spreadsheet_id)
        try:
            return self._call(sheet.get_worksheet_by_id, gid).title
        except WorksheetNotFound as exc:
            raise SheetsClientError(f"Worksheet not found for gid={gid}") from exc

    # ---------------------------------------------------------------- internal

    def _open_spreadsheet(self, spreadsheet_id: str):
        """Open a spreadsheet by ID, translating gspread errors to our types."""
        try:
            return self._call(self._client.open_by_key, spreadsheet_id)
        except SpreadsheetNotFound as exc:
            raise SheetsClientError(f"Spreadsheet not found: {spreadsheet_id}") from exc
        except PermissionError as exc:
            raise SheetsAuthError(
                f"Access denied to spreadsheet {spreadsheet_id} — "
                "is it shared with the service account?"
            ) from exc

    def _open_worksheet(self, spreadsheet_id: str, worksheet: WorksheetRef):
        sheet = self._open_spreadsheet(spreadsheet_id)

        try:
            if isinstance(worksheet, int):
                return self._call(sheet.get_worksheet, worksheet)
            return self._call(sheet.worksheet, worksheet)
        except WorksheetNotFound as exc:
            raise SheetsClientError(f"Worksheet not found: {worksheet!r}") from exc

    def _call(self, func, *args, **kwargs):
        """Invoke a gspread call, retrying on HTTP 429 with exponential backoff."""
        for attempt in range(self._max_retries + 1):
            try:
                return func(*args, **kwargs)
            except APIError as exc:
                status = getattr(exc.response, "status_code", None)
                if status in (401, 403):
                    raise SheetsAuthError(f"Google rejected the request ({status}): {exc}") from exc
                if status == 429 and attempt < self._max_retries:
                    time.sleep(self._backoff_base * (2 ** attempt))
                    continue
                if status == 429:
                    raise SheetsRateLimitError(
                        f"Rate limited after {self._max_retries} retries"
                    ) from exc
                raise


if __name__ == "__main__":
    # Smoke test — exercises all three public methods against a real sheet.
    # Configure via .env: EMPLOYEE_SHEET_ID, EMPLOYEE_SHEET_GID (optional),
    # EMPLOYEE_SHEET_RANGE (optional, e.g. "A1:D4").
    from datetime import datetime

    from dotenv import load_dotenv

    load_dotenv()

    spreadsheet_id = os.environ["EMPLOYEE_SHEET_ID"]
    gid = int(os.environ.get("EMPLOYEE_SHEET_GID", 0))
    range_a1 = os.environ.get("EMPLOYEE_SHEET_RANGE", "A1:D10")

    print(f"Connecting to spreadsheet {spreadsheet_id} ...")
    client = SheetsClient()

    worksheet_title = client.get_worksheet_title(spreadsheet_id, gid)
    print(f"Using worksheet (gid={gid}): {worksheet_title!r}\n")

    print("--- read_sheet() ---")
    rows = client.read_sheet(spreadsheet_id, worksheet_title)
    for row in rows:
        print(row)

    print(f"\n--- read_range({range_a1!r}) ---")
    for row in client.read_range(spreadsheet_id, range_a1, worksheet_title):
        print(row)

    print("\n--- append_row() ---")
    test_row = [
        9999,
        "Smoke",
        "Test",
        f"smoke-{datetime.now().isoformat(timespec='seconds')}@test.com",
    ]
    client.append_row(spreadsheet_id, test_row, worksheet_title)
    print(f"Appended: {test_row}")

    print("\n--- re-read_sheet() to confirm append ---")
    rows = client.read_sheet(spreadsheet_id, worksheet_title)
    print(f"Row count after append: {len(rows)}")
    print(f"Last row:              {rows[-1]}")
