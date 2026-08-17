"""Top-level CLI dispatcher for the alpha-omega employee tool.

Usage:
    python main.py qr [...flags]          # → src.qr_generator.main
    python main.py report [...flags]      # → src.time_reporter.main
    python main.py fill-hours [...flags]  # → src.hours_writer.main
    python main.py <cmd> --help           # subcommand-specific help

Each subcommand is also runnable standalone:
    python -m src.qr_generator [...flags]
    python -m src.time_reporter [...flags]
    python -m src.hours_writer [...flags]
"""
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from src import hours_writer, qr_generator, time_reporter

COMMANDS = {
    "qr": (qr_generator.main, "Generate per-employee QR-code PDF."),
    "report": (time_reporter.main, "Generate weekly time-tracking HTML report."),
    "fill-hours": (
        hours_writer.main,
        "Fill blank Total_hours in the sheet from clock times (dry run unless --apply).",
    ),
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="alpha-omega",
        description="Alpha Omega employee tooling (QR codes + time reports).",
        epilog="Run `<command> --help` for subcommand options.",
    )
    parser.add_argument(
        "command",
        choices=sorted(COMMANDS),
        help="\n".join(f"{name}: {desc}" for name, (_, desc) in COMMANDS.items()),
    )
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to the subcommand.",
    )

    parsed = parser.parse_args(argv)
    func, _ = COMMANDS[parsed.command]
    return func(parsed.args)


if __name__ == "__main__":
    sys.exit(main())
