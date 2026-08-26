"""Finds recently-touched BOMs on the shared drive, for the picker's shortlist.

Kept out of the dialog so it can be tested without a Qt event loop, and run off
the UI thread: a scan of the LASER share takes ~13 s over the network, which is
longer than the frozen exe's own startup.
"""
from __future__ import annotations

import os


def _is_candidate(name: str, extensions: tuple[str, ...], radan_suffix: str) -> bool:
    lowered = name.lower()
    if lowered.startswith("~$"):
        # Excel's lock file for an open workbook, not something to convert.
        return False
    if lowered.endswith(radan_suffix.lower()):
        # This tool's own output lands beside the BOM it came from. Offering it
        # back as an input is how someone converts a converted file.
        return False
    return lowered.endswith(extensions)


def find_recent_boms(
    root: str,
    *,
    extensions: tuple[str, ...] = (".csv", ".xlsx"),
    radan_suffix: str = "_Radan.csv",
    max_depth: int = 2,
    limit: int = 15,
) -> list[tuple[str, float]]:
    """Newest-first `(path, mtime)` for spreadsheets under `root`.

    Depth-bounded because the share is deep and mostly not BOMs; jobs sit two
    levels down, as in `LASER / For Battleshield Fabrication / F59822 /
    F59822-BOM.xlsx`.
    Returns an empty list rather than raising if the drive is not mapped - the
    picker still works, it just has nothing to suggest.
    """
    found: list[tuple[str, float]] = []

    def walk(path: str, depth: int) -> None:
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if depth < max_depth:
                                walk(entry.path, depth + 1)
                        elif _is_candidate(entry.name, extensions, radan_suffix):
                            found.append((entry.path, entry.stat().st_mtime))
                    except OSError:
                        continue
        except OSError:
            return

    if not root:
        return []
    walk(root, 0)
    found.sort(key=lambda pair: pair[1], reverse=True)
    return found[:limit]
