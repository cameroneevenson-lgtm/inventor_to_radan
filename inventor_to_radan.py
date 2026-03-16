import os
import sys
import csv

# ============================================================
# Optional dependencies
# ============================================================

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas is not installed.\nRun: python -m pip install pandas")
    sys.exit(1)

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication, QDialog, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QLineEdit, QMessageBox, QCheckBox, QWidget, QSpacerItem, QSizePolicy
    )
except ImportError:
    print("ERROR: PySide6 is not installed.\nRun: python -m pip install pyside6")
    sys.exit(1)

# ============================================================
# Configuration
# ============================================================

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

RULES_CSV = os.path.join(TOOLS_DIR, "description_rules.csv")  # Description,Material,Thickness,Strategy
FTQ_CSV = os.path.join(TOOLS_DIR, "ftq_parts.csv")            # PartNumber

# DXF Accountability (trust BOM) — your nuance:
# - Non-laser confirmation uses FIRST TOKEN only (family-level)
# - Expected-laser (missing DXF) uses FULL DESCRIPTION (exact)
NONLASER_TOKENS_CSV = os.path.join(TOOLS_DIR, "nonlaser_tokens.csv")                 # Token
EXPECTED_LASER_DESC_CSV = os.path.join(TOOLS_DIR, "expected_laser_descriptions.csv") # Description
LASER_MATERIALS_CSV = os.path.join(TOOLS_DIR, "laser_materials.csv")                 # Material (learned)

RADAN_OUTPUT_SUFFIX = "_Radan.csv"
REPORT_SUFFIX = "_report.txt"
SUPPORTED_BOM_EXTENSIONS = {".csv", ".xlsx"}

# HARD REQUIREMENT: Output column order must not change
RADAN_COL_ORDER = ["FILE", "QTY", "MATERIAL", "THICKNESS", "UNIT", "STRATEGY"]

# ============================================================
# Disk-first helpers (write immediately; read from disk for checks)
# ============================================================

def normalize_text(val) -> str:
    if pd.isna(val):
        return ""
    return str(val).replace("\u00a0", " ").strip()

def first_token(desc: str) -> str:
    d = normalize_text(desc)
    return d.split()[0] if d else ""

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

def load_rules() -> dict[str, dict]:
    rules: dict[str, dict] = {}
    if not os.path.exists(RULES_CSV):
        return rules
    with open(RULES_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = normalize_text(r.get("Description", ""))
            if d:
                rules[d] = r
    return rules

def append_rule(desc: str, mat: str, thk: str, strat: str) -> None:
    # Enforce "normalize once" on Description key
    append_unique(RULES_CSV, ["Description", "Material", "Thickness", "Strategy"], [desc, mat, thk, strat])

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

# ============================================================
# Robust BOM reading (handles shifted right/down)
# ============================================================

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

def read_bom(path: str) -> pd.DataFrame:
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

    supported = ", ".join(sorted(SUPPORTED_BOM_EXTENSIONS))
    raise ValueError(f"Unsupported BOM type: {ext}. Supported types: {supported}.")

# ============================================================
# PySide6: Stepped dialogs
# ============================================================

def _label(text: str, bold=False, wrap=True) -> QLabel:
    lab = QLabel(text)
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    if wrap:
        lab.setWordWrap(True)
    if bold:
        f = lab.font()
        f.setBold(True)
        lab.setFont(f)
    return lab

class MissingDxfDialog(QDialog):
    """
    Step through UNKNOWN missing-DXF descriptions and force a classification:
      - Non-Laser: store FIRST TOKEN to nonlaser_tokens.csv
      - Expected Laser: store FULL DESCRIPTION to expected_laser_descriptions.csv (+ optionally add material to laser_materials.csv)
    Writes immediately to disk on each click.

    Sanity feature: shows current Non-Laser token list from disk inside the dialog.
    """
    def __init__(self, items: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("DXF Accountability: Missing DXF Classification")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        self.items = items
        self.i = 0

        self.lbl_progress = _label("")
        self.lbl_desc = _label("", bold=True)
        self.lbl_token = _label("")
        self.lbl_mat = _label("")
        self.lbl_count = _label("")

        note = (
            "No DXF exists for this BOM entry.\n\n"
            "• Mark as Non-Laser → stores FIRST TOKEN only (family-level) in nonlaser_tokens.csv\n"
            "• Expected Laser → stores FULL DESCRIPTION (exact) in expected_laser_descriptions.csv\n"
            "   and will be listed as an expected missing DXF in the final report.\n"
        )
        self.lbl_note = _label(note)

        self.chk_add_mat = QCheckBox("Also add this Material to known LASER materials (helps future missing-DXF checks)")
        self.chk_add_mat.setChecked(False)

        # --- Sanity panel: current non-laser token list (from disk)
        self.lbl_nonlaser_title = _label("Current Non-Laser token list (from disk):", bold=True)
        self.lbl_nonlaser_list = _label("", wrap=True)
        self.lbl_nonlaser_list.setMinimumHeight(90)

        self.btn_nonlaser = QPushButton("Mark as Non-Laser")
        self.btn_expected = QPushButton("Expected Laser (DXF missing)")

        self.btn_nonlaser.clicked.connect(self.choose_nonlaser)
        self.btn_expected.clicked.connect(self.choose_expected)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_nonlaser)
        btn_row.addWidget(self.btn_expected)

        lay = QVBoxLayout()
        lay.addWidget(self.lbl_progress)
        lay.addWidget(self.lbl_desc)
        lay.addWidget(self.lbl_token)
        lay.addWidget(self.lbl_mat)
        lay.addWidget(self.lbl_count)
        lay.addSpacing(8)
        lay.addWidget(self.lbl_note)
        lay.addWidget(self.chk_add_mat)
        lay.addSpacing(10)
        lay.addWidget(self.lbl_nonlaser_title)
        lay.addWidget(self.lbl_nonlaser_list)
        lay.addItem(QSpacerItem(10, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))
        lay.addLayout(btn_row)
        self.setLayout(lay)

        self.resize(760, 620)
        self.load_step()

    def _refresh_nonlaser_list(self):
        toks = sorted(load_set(NONLASER_TOKENS_CSV, "Token"))
        if not toks:
            self.lbl_nonlaser_list.setText("(none yet)")
            return
        # Keep it readable: show all if small, else show first N with count
        if len(toks) <= 40:
            text = ", ".join(toks)
        else:
            text = ", ".join(toks[:40]) + f" ... (+{len(toks)-40} more)"
        self.lbl_nonlaser_list.setText(text)

    def load_step(self):
        it = self.items[self.i]
        desc = it["desc"]
        tok = it["token"]
        mat = it.get("material", "")
        cnt = it.get("count", 0)

        self.lbl_progress.setText(f"{self.i+1} of {len(self.items)}")
        self.lbl_desc.setText(f"Description (full):\n{desc}")
        self.lbl_token.setText(f"Non-laser family key (first token): {tok if tok else '(blank)'}")
        self.lbl_mat.setText(f"Material (from BOM): {mat if mat else '(blank)'}")
        self.lbl_count.setText(f"Occurrences (missing DXF): {cnt}")

        known_laser_mats = load_set(LASER_MATERIALS_CSV, "Material")
        if mat and (mat not in known_laser_mats):
            self.chk_add_mat.setEnabled(True)
            self.chk_add_mat.setChecked(True)
        else:
            self.chk_add_mat.setEnabled(False)
            self.chk_add_mat.setChecked(False)

        self._refresh_nonlaser_list()

    def choose_nonlaser(self):
        it = self.items[self.i]
        tok = it["token"]
        if not tok:
            QMessageBox.critical(self, "Missing token", "Cannot classify as non-laser because the first token is blank.")
            return
        append_unique(NONLASER_TOKENS_CSV, ["Token"], [tok])
        self.next_step()

    def choose_expected(self):
        it = self.items[self.i]
        desc = it["desc"]
        mat = it.get("material", "")

        append_unique(EXPECTED_LASER_DESC_CSV, ["Description"], [desc])
        if mat and self.chk_add_mat.isEnabled() and self.chk_add_mat.isChecked():
            append_unique(LASER_MATERIALS_CSV, ["Material"], [mat])
        self.next_step()

    def next_step(self):
        self.i += 1
        if self.i >= len(self.items):
            self.accept()
        else:
            self.load_step()

class RadanRuleDialog(QDialog):
    """
    Step through missing RADAN rules (for descriptions that DO have DXFs).
    Writes immediately to description_rules.csv on each Save.
    """
    def __init__(self, descs: list[str], ftq_descs: set[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Define RADAN Rule (by Description)")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        self.descs = descs
        self.ftq_descs = ftq_descs
        self.i = 0

        self.lbl_progress = _label("")
        self.lbl_desc = _label("", bold=True)

        self.inp_mat = QLineEdit()
        self.inp_thk = QLineEdit()
        self.inp_strat = QLineEdit()

        self.lbl_mat = _label("Material:")
        self.lbl_thk = _label("Thickness:")
        self.lbl_strat = _label("Strategy:")

        form = QVBoxLayout()
        row1 = QHBoxLayout(); row1.addWidget(self.lbl_mat); row1.addWidget(self.inp_mat)
        row2 = QHBoxLayout(); row2.addWidget(self.lbl_thk); row2.addWidget(self.inp_thk)
        row3 = QHBoxLayout(); row3.addWidget(self.lbl_strat); row3.addWidget(self.inp_strat)
        form.addLayout(row1); form.addLayout(row2); form.addLayout(row3)

        self.btn_save = QPushButton("Save & Next")
        self.btn_save.clicked.connect(self.save_next)

        lay = QVBoxLayout()
        lay.addWidget(self.lbl_progress)
        lay.addWidget(self.lbl_desc)
        lay.addSpacing(8)
        lay.addLayout(form)
        lay.addItem(QSpacerItem(10, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))
        lay.addWidget(self.btn_save)
        self.setLayout(lay)

        self.resize(640, 360)
        self.load_step()

    def load_step(self):
        desc = self.descs[self.i]
        self.lbl_progress.setText(f"{self.i+1} of {len(self.descs)}")
        self.lbl_desc.setText(f"Description:\n{desc}")

        self.inp_mat.setText("")
        self.inp_thk.setText("")
        self.inp_strat.setText("")

        if desc in self.ftq_descs:
            self.inp_mat.setText("Aluminum 3003 CHK FTQ")
            self.inp_mat.setEnabled(False)
        else:
            self.inp_mat.setEnabled(True)

    def save_next(self):
        desc = self.descs[self.i]
        mat = self.inp_mat.text().strip()
        thk = self.inp_thk.text().strip()
        strat = self.inp_strat.text().strip()

        if not mat or not thk or not strat:
            QMessageBox.critical(self, "Missing data", "Material, Thickness, and Strategy are all required.")
            return

        append_rule(desc, mat, thk, strat)

        self.i += 1
        if self.i >= len(self.descs):
            self.accept()
        else:
            self.load_step()

# ============================================================
# Core logic
# ============================================================

def compute_expected_missing_dxfs(df: pd.DataFrame) -> list[str]:
    """
    Expected missing = (full Description in expected_laser_descriptions.csv OR Material in laser_materials.csv)
    AND NOT (first token in nonlaser_tokens.csv)
    for rows with no DXF.
    Returns sorted unique list of "PartNumber.dxf" names.
    """
    expected_desc = load_set(EXPECTED_LASER_DESC_CSV, "Description")
    nonlaser_tokens = {t.lower() for t in load_set(NONLASER_TOKENS_CSV, "Token")}
    laser_mats = {m.lower() for m in load_set(LASER_MATERIALS_CSV, "Material")}

    missing: list[str] = []
    nodxf = df[df["_HasDxf"] == False]
    for _, r in nodxf.iterrows():
        part = r["_Part"]
        desc = r["_Desc"]
        tok = first_token(desc).lower()
        mat = (r["_Mat"] or "").lower()

        if tok and tok in nonlaser_tokens:
            continue

        is_expected = (desc in expected_desc) or (mat and (mat in laser_mats))
        if is_expected and part:
            missing.append(f"{part}.dxf")

    return sorted(set(missing))

def compute_nonlaser_parts(df: pd.DataFrame) -> list[str]:
    """
    Non-laser parts (no DXF) based on FIRST TOKEN match to nonlaser_tokens.csv.
    Returns sorted unique list of PartNumbers.
    """
    nonlaser_tokens = {t.lower() for t in load_set(NONLASER_TOKENS_CSV, "Token")}
    out: list[str] = []
    nodxf = df[df["_HasDxf"] == False]
    for _, r in nodxf.iterrows():
        part = r["_Part"]
        tok = first_token(r["_Desc"]).lower()
        if part and tok and tok in nonlaser_tokens:
            out.append(part)
    return sorted(set(out))

def write_report(report_path: str,
                 bom_path: str,
                 out_path: str,
                 added_count: int,
                 expected_missing_dxfs: list[str],
                 orphan_dxfs: set[str],
                 missing_pdfs: set[str],
                 nonlaser_parts: list[str]) -> None:
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"BOM: {bom_path}\n")
        f.write(f"Folder: {os.path.dirname(bom_path)}\n")
        f.write(f"RADAN output: {out_path}\n")
        f.write("\n")
        f.write(f"Added to RADAN (rows): {added_count}\n")
        f.write("\n")

        f.write("Expected laser but missing DXF (likely deleted / missing):\n")
        if expected_missing_dxfs:
            for name in expected_missing_dxfs:
                f.write(f"  {name}\n")
        else:
            f.write("  (none)\n")
        f.write("\n")

        f.write("Orphan DXFs (in folder but not referenced by BOM):\n")
        if orphan_dxfs:
            for name in sorted(orphan_dxfs):
                f.write(f"  {name}\n")
        else:
            f.write("  (none)\n")
        f.write("\n")

        f.write("DXFs missing PDFs:\n")
        if missing_pdfs:
            for base_name in sorted(missing_pdfs):
                f.write(f"  {base_name}.dxf (missing {base_name}.pdf)\n")
        else:
            f.write("  (none)\n")
        f.write("\n")

        f.write("Non-laser parts (no DXF; token-classified):\n")
        if nonlaser_parts:
            for p in nonlaser_parts:
                f.write(f"  {p}\n")
        else:
            f.write("  (none)\n")
        f.write("\n")

def main(bom_path: str) -> int:
    ensure_dir(TOOLS_DIR)
    ensure_csv(RULES_CSV, ["Description", "Material", "Thickness", "Strategy"])
    ensure_csv(FTQ_CSV, ["PartNumber"])
    ensure_csv(NONLASER_TOKENS_CSV, ["Token"])
    ensure_csv(EXPECTED_LASER_DESC_CSV, ["Description"])
    ensure_csv(LASER_MATERIALS_CSV, ["Material"])

    base_dir = os.path.dirname(bom_path)

    # ---- Read BOM robustly
    df = read_bom(bom_path)

    # ---- Identify key columns
    part_col = find_col(df, ["part number", "part #", "part", "pn"])
    desc_col = find_col(df, ["description", "desc"])
    qty_col = choose_qty_col(df)

    try:
        mat_col = find_col(df, ["material"])
    except Exception:
        mat_col = None

    # ---- Normalize fields
    df["_Part"] = df[part_col].apply(normalize_text)
    df["_Desc"] = df[desc_col].apply(normalize_text)
    df["_Qty"]  = df[qty_col].apply(to_int)
    df["_Mat"]  = df[mat_col].apply(normalize_text) if mat_col else ""

    # ---- DXF existence (BOM folder)
    def has_dxf(part: str) -> bool:
        if not part:
            return False
        return os.path.exists(os.path.join(base_dir, f"{part}.dxf"))

    df["_HasDxf"] = df["_Part"].apply(has_dxf)

    # ---- Persistence (disk)
    ftq_parts = load_set(FTQ_CSV, "PartNumber")

    # ---- Learn laser materials from DXF-present rows (trust BOM)
    if mat_col:
        for m, hd in zip(df["_Mat"].tolist(), df["_HasDxf"].tolist()):
            if hd and m:
                append_unique(LASER_MATERIALS_CSV, ["Material"], [m])

    # ============================================================
    # DXF Accountability: classify unknown missing-DXF descriptions
    # ============================================================

    missing_df = df[df["_HasDxf"] == False].copy()
    prompt_items: list[dict] = []

    if len(missing_df) > 0:
        grouped = missing_df.groupby("_Desc", dropna=False)

        expected_desc = load_set(EXPECTED_LASER_DESC_CSV, "Description")
        nonlaser_tokens = load_set(NONLASER_TOKENS_CSV, "Token")
        laser_mats = load_set(LASER_MATERIALS_CSV, "Material")
        nonlaser_tokens_l = {t.lower() for t in nonlaser_tokens}
        laser_mats_l = {m.lower() for m in laser_mats}

        for desc, g in grouped:
            desc = normalize_text(desc)
            if not desc:
                continue

            tok_l = first_token(desc).lower()
            mats = {normalize_text(m) for m in g["_Mat"].tolist() if normalize_text(m)}

            if desc in expected_desc:
                continue
            if tok_l and tok_l in nonlaser_tokens_l:
                continue
            if mats and any(m.lower() in laser_mats_l for m in mats):
                continue

            sample_mat = sorted(mats)[0] if mats else ""
            prompt_items.append({
                "desc": desc,
                "token": first_token(desc),
                "material": sample_mat,
                "count": int(len(g)),
            })

    seen: set[str] = set()
    prompt_unique: list[dict] = []
    for it in prompt_items:
        if it["desc"] in seen:
            continue
        seen.add(it["desc"])
        prompt_unique.append(it)

    if prompt_unique:
        dlg = MissingDxfDialog(prompt_unique)
        if dlg.exec() != QDialog.Accepted:
            return 2

    # ============================================================
    # RADAN rules: prompt only for descriptions that have DXFs
    # ============================================================

    rules = load_rules()
    ftq_descs = set(df.loc[df["_Part"].isin(ftq_parts), "_Desc"].tolist())

    laser_descs = sorted(set(df.loc[df["_HasDxf"] == True, "_Desc"].tolist()))
    rules = load_rules()
    missing_rules = [d for d in laser_descs if d and d not in rules]

    if missing_rules:
        dlg = RadanRuleDialog(missing_rules, ftq_descs)
        if dlg.exec() != QDialog.Accepted:
            return 2
        rules = load_rules()

    # ============================================================
    # Generate RADAN output: BOM row + DXF exists + qty > 0
    # ============================================================

    rows: list[dict] = []
    bom_dxfs: set[str] = set()

    for _, r in df.iterrows():
        part = r["_Part"]
        desc = r["_Desc"]

        if part:
            bom_dxfs.add(f"{part}.dxf".lower())

        if not r["_HasDxf"]:
            continue
        if not desc or desc not in rules:
            continue

        qty = int(r["_Qty"])
        if qty <= 0:
            continue

        rule = rules[desc]
        material_out = "Aluminum 3003 CHK FTQ" if part in ftq_parts else rule.get("Material", "")

        rows.append({
            "FILE": os.path.join(base_dir, f"{part}.dxf"),
            "QTY": qty,
            "MATERIAL": material_out,
            "THICKNESS": rule.get("Thickness", ""),
            "UNIT": "in",
            "STRATEGY": rule.get("Strategy", ""),
        })

    out_path = os.path.join(
        base_dir,
        os.path.splitext(os.path.basename(bom_path))[0] + RADAN_OUTPUT_SUFFIX
    )

    out_df = pd.DataFrame(rows)

    # Optional: aggregate duplicates, BUT KEEP COLUMN ORDER FIXED
    if not out_df.empty:
        out_df = out_df.groupby(
            ["FILE", "MATERIAL", "THICKNESS", "UNIT", "STRATEGY"],
            as_index=False
        )["QTY"].sum()

        # Force required output order (groupby can reorder)
        out_df = out_df.reindex(columns=RADAN_COL_ORDER)
    else:
        # Still write a header-only CSV in the correct order
        out_df = pd.DataFrame(columns=RADAN_COL_ORDER)

    out_df.to_csv(out_path, index=False, header=False, columns=RADAN_COL_ORDER)

    # ============================================================
    # Folder integrity + report
    # ============================================================

    actual_dxf_files = [f for f in os.listdir(base_dir) if f.lower().endswith(".dxf")]
    actual_dxfs = {f.lower() for f in actual_dxf_files}
    orphan_dxfs = actual_dxfs - bom_dxfs

    missing_pdfs = {
        os.path.splitext(f)[0]
        for f in actual_dxf_files
        if not os.path.exists(os.path.join(base_dir, os.path.splitext(f)[0] + ".pdf"))
    }

    expected_missing_dxfs = compute_expected_missing_dxfs(df)
    nonlaser_parts = compute_nonlaser_parts(df)

    report_path = os.path.join(
        base_dir,
        os.path.splitext(os.path.basename(bom_path))[0] + REPORT_SUFFIX
    )
    write_report(
        report_path=report_path,
        bom_path=bom_path,
        out_path=out_path,
        added_count=len(out_df),
        expected_missing_dxfs=expected_missing_dxfs,
        orphan_dxfs=orphan_dxfs,
        missing_pdfs=missing_pdfs,
        nonlaser_parts=nonlaser_parts,
    )

    # Final summary with previews
    msg_lines = [
        f"Added {len(out_df)} rows to RADAN output:",
        out_path,
        "",
        "Wrote report:",
        report_path,
    ]

    if expected_missing_dxfs:
        preview = expected_missing_dxfs[:20]
        more = len(expected_missing_dxfs) - len(preview)
        msg_lines += ["", "Expected DXFs missing (showing up to 20):"]
        msg_lines += preview
        if more > 0:
            msg_lines += [f"... (+{more} more)"]
    else:
        msg_lines += ["", "Expected DXFs missing: (none)"]

    if orphan_dxfs:
        msg_lines += ["", f"Orphan DXFs (in folder, not in BOM): {len(orphan_dxfs)} (see report)"]
    else:
        msg_lines += ["", "Orphan DXFs: (none)"]

    if missing_pdfs:
        msg_lines += [f"DXFs missing PDFs: {len(missing_pdfs)} (see report)"]
    else:
        msg_lines += ["DXFs missing PDFs: (none)"]

    if nonlaser_parts:
        msg_lines += ["", f"Non-laser parts (no DXF): {len(nonlaser_parts)} (see report)"]
    else:
        msg_lines += ["", "Non-laser parts (no DXF): (none)"]

    QMessageBox.information(None, "Done", "\n".join(msg_lines))
    return 0

# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    # Optional dev pause (set env var PAUSE_ON_START=1)
    if os.environ.get("PAUSE_ON_START") == "1":
        input("Script started. Press Enter to continue...")

    if len(sys.argv) < 2:
        print("Drag a BOM (.csv or .xlsx) onto this script.")
        sys.exit(1)

    app = QApplication(sys.argv)
    try:
        rc = main(sys.argv[1])
    except Exception as e:
        QMessageBox.critical(None, "Error", f"{type(e).__name__}: {e}")
        rc = 1
    sys.exit(rc)


