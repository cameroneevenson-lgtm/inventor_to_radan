from __future__ import annotations

import csv
import os
import shutil

from bom_reader import normalize_text


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def seed_csv(src: str, dst: str) -> None:
    """Populate a missing config CSV from the copy shipped with the package.

    Only bites on a pip install, where the rule tables cannot live in
    site-packages: without this the operator would open the tool to four
    header-only files instead of the shop's catalog. A checkout seeds itself
    (src is dst) and is skipped.
    """
    if os.path.abspath(src) == os.path.abspath(dst):
        return
    if not os.path.exists(src):
        return
    try:
        # A zero-byte table counts as absent, not as present-and-empty. Every
        # legitimate one has at least a header row, so 0 bytes means an
        # interrupted write or a truncated copy - and left in place it would
        # read as "no rules at all" and make every description look new.
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            return
    except OSError:
        return
    shutil.copyfile(src, dst)


def back_up_tables(data_dir: str, backup_dir: str, names) -> None:
    """Copy the live tables aside, so losing them costs one run at most.

    Runs at startup, before anything this session can change, so the backup is
    always the last known-good state rather than a mirror of whatever just
    happened. Empty files are skipped: a truncated table must not be allowed to
    overwrite a good backup with nothing.

    Best-effort throughout - a read-only share or a locked file means no
    backup, never a failed run.
    """
    if not backup_dir:
        return
    try:
        os.makedirs(backup_dir, exist_ok=True)
    except OSError:
        return
    for name in names:
        source = os.path.join(data_dir, name)
        try:
            if os.path.getsize(source) <= 0:
                continue
            shutil.copyfile(source, os.path.join(backup_dir, name))
        except OSError:
            continue


def ensure_csv(path: str, header: list[str]) -> None:
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)


def load_set(path: str, col: str) -> set[str]:
    s: set[str] = set()
    if not os.path.exists(path):
        return s
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = normalize_text(r.get(col, ""))
            if v:
                s.add(v)
    return s


def append_unique(path: str, header: list[str], row: list[str]) -> None:
    """Append row if key (first column) isn't already present. Reads disk each time."""
    key = normalize_text(row[0]) if row else ""
    if not key:
        return
    if key in load_set(path, header[0]):
        return
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


def load_rules(path: str) -> dict[str, dict]:
    rules: dict[str, dict] = {}
    if not os.path.exists(path):
        return rules
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = normalize_text(r.get("Description", ""))
            if d:
                rules[d] = r
    return rules


def append_rule(path: str, desc: str, mat: str, thk: str, strat: str) -> None:
    append_unique(path, ["Description", "Material", "Thickness", "Strategy"], [desc, mat, thk, strat])
