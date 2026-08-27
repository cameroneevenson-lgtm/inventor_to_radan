"""Frozen entry point for the verification-only build.

PyInstaller freezes one script and a shortcut passes no arguments, so the
verify build needs its own entry rather than a `--verify` flag nobody can
type. It checks the BOM and writes the report; the RADAN import CSV stays the
laser programmer's artifact and is not produced here.
"""
from __future__ import annotations

import os
import sys
import traceback


def crash_log_path() -> str:
    """Beside the exe if that is writable, otherwise the temp directory.

    A double-clicked exe that dies before its first window takes the console
    with it, so the failure is invisible - "nothing happens" is all the
    operator can report. This is the only record that survives that.
    """
    if getattr(sys, "frozen", False):
        beside = os.path.dirname(os.path.abspath(sys.executable))
        try:
            probe = os.path.join(beside, ".itr_write_probe")
            with open(probe, "w", encoding="utf-8") as handle:
                handle.write("")
            os.remove(probe)
            return os.path.join(beside, "BOM Verify - error.log")
        except OSError:
            pass
    import tempfile

    return os.path.join(tempfile.gettempdir(), "BOM Verify - error.log")


def record_crash(exc: BaseException) -> str:
    path = crash_log_path()
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("".join(traceback.format_exception(exc)))
            handle.write(f"\nfrozen: {getattr(sys, 'frozen', False)}\n")
            handle.write(f"executable: {sys.executable}\n")
    except OSError:
        return ""
    return path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    from tkinter import messagebox

    import bom_converter
    import config
    from dialogs.bom_picker_dialog import pick_bom
    from dialogs.tk_base import ensure_root

    ensure_root()
    bom_converter.ensure_config_csvs()

    def verify_one(bom_path: str) -> str:
        name = os.path.basename(bom_path)
        try:
            bom_converter.convert_bom_to_radan_csv(
                bom_path,
                allow_prompts=True,
                show_summary=True,
                write_csv=False,
                collect_radan_rules=False,
            )
        except bom_converter.InventorToRadanCancelled:
            return f"{name}: cancelled."
        except bom_converter.InventorToRadanReportRejected:
            return f"{name}: report discarded, nothing kept."
        except Exception as exc:
            messagebox.showerror("Error", f"{type(exc).__name__}: {exc}")
            return f"{name}: {type(exc).__name__}."
        return f"{name}: checked. Report written next to the BOM."

    # A BOM dropped on the exe runs once and exits; launched from a shortcut it
    # asks, and keeps asking, because fix-and-recheck is the normal loop.
    if args:
        verify_one(args[0])
        return 0

    scan_settings = {
        "root": config.BOM_SEARCH_ROOT,
        "radan_suffix": config.RADAN_OUTPUT_SUFFIX,
        # The rule tables live beside the exe, so an exe on the share puts them
        # inside the search root as four .csv files that are not BOMs.
        "exclude_names": config.CONFIG_CSV_NAMES,
        "max_depth": config.BOM_SEARCH_DEPTH,
        "max_age_days": config.BOM_MAX_AGE_DAYS,
        "limit": config.BOM_SHORTLIST_LIMIT,
    }

    message = ""
    while True:
        bom_path = pick_bom(config.DATA_DIR, scan_settings, message)
        if not bom_path:
            return 0
        message = verify_one(bom_path)


def run() -> int:
    """Startup guard. Everything above this can fail before there is a window
    to show an error in - a broken Tcl/Tk unpack on a share, an unwritable
    data dir - and the operator would see the process vanish with no
    message."""
    try:
        return main()
    except BaseException as exc:  # noqa: BLE001 - last line before silence
        log = record_crash(exc)
        try:
            from tkinter import messagebox

            from dialogs.tk_base import ensure_root

            ensure_root()
            messagebox.showerror(
                "BOM Verify could not start",
                f"{type(exc).__name__}: {exc}" + chr(10) + chr(10) + "Details written to:" + chr(10) + (log or "(could not write a log)"),
            )
        except BaseException:
            print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            print(f"Details: {log}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
