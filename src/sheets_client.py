"""Thin wrapper around the Google Sheets API.

Loads credentials from the path in `GOOGLE_APPLICATION_CREDENTIALS` and
exposes helpers used by both `qr_generator` and `time_reporter`.
"""
from __future__ import annotations


def get_client():
    raise NotImplementedError("sheets_client.get_client() not implemented yet")
