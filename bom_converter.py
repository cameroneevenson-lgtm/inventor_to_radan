import csv
import os
import sys
from dataclasses import dataclass

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

# ============================================================
# Required dependencies
# ============================================================


class MissingDependencyError(ImportError):
    """A package this tool needs is not installed.

    Raised rather than exiting because this module is a library as well as a
    CLI - odd_job_intake imports it to convert a BOM. sys.exit raises
    SystemExit, which is not an Exception, so it slipped straight through
    every caller's error handling and took their process down with it at
    import time, before any of their own code could report anything.
    """


def tell(message: str, *, title: str = "Inventor to RADAN") -> None:
    """Say something to whoever is running this, whatever they are running it as.

    A windowed build has no console: PyInstaller sets sys.stdout and sys.stderr
    to None, and a bare print() then raises. So the frozen app gets a message
    box and the script run keeps its console output.
    """
    if getattr(sys, "frozen", False):
        try:
            from tkinter import messagebox

            from dialogs.tk_base import ensure_root

            ensure_root()
            messagebox.showinfo(title, message)
            return
        except Exception:
            pass
    try:
        print(message)
    except Exception:
        pass


def _missing(package: str, install: str, cause: ImportError):
    """What to do about a missing package, which depends on who is asking.

    Run directly (someone dragged a BOM onto the script), the useful answer is
    the one-line install command and a non-zero exit. Imported as a library,
    the useful answer is an exception the caller can catch and report in its
    own UI.
    """
    message = f"{package} is not installed.\nRun: python -m pip install {install}"
    if __name__ == "__main__":
        tell(f"ERROR: {message}")
        raise SystemExit(1)
    raise MissingDependencyError(message) from cause


from tkinter import messagebox

from bom_reader import (
    BomTable,
    choose_qty_col,
    find_col,
    first_token,
    normalize_text,
    part_family,
    read_bom as _read_bom,
    to_int,
)
from config import (
    CONFIG_CSV_NAMES,
    DATA_DIR,
    FTQ_CSV,
    NONLASER_TOKENS_CSV,
    RADAN_COL_ORDER,
    RADAN_OUTPUT_SUFFIX,
    REPORT_SUFFIX,
    RULES_CSV,
    STOCK_CUT_PARTS_CSV,
    SEED_DIR,
    SUPPORTED_BOM_EXTENSIONS,
)
from dialogs.missing_dxf_dialog import MissingDxfDialog as _MissingDxfDialog
from dialogs.radan_rule_dialog import RadanRuleDialog as _RadanRuleDialog
from dialogs.report_review_dialog import ReportReviewDialog
from dialogs.tk_base import ACCEPTED, ensure_root
from report_writer import write_report
import rule_store

# ============================================================
# Configuration
# ============================================================

# HARD REQUIREMENT: Output column order must not change


@dataclass(frozen=True)
class InventorToRadanResult:
    bom_path: str
    out_path: str | None  # None on a verification-only run
    report_path: str
    added_count: int
    expected_missing_dxfs: tuple[str, ...]
    orphan_dxfs: tuple[str, ...]
    missing_pdfs: tuple[str, ...]
    nonlaser_parts: tuple[str, ...]
    stock_cut_parts: tuple[str, ...]
    # Descriptions a verification run saw for the first time. Empty on the
    # normal path, where the operator is made to supply a rule there and then.
    unresolved_descriptions: tuple[str, ...] = ()


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

def seed_csv(src: str, dst: str) -> None:
    rule_store.seed_csv(src, dst)

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

def read_bom(path: str) -> BomTable:
    return _read_bom(path, supported_extensions=SUPPORTED_BOM_EXTENSIONS)

# ============================================================
# Stepped dialogs (tkinter)
# ============================================================

class MissingDxfDialog(_MissingDxfDialog):
    def __init__(self, items: list[dict], parent=None):
        super().__init__(
            items,
            nonlaser_tokens_csv=NONLASER_TOKENS_CSV,
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

def compute_expected_missing_dxfs(
    rows: list[dict], extra_expected: set[str] | None = None
) -> list[str]:
    """
    For rows with no DXF, expected missing = full Description in column A of
    description_rules.csv AND NOT first token in nonlaser_tokens.csv AND NOT a
    family in stock_cut_parts.csv.
    Returns sorted unique list of "PartNumber.dxf" names.

    `extra_expected` carries descriptions the operator just marked as expected
    laser. Normally answering that writes a rule, which puts the description in
    the table above; a verification run does not write rules, and without this
    the answer would vanish from the very section it belongs in.
    """
    expected_desc = set(load_rules()) | set(extra_expected or ())
    nonlaser_tokens = {t.lower() for t in load_set(NONLASER_TOKENS_CSV, "Token")}
    stock_cut_families = _stock_cut_families()

    missing: list[str] = []
    for r in rows:
        if r["_HasDxf"]:
            continue
        part = r["_Part"]
        desc = r["_Desc"]
        tok = first_token(desc).lower()

        if tok and tok in nonlaser_tokens:
            continue

        if part_family(part).lower() in stock_cut_families:
            continue

        if desc in expected_desc and part:
            missing.append(f"{part}.dxf")

    return sorted(set(missing))

def _stock_cut_families() -> set[str]:
    return {f.lower() for f in load_set(STOCK_CUT_PARTS_CSV, "PartFamily") if f}

def compute_stock_cut_parts(rows: list[dict]) -> list[str]:
    """
    Parts with no DXF whose family is listed in stock_cut_parts.csv - cut to
    length from stock rather than nested, so a per-length DXF is never drawn.
    Keyed on the PART NUMBER family, not the description token: these carry an
    ordinary sheet description shared with real laser parts, so a description
    token would mute far more than the family.
    Returns sorted unique list of PartNumbers.
    """
    stock_cut_families = _stock_cut_families()
    out: list[str] = []
    for r in rows:
        if r["_HasDxf"]:
            continue
        part = r["_Part"]
        if part and part_family(part).lower() in stock_cut_families:
            out.append(part)
    return sorted(set(out))

def compute_nonlaser_parts(rows: list[dict]) -> list[str]:
    """
    Non-laser parts (no DXF) based on FIRST TOKEN match to nonlaser_tokens.csv.
    Returns sorted unique list of PartNumbers.
    """
    nonlaser_tokens = {t.lower() for t in load_set(NONLASER_TOKENS_CSV, "Token")}
    out: list[str] = []
    for r in rows:
        if r["_HasDxf"]:
            continue
        part = r["_Part"]
        tok = first_token(r["_Desc"]).lower()
        if part and tok and tok in nonlaser_tokens:
            out.append(part)
    return sorted(set(out))

def ensure_config_csvs() -> None:
    ensure_dir(DATA_DIR)
    # Seeding is a property of DATA_DIR, not of the path constants above: a
    # caller that points RULES_CSV somewhere of its own wants that file left
    # alone, not backfilled with the shop catalog.
    for name in CONFIG_CSV_NAMES:
        seed_csv(os.path.join(SEED_DIR, name), os.path.join(DATA_DIR, name))
    ensure_csv(RULES_CSV, ["Description", "Material", "Thickness", "Strategy"])
    ensure_csv(FTQ_CSV, ["PartNumber"])
    ensure_csv(NONLASER_TOKENS_CSV, ["Token"])
    ensure_csv(STOCK_CUT_PARTS_CSV, ["PartFamily"])


def prepare_bom_rows(bom_path: str) -> tuple[list[dict], str]:
    base_dir = os.path.dirname(bom_path)

    # ---- Read BOM robustly
    bom = read_bom(bom_path)

    # ---- Identify key columns
    part_col = find_col(bom, ["part number", "part #", "part", "pn"])
    desc_col = find_col(bom, ["description", "desc"])
    qty_col = choose_qty_col(bom)

    # ---- DXF existence (BOM folder)
    def has_dxf(part: str) -> bool:
        if not part:
            return False
        return os.path.exists(os.path.join(base_dir, f"{part}.dxf"))

    # ---- Normalized working rows; downstream reads only these four keys
    rows: list[dict] = []
    for record in bom.records:
        part = normalize_text(record.get(part_col))
        rows.append({
            "_Part": part,
            "_Desc": normalize_text(record.get(desc_col)),
            "_Qty": to_int(record.get(qty_col)),
            "_HasDxf": has_dxf(part),
        })
    return rows, base_dir


def collect_missing_dxf_prompt_items(rows: list[dict]) -> list[dict]:
    prompt_items: list[dict] = []
    # Group missing-DXF rows by description. Iterated in sorted order because
    # that is the order the classify dialog has always shown them in (the
    # pandas groupby this replaced sorted its group keys).
    counts: dict[str, int] = {}
    for r in rows:
        if not r["_HasDxf"]:
            counts[r["_Desc"]] = counts.get(r["_Desc"], 0) + 1

    if counts:
        expected_desc = set(load_rules())
        nonlaser_tokens = load_set(NONLASER_TOKENS_CSV, "Token")
        nonlaser_tokens_l = {t.lower() for t in nonlaser_tokens}

        for desc in sorted(counts):
            count = counts[desc]
            desc = normalize_text(desc)
            if not desc:
                continue

            tok_l = first_token(desc).lower()

            if desc in expected_desc:
                continue
            if tok_l and tok_l in nonlaser_tokens_l:
                continue

            prompt_items.append({
                "desc": desc,
                "token": first_token(desc),
                "count": count,
            })

    seen: set[str] = set()
    prompt_unique: list[dict] = []
    for it in prompt_items:
        if it["desc"] in seen:
            continue
        seen.add(it["desc"])
        prompt_unique.append(it)

    return prompt_unique


def collect_missing_rules(rows: list[dict], rules: dict[str, dict]) -> list[str]:
    laser_descs = sorted({r["_Desc"] for r in rows if r["_HasDxf"]})
    return [d for d in laser_descs if d and d not in rules]


def write_radan_outputs(
    *,
    bom_path: str,
    base_dir: str,
    rows: list[dict],
    rules: dict[str, dict],
    ftq_parts: set[str],
    write_csv: bool = True,
    unresolved_descriptions: tuple[str, ...] = (),
    extra_expected_descs: set[str] | None = None,
) -> InventorToRadanResult:
    export_rows: list[dict] = []
    bom_dxfs: set[str] = set()

    for r in rows:
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

        export_rows.append({
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

    # Aggregate duplicate parts, summing QTY. Emitted sorted by the grouping
    # key - the pandas groupby this replaced sorted its keys, and the output
    # row order is part of what RADAN operators are used to seeing.
    grouped_qty: dict[tuple, int] = {}
    for row in export_rows:
        key = (row["FILE"], row["MATERIAL"], row["THICKNESS"], row["UNIT"], row["STRATEGY"])
        grouped_qty[key] = grouped_qty.get(key, 0) + row["QTY"]

    out_rows = [
        {"FILE": k[0], "QTY": qty, "MATERIAL": k[1], "THICKNESS": k[2], "UNIT": k[3], "STRATEGY": k[4]}
        for k, qty in sorted(grouped_qty.items())
    ]

    if write_csv:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\r\n")
            for row in out_rows:
                writer.writerow([row[col] for col in RADAN_COL_ORDER])
    else:
        # Verification only: the accountability checks and the report still run,
        # but the RADAN import CSV is the laser programmer's artifact and is not
        # this run's to produce.
        out_path = None

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

    expected_missing_dxfs = compute_expected_missing_dxfs(rows, extra_expected_descs)
    nonlaser_parts = compute_nonlaser_parts(rows)
    stock_cut_parts = compute_stock_cut_parts(rows)

    report_path = os.path.join(
        base_dir,
        os.path.splitext(os.path.basename(bom_path))[0] + REPORT_SUFFIX
    )
    write_report(
        report_path=report_path,
        bom_path=bom_path,
        out_path=out_path,
        added_count=len(out_rows),
        expected_missing_dxfs=expected_missing_dxfs,
        orphan_dxfs=orphan_dxfs,
        missing_pdfs=missing_pdfs,
        nonlaser_parts=nonlaser_parts,
        stock_cut_parts=stock_cut_parts,
        unresolved_descriptions=list(unresolved_descriptions),
    )

    return InventorToRadanResult(
        bom_path=bom_path,
        out_path=out_path,
        report_path=report_path,
        added_count=len(out_rows),
        expected_missing_dxfs=tuple(expected_missing_dxfs),
        orphan_dxfs=tuple(sorted(orphan_dxfs)),
        missing_pdfs=tuple(sorted(missing_pdfs)),
        nonlaser_parts=tuple(nonlaser_parts),
        stock_cut_parts=tuple(stock_cut_parts),
        unresolved_descriptions=tuple(unresolved_descriptions),
    )


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
    write_csv: bool = True,
    collect_radan_rules: bool = True,
) -> InventorToRadanResult:
    ensure_config_csvs()
    rows, base_dir = prepare_bom_rows(bom_path)

    # ---- Persistence (disk)
    ftq_parts = load_set(FTQ_CSV, "PartNumber")

    # ============================================================
    # DXF Accountability: classify unknown missing-DXF descriptions
    # ============================================================

    expected_missing_rules: list[str] = []
    prompt_unique = collect_missing_dxf_prompt_items(rows)
    if prompt_unique:
        if not allow_prompts:
            raise InventorToRadanNeedsUi(missing_dxf_items=prompt_unique)
        dlg = MissingDxfDialog(prompt_unique)
        if dlg.exec() != ACCEPTED:
            raise InventorToRadanCancelled()
        expected_missing_rules = dlg.expected_descriptions

    # ============================================================
    # RADAN rules: prompt only for descriptions that have DXFs
    # ============================================================

    rules = load_rules()
    ftq_descs = {r["_Desc"] for r in rows if r["_Part"] in ftq_parts}
    missing_rules = sorted(set(collect_missing_rules(rows, rules)) | set(expected_missing_rules))

    unresolved_descriptions: tuple[str, ...] = ()
    if missing_rules:
        if not collect_radan_rules:
            # Upstream of RADAN. Material, thickness and strategy are the laser
            # programmer's vocabulary, and asking a designer for them gets
            # guesses written into the shop's rule table. The run reports the
            # descriptions instead and leaves the table alone - a rule with
            # blank fields is worse than no rule, because column A of
            # description_rules.csv is what marks a description as known laser.
            unresolved_descriptions = tuple(missing_rules)
        elif not allow_prompts:
            raise InventorToRadanNeedsUi(missing_rules=missing_rules)
        else:
            dlg = RadanRuleDialog(missing_rules, ftq_descs)
            if dlg.exec() != ACCEPTED:
                raise InventorToRadanCancelled()
            rules = load_rules()

    result = write_radan_outputs(
        bom_path=bom_path,
        base_dir=base_dir,
        rows=rows,
        rules=rules,
        ftq_parts=ftq_parts,
        write_csv=write_csv,
        unresolved_descriptions=unresolved_descriptions,
        extra_expected_descs=set(expected_missing_rules),
    )
    if show_summary:
        dialog = ReportReviewDialog(result)
        if dialog.exec() != ACCEPTED:
            failed_deletes = delete_generated_outputs(result)
            if failed_deletes:
                messagebox.showwarning(
                    "Delete Inventor Output",
                    "Some generated files could not be deleted:\n\n" + "\n".join(failed_deletes),
                )
            raise InventorToRadanReportRejected()
    return result


def main(bom_path: str, *, write_csv: bool = True, collect_radan_rules: bool = True) -> int:
    try:
        convert_bom_to_radan_csv(
            bom_path,
            allow_prompts=True,
            show_summary=True,
            write_csv=write_csv,
            collect_radan_rules=collect_radan_rules,
        )
    except (InventorToRadanCancelled, InventorToRadanReportRejected):
        return 2
    return 0

# ============================================================
# Entry point
# ============================================================

def run_cli(argv: list[str] | None = None, *, write_csv: bool = True) -> int:
    """Argument handling and the GUI bootstrap.

    Shared by the script run (the .bat drag-and-drop) and the installed
    `inventor-to-radan` command via `cli.py`, so the two cannot drift apart.
    """
    args = list(sys.argv[1:] if argv is None else argv)

    # --verify checks the BOM and writes only the report. The RADAN import CSV
    # is the laser programmer's artifact; a designer checking their own BOM for
    # missing DXFs and unknown descriptions has no use for it and should not be
    # leaving one behind in the job folder.
    if "--verify" in args:
        args = [a for a in args if a != "--verify"]
        write_csv = False

    # Optional dev pause (set env var PAUSE_ON_START=1)
    if os.environ.get("PAUSE_ON_START") == "1":
        input("Script started. Press Enter to continue...")

    if not args:
        tell("Drag a BOM (.csv or .xlsx) onto this script.")
        return 1

    ensure_root()
    try:
        return main(args[0], write_csv=write_csv)
    except Exception as e:
        messagebox.showerror("Error", f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(run_cli())
