import os
import sys
from dataclasses import dataclass

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
        QApplication, QDialog, QMessageBox
    )
except ImportError:
    print("ERROR: PySide6 is not installed.\nRun: python -m pip install pyside6")
    sys.exit(1)

from bom_reader import (
    _detect_header_row,
    _finalize_bom_frame,
    _trim_raw_bom,
    choose_qty_col,
    find_col,
    first_token,
    normalize_text,
    read_bom as _read_bom,
    to_int,
)
from config import (
    EXPECTED_LASER_DESC_CSV,
    FTQ_CSV,
    LASER_MATERIALS_CSV,
    NONLASER_TOKENS_CSV,
    RADAN_COL_ORDER,
    RADAN_OUTPUT_SUFFIX,
    REPORT_SUFFIX,
    RULES_CSV,
    SUPPORTED_BOM_EXTENSIONS,
    TOOLS_DIR,
)
from dialogs.missing_dxf_dialog import MissingDxfDialog as _MissingDxfDialog, make_label as _label
from dialogs.radan_rule_dialog import RadanRuleDialog as _RadanRuleDialog
from dialogs.report_review_dialog import ReportReviewDialog
from report_writer import write_report
import rule_store

# ============================================================
# Configuration
# ============================================================

# HARD REQUIREMENT: Output column order must not change


@dataclass(frozen=True)
class InventorToRadanResult:
    bom_path: str
    out_path: str
    report_path: str
    added_count: int
    expected_missing_dxfs: tuple[str, ...]
    orphan_dxfs: tuple[str, ...]
    missing_pdfs: tuple[str, ...]
    nonlaser_parts: tuple[str, ...]


class InventorToRadanNeedsUi(RuntimeError):
    def __init__(
        self,
        *,
        missing_dxf_items: list[dict] | None = None,
        missing_rules: list[str] | None = None,
    ) -> None:
        self.missing_dxf_items = missing_dxf_items or []
        self.missing_rules = missing_rules or []
        parts: list[str] = []
        if self.missing_dxf_items:
            parts.append(f"{len(self.missing_dxf_items)} missing-DXF classification(s)")
        if self.missing_rules:
            parts.append(f"{len(self.missing_rules)} RADAN rule(s)")
        detail = " and ".join(parts) if parts else "user input"
        super().__init__(f"Inventor-to-RADAN needs {detail}.")


class InventorToRadanCancelled(RuntimeError):
    pass


class InventorToRadanReportRejected(RuntimeError):
    pass

# ============================================================
# Disk-first helpers (write immediately; read from disk for checks)
# ============================================================

def ensure_dir(path: str) -> None:
    rule_store.ensure_dir(path)

def ensure_csv(path: str, header: list[str]) -> None:
    rule_store.ensure_csv(path, header)

def load_set(path: str, col: str) -> set[str]:
    return rule_store.load_set(path, col)

def append_unique(path: str, header: list[str], row: list[str]) -> None:
    rule_store.append_unique(path, header, row)

def load_rules() -> dict[str, dict]:
    return rule_store.load_rules(RULES_CSV)

def append_rule(desc: str, mat: str, thk: str, strat: str) -> None:
    rule_store.append_rule(RULES_CSV, desc, mat, thk, strat)

# ============================================================
# Robust BOM reading (handles shifted right/down)
# ============================================================

def read_bom(path: str) -> pd.DataFrame:
    return _read_bom(path, supported_extensions=SUPPORTED_BOM_EXTENSIONS)

# ============================================================
# PySide6: Stepped dialogs
# ============================================================

class MissingDxfDialog(_MissingDxfDialog):
    def __init__(self, items: list[dict], parent=None):
        super().__init__(
            items,
            nonlaser_tokens_csv=NONLASER_TOKENS_CSV,
            expected_laser_desc_csv=EXPECTED_LASER_DESC_CSV,
            laser_materials_csv=LASER_MATERIALS_CSV,
            load_set=load_set,
            append_unique=append_unique,
            parent=parent,
        )


class RadanRuleDialog(_RadanRuleDialog):
    def __init__(self, descs: list[str], ftq_descs: set[str], parent=None):
        super().__init__(
            descs,
            ftq_descs,
            append_rule=append_rule,
            parent=parent,
        )

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

def ensure_config_csvs() -> None:
    ensure_dir(TOOLS_DIR)
    ensure_csv(RULES_CSV, ["Description", "Material", "Thickness", "Strategy"])
    ensure_csv(FTQ_CSV, ["PartNumber"])
    ensure_csv(NONLASER_TOKENS_CSV, ["Token"])
    ensure_csv(EXPECTED_LASER_DESC_CSV, ["Description"])
    ensure_csv(LASER_MATERIALS_CSV, ["Material"])


def prepare_bom_dataframe(bom_path: str) -> tuple[pd.DataFrame, str]:
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
    return df, base_dir


def learn_laser_materials(df: pd.DataFrame) -> None:
    if "_Mat" not in df.columns:
        return
    for m, hd in zip(df["_Mat"].tolist(), df["_HasDxf"].tolist()):
        if hd and m:
            append_unique(LASER_MATERIALS_CSV, ["Material"], [m])


def collect_missing_dxf_prompt_items(df: pd.DataFrame) -> list[dict]:
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

    return prompt_unique


def collect_missing_rules(df: pd.DataFrame, rules: dict[str, dict]) -> list[str]:
    laser_descs = sorted(set(df.loc[df["_HasDxf"] == True, "_Desc"].tolist()))
    return [d for d in laser_descs if d and d not in rules]


def write_radan_outputs(
    *,
    bom_path: str,
    base_dir: str,
    df: pd.DataFrame,
    rules: dict[str, dict],
    ftq_parts: set[str],
) -> InventorToRadanResult:
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

    return InventorToRadanResult(
        bom_path=bom_path,
        out_path=out_path,
        report_path=report_path,
        added_count=len(out_df),
        expected_missing_dxfs=tuple(expected_missing_dxfs),
        orphan_dxfs=tuple(sorted(orphan_dxfs)),
        missing_pdfs=tuple(sorted(missing_pdfs)),
        nonlaser_parts=tuple(nonlaser_parts),
    )


def build_summary_message(result: InventorToRadanResult) -> str:
    msg_lines = [
        f"Added {result.added_count} rows to RADAN output:",
        result.out_path,
        "",
        "Wrote report:",
        result.report_path,
    ]

    if result.expected_missing_dxfs:
        preview = list(result.expected_missing_dxfs[:20])
        more = len(result.expected_missing_dxfs) - len(preview)
        msg_lines += ["", "Expected DXFs missing (showing up to 20):"]
        msg_lines += preview
        if more > 0:
            msg_lines += [f"... (+{more} more)"]
    else:
        msg_lines += ["", "Expected DXFs missing: (none)"]

    if result.orphan_dxfs:
        msg_lines += ["", f"Orphan DXFs (in folder, not in BOM): {len(result.orphan_dxfs)} (see report)"]
    else:
        msg_lines += ["", "Orphan DXFs: (none)"]

    if result.missing_pdfs:
        msg_lines += [f"DXFs missing PDFs: {len(result.missing_pdfs)} (see report)"]
    else:
        msg_lines += ["DXFs missing PDFs: (none)"]

    if result.nonlaser_parts:
        msg_lines += ["", f"Non-laser parts (no DXF): {len(result.nonlaser_parts)} (see report)"]
    else:
        msg_lines += ["", "Non-laser parts (no DXF): (none)"]

    return "\n".join(msg_lines)


def delete_generated_outputs(result: InventorToRadanResult) -> tuple[str, ...]:
    failed: list[str] = []
    for path in (result.out_path, result.report_path):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError as exc:
            failed.append(f"{path}: {exc}")
    return tuple(failed)


def convert_bom_to_radan_csv(
    bom_path: str,
    *,
    allow_prompts: bool = False,
    show_summary: bool = False,
) -> InventorToRadanResult:
    ensure_config_csvs()
    df, base_dir = prepare_bom_dataframe(bom_path)

    # ---- Persistence (disk)
    ftq_parts = load_set(FTQ_CSV, "PartNumber")

    # ---- Learn laser materials from DXF-present rows (trust BOM)
    learn_laser_materials(df)

    # ============================================================
    # DXF Accountability: classify unknown missing-DXF descriptions
    # ============================================================

    prompt_unique = collect_missing_dxf_prompt_items(df)
    if prompt_unique:
        if not allow_prompts:
            raise InventorToRadanNeedsUi(missing_dxf_items=prompt_unique)
        dlg = MissingDxfDialog(prompt_unique)
        if dlg.exec() != QDialog.Accepted:
            raise InventorToRadanCancelled()

    # ============================================================
    # RADAN rules: prompt only for descriptions that have DXFs
    # ============================================================

    rules = load_rules()
    ftq_descs = set(df.loc[df["_Part"].isin(ftq_parts), "_Desc"].tolist())
    missing_rules = collect_missing_rules(df, rules)

    if missing_rules:
        if not allow_prompts:
            raise InventorToRadanNeedsUi(missing_rules=missing_rules)
        dlg = RadanRuleDialog(missing_rules, ftq_descs)
        if dlg.exec() != QDialog.Accepted:
            raise InventorToRadanCancelled()
        rules = load_rules()

    result = write_radan_outputs(
        bom_path=bom_path,
        base_dir=base_dir,
        df=df,
        rules=rules,
        ftq_parts=ftq_parts,
    )
    if show_summary:
        dialog = ReportReviewDialog(result)
        if dialog.exec() != QDialog.Accepted:
            failed_deletes = delete_generated_outputs(result)
            if failed_deletes:
                QMessageBox.warning(
                    None,
                    "Delete Inventor Output",
                    "Some generated files could not be deleted:\n\n" + "\n".join(failed_deletes),
                )
            raise InventorToRadanReportRejected()
    return result


def main(bom_path: str) -> int:
    try:
        convert_bom_to_radan_csv(bom_path, allow_prompts=True, show_summary=True)
    except (InventorToRadanCancelled, InventorToRadanReportRejected):
        return 2
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


