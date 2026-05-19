from __future__ import annotations

import csv
import os

from bom_reader import normalize_text


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


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
