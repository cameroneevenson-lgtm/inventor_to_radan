"""Console-script shim for the installed package.

`pip install` puts an `inventor-to-radan` command on PATH pointing here. The
real work - argument handling and the QApplication bootstrap - stays in
`bom_converter.run_cli`, which the .bat's script run also uses, so the two
entry points cannot drift apart.

Importing `bom_converter` is what can fail on a fresh machine (it imports
pandas and PySide6 at module level and raises MissingDependencyError, an
ImportError, when either is absent), so that import is the part wrapped here.
"""
from __future__ import annotations


def main() -> int:
    try:
        from inventor_to_radan import bom_converter
    except ImportError as exc:
        # No `tell` here: importing bom_converter is what just failed.
        try:
            print(f"ERROR: {exc}")
        except Exception:
            pass
        return 1
    return bom_converter.run_cli()
