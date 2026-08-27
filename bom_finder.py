"""Finds recently-touched BOMs on the shared drive, for the picker's shortlist.

Kept out of the dialog so it can be tested without a Qt event loop, and run off
the UI thread: a scan of the LASER share takes ~13 s over the network, which is
longer than the frozen exe's own startup.
"""
from __future__ import annotations

import os
import time


def _is_candidate(
    name: str,
    extensions: tuple[str, ...],
    radan_suffix: str,
    exclude_names: tuple[str, ...],
) -> bool:
    lowered = name.lower()
    if lowered.startswith("~$"):
        # Excel's lock file for an open workbook, not something to convert.
        return False
    if lowered.endswith(radan_suffix.lower()):
        # This tool's own output lands beside the BOM it came from. Offering it
        # back as an input is how someone converts a converted file.
        return False
    if lowered in {n.lower() for n in exclude_names}:
        # The app's own rule tables. They sit beside the exe, so putting the exe
        # on the share puts them inside the search root, where they are four
        # .csv files that are emphatically not BOMs.
        return False
    return lowered.endswith(extensions)


def find_recent_boms(
    root: str,
    *,
    extensions: tuple[str, ...] = (".csv", ".xlsx"),
    radan_suffix: str = "_Radan.csv",
    exclude_names: tuple[str, ...] = (),
    max_depth: int = 2,
    max_age_days: float | None = None,
    time_budget: float | None = None,
    limit: int = 15,
    on_hit=None,
) -> list[tuple[str, float]]:
    """Newest-first `(path, mtime)` for spreadsheets under `root`.

    Depth-bounded because the share is deep and mostly not BOMs. The bound has
    to clear the kit packs, not just job folders: under the fabrication root a
    whole-job BOM is at depth 1, a pack BOM at depth 2, and anything under
    PUMP PACK at depth 3.

    `max_age_days` is what makes the list "recent" - roughly 800 spreadsheets
    live under that root and only a couple of dozen are current work.

    `on_hit(path, mtime)` is called for each match as it is found, so the
    picker can fill its list during the walk rather than after it.

    The walk stops at whichever comes first: `limit` results, or `time_budget`
    seconds. Folders are visited newest-first, so what either one drops is the
    oldest end of the search - the full walk is ~25 s over the network and
    every current BOM turns up in the first second or two of it.

    Because that ordering is a heuristic (a folder's own timestamp, not its
    contents'), stopping at `limit` returns the first N found rather than a
    guaranteed newest N. They are still sorted by date on the way out.

    Returns an empty list rather than raising if the drive is not mapped - the
    picker still works, it just has nothing to suggest.
    """
    found: list[tuple[str, float]] = []
    cutoff = None if max_age_days is None else time.time() - max_age_days * 86400
    deadline = None if time_budget is None else time.monotonic() + time_budget

    def should_stop() -> bool:
        if limit and len(found) >= limit:
            return True
        return deadline is not None and time.monotonic() >= deadline

    def walk(path: str, depth: int) -> None:
        if should_stop():
            return
        subdirs: list[tuple[float, str]] = []
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if depth < max_depth:
                                subdirs.append((entry.stat().st_mtime, entry.path))
                        elif _is_candidate(entry.name, extensions, radan_suffix, exclude_names):
                            mtime = entry.stat().st_mtime
                            if cutoff is not None and mtime < cutoff:
                                continue
                            found.append((entry.path, mtime))
                            if on_hit is not None:
                                on_hit(entry.path, mtime)
                            if should_stop():
                                return
                    except OSError:
                        continue
        except OSError:
            return

        # Newest folders first, so current work surfaces in the first seconds
        # instead of after the whole share has been walked. Directory order on
        # NTFS is roughly creation order, which meant the oldest jobs went
        # first and the list sat empty while they were searched. On Windows
        # scandir already carries the stat data, so the sort costs no extra
        # I/O. It only changes the order results arrive in - everything is
        # still visited, and the finished list is sorted by date regardless.
        for _, child in sorted(subdirs, reverse=True):
            if should_stop():
                return
            walk(child, depth + 1)

    if not root:
        return []
    walk(root, 0)
    found.sort(key=lambda pair: pair[1], reverse=True)
    return found[:limit]
