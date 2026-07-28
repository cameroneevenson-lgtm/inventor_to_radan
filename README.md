# Inventor to Radan

> Disaster recovery: see [docs/RECOVERY.md](docs/RECOVERY.md) before processing production BOM exports.

Convert an Inventor BOM (`.csv` or `.xlsx`) into a Radan import CSV, with DXF accountability checks and a text report.

## What this tool does

- Reads BOM data from CSV or Excel (`.xlsx`).
- Detects key BOM columns (Part, Description, Quantity).
- Checks whether each `PartNumber.dxf` exists in the BOM folder.
- Prompts for missing DXF classification:
  - Non-laser (stores first token in `nonlaser_tokens.csv`)
  - Expected laser but missing DXF (collects a complete RADAN rule)
- Prompts for missing RADAN rules for descriptions that have DXFs or were classified as expected laser.
- Generates:
  - Radan output CSV (`*_Radan.csv`)
  - Audit report (`*_report.txt`)
- After generating, opens a mandatory Report Review dialog. Choosing "Discard" deletes the just-written `*_Radan.csv` and `*_report.txt`; the run is not considered complete until the operator accepts or discards.
- Parts listed in `ftq_parts.csv` have their output `MATERIAL` forced to `Aluminum 3003 CHK FTQ` regardless of the matched description rule.

## Project files

- `inventor_to_radan.py` - main application logic (PySide6)
- `config.py` - paths and constants
- `bom_reader.py` - BOM column detection and value coercion
- `rule_store.py` - description-rule CSV load/save
- `report_writer.py` - audit report generation
- `inline_runner.py` - headless/programmatic entry point (see "Programmatic use" below)
- `dialogs/` - `missing_dxf_dialog.py`, `radan_rule_dialog.py`, `report_review_dialog.py`
- `inventor_to_radan.bat` - launcher script
- `description_rules.csv` - per-description Radan rule table
- `ftq_parts.csv` - FTQ part numbers whose material is forced to `Aluminum 3003 CHK FTQ`
- `nonlaser_tokens.csv` - non-laser family tokens

## Programmatic use

`inline_runner.run_inline()` and `convert_bom_to_radan_csv()` (`inventor_to_radan.py`) provide a headless conversion path with no dialogs, used by the sibling app `truck_nest_explorer` (`services.py` `run_inventor_to_radan_inline`, called with `allow_prompts=False, show_summary=False`). Passing `allow_prompts=False` skips the missing-DXF/missing-rule prompts and the Report Review gate; callers get `InventorToRadanNeedsUi`, `InventorToRadanCancelled`, or `InventorToRadanReportRejected` raised instead.

## Requirements

- Windows
- Python 3.10+ (recommended)
- Packages:
  - `pandas`
  - `openpyxl` for `.xlsx` BOM files
  - `pyside6`

Install dependencies:

```powershell
python -m pip install pandas openpyxl pyside6
```

## Run

### Option 1: Batch launcher (recommended)

1. Ensure `inventor_to_radan.bat` points to a valid Python at:
   - `C:\Tools\.venv\Scripts\python.exe`
2. Drag a BOM file (`.csv` or `.xlsx`) onto `inventor_to_radan.bat`.

### Option 2: Direct Python

```powershell
python inventor_to_radan.py "W:\path\to\BOM.csv"
```

You can also pass an Excel BOM:

```powershell
python inventor_to_radan.py "W:\path\to\BOM.xlsx"
```

## Output

Outputs are written to the same folder as the BOM input:

- `<BOM_NAME>_Radan.csv`
- `<BOM_NAME>_report.txt`

The Radan CSV has **no header row**; columns are written in this fixed order:

- `FILE, QTY, MATERIAL, THICKNESS, UNIT, STRATEGY`

## Notes

- The app creates missing local CSV config files automatically.
- Quantity values must be numeric; invalid/blank values are treated as `0`.
- Rows are exported only when:
  - DXF exists,
  - quantity > 0,
  - a description rule exists.
- Production Inventor BOMs do not provide a Material column; output material and strategy are resolved from `description_rules.csv` by Description. Its `Description` column is also the single list of known laser descriptions.
- Set `PAUSE_ON_START=1` to pause for a keypress before running (debugging aid).
