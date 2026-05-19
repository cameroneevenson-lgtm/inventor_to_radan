from __future__ import annotations

import os

import pandas as pd


def normalize_text(val) -> str:
    if pd.isna(val):
        return ""
    return str(val).replace("\u00a0", " ").strip()


def first_token(desc: str) -> str:
    d = normalize_text(desc)
    return d.split()[0] if d else ""


def find_col(df: pd.DataFrame, keys: list[str]) -> str:
    cols = [(c, normalize_text(c).lower()) for c in df.columns]
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

    raise ValueError(f"Missing column: {keys}. Available columns: {list(df.columns)}")


def to_int(val) -> int:
    try:
        v = normalize_text(val)
        if not v:
            return 0
        return int(float(v))
    except Exception:
        return 0


def choose_qty_col(df: pd.DataFrame) -> str:
    """
    Choose the best Qty/Quantity column by content (most numeric).
    Prevents silent 'qty=0' when a similarly-named non-numeric column is selected.
    """
    candidates: list[str] = []
    for c in df.columns:
        n = normalize_text(c).lower()
        if any(k in n for k in ["qty", "quantity", "q'ty", "q ty"]):
            candidates.append(c)
    if not candidates:
        candidates = list(df.columns)

    def numeric_rate(col: str) -> float:
        s = df[col].apply(normalize_text)
        ok = 0
        total = 0
        for v in s.tolist():
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


def _trim_raw_bom(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if raw.shape[0] == 0 or raw.shape[1] == 0:
        raise ValueError("BOM appears empty after removing blank rows/columns.")
    return raw


def _detect_header_row(raw: pd.DataFrame) -> tuple[int | None, int]:
    header_keywords = ["part", "description", "desc", "qty", "quantity", "material"]
    best_row = None
    best_score = -1

    for i in range(min(50, len(raw))):
        row_vals = [normalize_text(v).lower() for v in raw.iloc[i].tolist()]
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


def _finalize_bom_frame(raw: pd.DataFrame, source_label: str) -> pd.DataFrame:
    raw = _trim_raw_bom(raw)
    best_row, best_score = _detect_header_row(raw)

    if best_row is None or best_score < 2:
        preview = raw.head(10).to_string(index=False, header=False)
        raise ValueError(
            f"Could not confidently locate the header row in {source_label}.\n"
            "Expected columns like Part/Description/Qty.\n\n"
            f"Top of file preview:\n{preview}"
        )

    header = [normalize_text(v) for v in raw.iloc[best_row].tolist()]
    df = raw.iloc[best_row + 1:].copy()
    df.columns = header

    df = df.loc[:, [c for c in df.columns if normalize_text(c) != ""]]
    df = df.dropna(axis=0, how="all")
    return df


def read_bom(path: str, *, supported_extensions: set[str]) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()

    if ext == ".csv":
        raw = pd.read_csv(path, header=None, engine="python")
        return _finalize_bom_frame(raw, os.path.basename(path))

    if ext == ".xlsx":
        try:
            sheets = pd.read_excel(path, header=None, sheet_name=None, engine="openpyxl")
        except ImportError as exc:
            raise RuntimeError(
                "Reading .xlsx BOMs requires openpyxl.\n"
                "Run: python -m pip install openpyxl"
            ) from exc

        best_candidate = None

        for sheet_name, raw in sheets.items():
            try:
                trimmed = _trim_raw_bom(raw)
            except ValueError:
                continue

            best_row, best_score = _detect_header_row(trimmed)
            candidate = {
                "sheet_name": sheet_name,
                "raw": trimmed,
                "best_score": best_score,
            }
            if best_candidate is None or candidate["best_score"] > best_candidate["best_score"]:
                best_candidate = candidate

        if best_candidate is None:
            raise ValueError("Workbook appears empty across all sheets.")

        return _finalize_bom_frame(
            best_candidate["raw"],
            f"{os.path.basename(path)} [{best_candidate['sheet_name']}]",
        )

    supported = ", ".join(sorted(supported_extensions))
    raise ValueError(f"Unsupported BOM type: {ext}. Supported types: {supported}.")
