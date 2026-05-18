"""Smoke tests — confirms the package imports cleanly."""
from __future__ import annotations

import src


def test_package_has_version() -> None:
    assert isinstance(src.__version__, str)
    assert src.__version__


def test_modules_importable() -> None:
    from src import qr_generator, sheets_client, time_reporter

    assert qr_generator is not None
    assert sheets_client is not None
    assert time_reporter is not None
