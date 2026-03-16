# Inventor to Radan (v1.0)

Convert an Inventor BOM (`.csv` or `.xlsx`) into a Radan import CSV, with DXF accountability checks and a text report.

## What this tool does

- Reads BOM data from CSV or Excel (`.xlsx`).
- Detects key BOM columns (Part, Description, Quantity, optional Material).
- Checks whether each `PartNumber.dxf` exists in the BOM folder.
- Prompts for missing DXF classification:
  - Non-laser (stores first token in `nonlaser_tokens.csv`)
  - Expected laser but missing DXF (stores full description)
- Prompts for missing Radan rules for descriptions that do have DXFs.
- Generates:
  - Radan output CSV (`*_Radan.csv`)
  - Audit report (`*_report.txt`)

## Project files

- `inventor_to_radan.py` - main application logic and dialogs (PySide6)
- `inventor_to_radan.bat` - launcher script
- `description_rules.csv` - per-description Radan rule table
- `ftq_parts.csv` - FTQ part numbers
- `nonlaser_tokens.csv` - non-laser family tokens
- `expected_laser_descriptions.csv` - descriptions expected to be laser-cut
- `laser_materials.csv` - known laser materials

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

Radan CSV columns are fixed in this order:

- `FILE, QTY, MATERIAL, THICKNESS, UNIT, STRATEGY`

## Notes

- The app creates missing local CSV config files automatically.
- Quantity values must be numeric; invalid/blank values are treated as `0`.
- Rows are exported only when:
  - DXF exists,
  - quantity > 0,
  - a description rule exists.

## Version

- `v1.0` - stable production version.
