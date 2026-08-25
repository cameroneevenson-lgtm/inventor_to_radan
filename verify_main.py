"""Frozen entry point for the verification-only build.

PyInstaller freezes one script and a shortcut passes no arguments, so the
verify build needs its own entry rather than a `--verify` flag nobody can
type. It checks the BOM and writes the report; the RADAN import CSV stays the
laser programmer's artifact and is not produced here.
"""
from __future__ import annotations

import os
import sys

import bom_converter
import config
from dialogs.bom_picker_dialog import pick_bom

from PySide6.QtWidgets import QApplication, QMessageBox


def verify_one(bom_path: str) -> str:
    """Run the checks on one BOM and return what to show above the picker."""
    name = os.path.basename(bom_path)
    try:
        bom_converter.convert_bom_to_radan_csv(
            bom_path, allow_prompts=True, show_summary=True, write_csv=False
        )
    except bom_converter.InventorToRadanCancelled:
        return f"{name}: cancelled."
    except bom_converter.InventorToRadanReportRejected:
        return f"{name}: report discarded, nothing kept."
    except Exception as exc:
        QMessageBox.critical(None, "Error", f"{type(exc).__name__}: {exc}")
        return f"{name}: {type(exc).__name__}."
    return f"{name}: checked. Report written next to the BOM."


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    app = QApplication(sys.argv)  # noqa: F841 - must outlive the dialogs below
    bom_converter.ensure_config_csvs()

    # A BOM dropped on the exe runs once and exits; launched from a shortcut it
    # asks, and keeps asking, because fix-and-recheck is the normal loop.
    if args:
        verify_one(args[0])
        return 0

    message = ""
    while True:
        bom_path = pick_bom(config.DATA_DIR, message)
        if not bom_path:
            return 0
        message = verify_one(bom_path)


if __name__ == "__main__":
    sys.exit(main())
