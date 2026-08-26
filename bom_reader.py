from __future__ import annotations

import csv
import io
import os
import re
from dataclasses import dataclass

_LENGTH_SUFFIX = re.compile(r"-\d+(?:\.\d+)?$")


@dataclass
class BomTable:
    """A parsed BOM: header names and one dict per data row.

    The pandas DataFrame this replaced earned its 40 MB of numpy by reading
    the file and grouping rows - nothing here computes. Cells hold whatever
    the file held: str from CSV, native int/float/str/None from openpyxl.
    """
    columns: list[str]
    records: list[dict]


def normalize_text(val) -> str:
    if val is None or (isinstance(val, float) and val != val):  # None or NaN
        return ""
    return str(val).replace(" ", " ").strip()


def first_token(desc: str) -> str:
    d = normalize_text(desc)
    return d.split()[0] if d else ""


def part_family(part: str) -> str:
    """Part number with a trailing cut length stripped: "TIE DOWN-28.75" and
    "TIE DOWN-6" are both the "TIE DOWN" family. A part number with no length
    suffix is its own family."""
    p = normalize_text(part)
    return _LENGTH_SUFFIX.sub("", p).strip()


def find_col(bom: BomTable, keys: list[str]) -> str:
    cols = [(c, normalize_text(c).lower()) for c in bom.columns]
    for k in keys:
        k = k.lower()
        for c, n in cols:
            if k in n:
                return c

    def squish(s: str) -> str:
        return "".join(ch for ch in s.lower() if ch.isalnum())

    keys_sq = [squish(k) for k in keys]
    for c, n in cols:
        n_sq = squish(n)
        for ksq in keys_sq:
            if ksq and ksq in n_sq:
                return c

    raise ValueError(f"Missing column: {keys}. Available columns: {bom.columns}")


def to_int(val) -> int:
    try:
        v = normalize_text(val)
        if not v:
            return 0
        return int(float(v))
    except Exception:
        return 0


def choose_qty_col(bom: BomTable) -> str:
    """
    Choose the best Qty/Quantity column by content (most numeric).
    Prevents silent 'qty=0' when a similarly-named non-numeric column is selected.
    """
    candidates: list[str] = []
    for c in bom.columns:
        n = normalize_text(c).lower()
        if any(k in n for k in ["qty", "quantity", "q'ty", "q ty"]):
            candidates.append(c)
    if not candidates:
        candidates = list(bom.columns)

    def numeric_rate(col: str) -> float:
        ok = 0
        total = 0
        for record in bom.records:
            v = normalize_text(record.get(col))
            if not v:
                continue
            total += 1
            try:
                float(v)
                ok += 1
            except Exception:
                pass
        return ok / max(total, 1)

    scored = [(numeric_rate(c), c) for c in candidates]
    scored.sort(reverse=True, key=lambda x: x[0])
    best_rate, best_col = scored[0]

    if best_rate < 0.60:
        raise ValueError(
            f"Could not confidently identify QTY column. "
            f"Best candidate '{best_col}' numeric-rate={best_rate:.2f}. "
            f"Candidates={candidates}"
        )
    return best_col


# A grid is the raw sheet: list of rows, each a list of cells, padded rectangular.

def _trim_raw_bom(grid: list[list]) -> list[list]:
    grid = [row for row in grid if any(normalize_text(v) for v in row)]
    if not grid:
        raise ValueError("BOM appears empty after removing blank rows/columns.")
    width = max(len(row) for row in grid)
    grid = [row + [None] * (width - len(row)) for row in grid]
    keep = [j for j in range(width) if any(normalize_text(row[j]) for row in grid)]
    if not keep:
        raise ValueError("BOM appears empty after removing blank rows/columns.")
    return [[row[j] for j in keep] for row in grid]


def _detect_header_row(grid: list[list]) -> tuple[int | None, int]:
    header_keywords = ["part", "description", "desc", "qty", "quantity", "material"]
    best_row = None
    best_score = -1

    for i in range(min(50, len(grid))):
        row_vals = [normalize_text(v).lower() for v in grid[i]]
        score = 0
        for kw in header_keywords:
            if any(kw in cell for cell in row_vals):
                score += 1
        if score > best_score:
            best_score = score
            best_row = i
        if score >= 3:
            best_row = i
            break

    return best_row, best_score


def _finalize_bom_table(grid: list[list], source_label: str) -> BomTable:
    grid = _trim_raw_bom(grid)
    best_row, best_score = _detect_header_row(grid)

    if best_row is None or best_score < 2:
        preview = "\n".join(
            " ".join(normalize_text(v) for v in row) for row in grid[:10]
        )
        raise ValueError(
            f"Could not confidently locate the header row in {source_label}.\n"
            "Expected columns like Part/Description/Qty.\n\n"
            f"Top of file preview:\n{preview}"
        )

    header = [normalize_text(v) for v in grid[best_row]]
    keep = [j for j, name in enumerate(header) if name]
    columns = [header[j] for j in keep]

    records: list[dict] = []
    for row in grid[best_row + 1:]:
        if not any(normalize_text(row[j]) for j in keep):
            continue
        records.append({columns[i]: row[j] for i, j in enumerate(keep)})
    return BomTable(columns=columns, records=records)


def _read_csv_grid(path: str) -> list[list]:
    # utf-8-sig eats a BOM marker if present; production exports have also
    # arrived as cp1252, which pandas' python engine used to shrug off.
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with io.open(path, newline="", encoding=encoding) as f:
                return [row for row in csv.reader(f)]
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {os.path.basename(path)} as utf-8 or cp1252.")


def read_bom(path: str, *, supported_extensions: set[str]) -> BomTable:
    ext = os.path.splitext(path)[1].lower()

    if ext == ".csv":
        return _finalize_bom_table(_read_csv_grid(path), os.path.basename(path))

    if ext == ".xlsx":
        try:
            import openpyxl
        except ImportError as exc:
            raise RuntimeError(
                "Reading .xlsx BOMs requires openpyxl.\n"
                "Run: python -m pip install openpyxl"
            ) from exc

        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            best_candidate = None
            for sheet in workbook.worksheets:
                grid = [list(row) for row in sheet.iter_rows(values_only=True)]
                try:
                    trimmed = _trim_raw_bom(grid)
                except ValueError:
                    continue

                best_row, best_score = _detect_header_row(trimmed)
                candidate = {
                    "sheet_name": sheet.title,
                    "grid": trimmed,
                    "best_score": best_score,
                }
                if best_candidate is None or candidate["best_score"] > best_candidate["best_score"]:
                    best_candidate = candidate
        finally:
            workbook.close()

        if best_candidate is None:
            raise ValueError("Workbook appears empty across all sheets.")

        return _finalize_bom_table(
            best_candidate["grid"],
            f"{os.path.basename(path)} [{best_candidate['sheet_name']}]",
        )

    supported = ", ".join(sorted(supported_extensions))
    raise ValueError(f"Unsupported BOM type: {ext}. Supported types: {supported}.")
