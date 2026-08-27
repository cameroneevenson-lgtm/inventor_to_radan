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
- Part families listed in `stock_cut_parts.csv` (e.g. `TIE DOWN`) are cut to length from stock, so a missing DXF is expected rather than a warning. One family row covers every length: `TIE DOWN-6`, `TIE DOWN-28.75`, and any length nobody has cut yet.

## Project files

- `bom_converter.py` - main application logic (tkinter)
- `config.py` - paths and constants
- `bom_reader.py` - BOM column detection and value coercion
- `rule_store.py` - description-rule CSV load/save
- `report_writer.py` - audit report generation
- `inline_runner.py` - headless/programmatic entry point (see "Programmatic use" below)
- `cli.py` - the `inventor-to-radan` console script installed by pip; defers to `bom_converter.run_cli`
- `__main__.py` - `python -m inventor_to_radan`, for when the scripts directory is not on `PATH`
- `verify_main.py` - frozen entry point for the verification-only exe (report, no RADAN CSV)
- `build_verify_exe.bat` - PyInstaller build for that exe; creates `.buildvenv` so the bundle carries
  only this app's dependencies
- `BOM Verify.spec` - the build's binary/data filtering and onefile config; committed because
  `--exclude-module` cannot drop individual Qt DLLs
- `dialogs/bom_picker_dialog.py` - the exe's **Select BOM...** front door
- `bom_finder.py` - the picker's shortlist: a depth-bounded scan of the laser share for
  recently touched BOMs
- `dialogs/` - `missing_dxf_dialog.py`, `radan_rule_dialog.py`, `report_review_dialog.py`
- `inventor_to_radan.bat` - launcher script
- `description_rules.csv` - per-description Radan rule table
- `ftq_parts.csv` - FTQ part numbers whose material is forced to `Aluminum 3003 CHK FTQ`
- `nonlaser_tokens.csv` - non-laser family tokens (matched against the Description)
- `stock_cut_parts.csv` - part-number families cut to length from stock (matched against the Part Number)

## Programmatic use

`inline_runner.run_inline()` and `convert_bom_to_radan_csv()` (`bom_converter.py`) provide a headless conversion path with no dialogs, used by the sibling app `truck_nest_explorer` (`services.py` `run_inventor_to_radan_inline`, called with `allow_prompts=False, show_summary=False`). Passing `allow_prompts=False` skips the missing-DXF/missing-rule prompts and the Report Review gate; callers get `InventorToRadanNeedsUi`, `InventorToRadanCancelled`, or `InventorToRadanReportRejected` raised instead.

## Install

### Option A: pip (a machine that just needs to run the tool)

```powershell
python -m pip install "git+https://github.com/cameroneevenson-lgtm/inventor_to_radan.git"
```

Use `python -m pip`, not bare `pip`: it guarantees the package lands in the same
interpreter that `python -m inventor_to_radan` will later use. A bare `pip` on `PATH` can
belong to a different Python than `python` does, which installs successfully and then
cannot be imported.

The quotes and the lack of a space after `git+` both matter: `git+https` is the URL
scheme, so `pip install git+ https://...` splits into two nonsense requirements and
`pip install git https://...` downloads the GitHub HTML page and reports `cannot detect
archive format`. Requires Git for Windows on `PATH`. Without git, install the zip
instead:

```powershell
python -m pip install "https://github.com/cameroneevenson-lgtm/inventor_to_radan/archive/refs/heads/main.zip"
```

Either one installs an `inventor-to-radan` command:

```powershell
inventor-to-radan "W:\path\to\BOM.csv"
```

If that comes back "not recognized", pip put it in the per-user scripts directory
(`%APPDATA%\Python\Python3XX\Scripts`), which is usually not on `PATH` - pip warns about
this rather than failing. Either add that directory to `PATH`, or skip it entirely:

```powershell
python -m inventor_to_radan "W:\path\to\BOM.csv"
```

**A pip install gets its own copy of the rule tables.** `description_rules.csv`,
`ftq_parts.csv`, `nonlaser_tokens.csv` and `stock_cut_parts.csv` cannot live in
site-packages - the next upgrade replaces that directory - so they are seeded into
`%LOCALAPPDATA%\inventor_to_radan` on first run and edited there from then on. Rules
learned on that machine stay on that machine, and rules added to the repo afterwards do
not reach it until it is reinstalled. To keep several machines on one shared table,
point them all at the same directory:

```powershell
setx INVENTOR_TO_RADAN_DATA_DIR "L:\Fabrication\inventor_to_radan"
```

### Option B: clone (the shop's own machines)

A checkout is its own data dir, so the rule tables stay version controlled and are
shared by pulling and committing them - which is how the catalog grows.

```powershell
git clone https://github.com/cameroneevenson-lgtm/inventor_to_radan.git
cd inventor_to_radan
python -m pip install openpyxl
```

### Option C: frozen exe (a machine with no Python at all)

`build_verify_exe.bat` produces `dist\BOM Verify.exe` - a single ~9 MB file, nothing else
to copy. It is the **verification-only** build: it checks a BOM for missing DXFs and
unknown descriptions and writes `*_report.txt` next to it, but does not produce the RADAN
import CSV - that stays the laser programmer's artifact.

Launched from a shortcut it opens a picker with a **Select BOM...** button and stays open
afterwards, because fix-and-recheck is the normal loop. A BOM dropped on the exe is checked
once. Being a onefile build it unpacks to temp on every launch; a splash covers that, since
those seconds are before any of the app's own code runs. There is no console window.

On launch it lists the most recently touched BOMs on the laser share, newest first, so the
usual answer is one double-click away; **Select BOM...** still browses anywhere, and
**Refresh** re-scans. The scan runs off the UI thread and its result is reused for the rest
of the session, so reopening the picker after a run is instant. `*_Radan.csv` files are
excluded - the tool writes those next to the BOM they came from, and offering one back as
an input is how somebody converts a converted file.

The search root defaults to `W:\LASER\For Battleshield Fabrication`, scanned three levels
deep and filtered to the **last 30 days**. The depth matters: a whole-job BOM sits at depth
1 (`P59979\`), a pack BOM at depth 2 (`F59270\EXTERIOR PACK\`), and anything under
`PUMP PACK\` at depth 3 - so a shallower scan shows job BOMs while silently hiding every
canonical kit BOM. Rows are labelled with the folder path relative to the root, because a
kit BOM's own folder is called `PUMP HOUSE` and does not say which truck.

`INVENTOR_TO_RADAN_BOM_ROOT` overrides the root; an empty string turns the shortlist off.
If the drive is not mapped the list is simply empty and the buttons still work. The walk
takes ~20 s over the network, so it runs off the UI thread and reports folders scanned as
it goes.

**It never asks a designer for a RADAN rule.** Material, thickness and strategy are the
laser programmer's vocabulary. When the exe meets a description it has not seen, it asks
only the question the person in front of it can answer - is this laser or not - and lists
anything still unresolved in the report under *New descriptions (laser, but no RADAN rule
yet)* for somebody with that vocabulary to settle. The rule table is not written to, because
a row with blank fields is worse than no row: column A of `description_rules.csv` is what
marks a description as known laser. A "not laser" answer is still saved, as it is a complete
answer on its own.

The four rule CSVs live in a **`data\` folder beside the exe**, not in a per-user folder,
seeded on first run from copies frozen into the bundle by the checkout that built it. So a
fresh copy starts with the shop's catalog as of build time and grows from there, and an exe
put on a share works as one shared installation: everyone running it reads and writes the
same tables.

An older build kept those CSVs loose beside the exe. The first run of a newer build **moves
them into `data\`** rather than seeding a fresh set - on a deployed copy the loose files
are the live tables, not a stale snapshot.

**Updating a deployed copy: send the exe, not the folder.** Once people have been using it,
the CSVs in `data\` are the live tables, holding every classification made since it was
deployed. Copying a freshly built folder over the top replaces them with the build-time
snapshot and throws that away. Replace `BOM Verify.exe` alone and leave `data\` where it
is; it is forward-compatible, and anything genuinely new reseeds only if missing.

If the location is read-only the tool falls back to `%LOCALAPPDATA%\inventor_to_radan`,
because it still has to be able to learn a rule. `INVENTOR_TO_RADAN_DATA_DIR` overrides
both.

If it fails to start it writes `BOM Verify - error.log` next to the exe - that file is the
first thing to read.

**The build uses `.buildvenv\`, not `C:\Tools\.venv`.** The shared venv carries every other
tool's dependencies and PyInstaller bundles what it finds: builds from it were shipping
80 MB of `pyarrow` (required by `streamlit`, not by pandas) plus scipy, matplotlib, PIL and
cryptography - 235 MB of folder for what is now a 9 MB app. The build script creates
`.buildvenv` on first run with only `openpyxl pyinstaller`. Do not point it back at the
shared venv, and do not re-add a `--exclude-module` list to `BOM Verify.spec` to compensate;
the packages are simply not there.

`BOM Verify.spec` additionally drops stdlib pieces nothing here loads: sqlite3, ssl, and
`_hashlib`. That last one is worth knowing about - openpyxl imports `hashlib` to hash
sheet-protection passwords this app never sets, and `_hashlib` is the OpenSSL binding that
pulls in `libcrypto`, which was 5.2 MB of a 10.7 MB exe. Without it `hashlib` falls back to
Python's built-in digests.

## Requirements

- Windows
- Python 3.10+ (recommended)
- Packages (installed for you by Option A):
  - `openpyxl` for `.xlsx` BOM files

  The GUI is tkinter, which ships with Python. pandas and PySide6 were removed: they were
  70 MB of the frozen exe and were doing work the standard library already does.

## Run

### Option 1: Batch launcher (a clone; recommended for the shop)

1. Ensure `inventor_to_radan.bat` points to a valid Python at:
   - `C:\Tools\.venv\Scripts\python.exe`
2. Drag a BOM file (`.csv` or `.xlsx`) onto `inventor_to_radan.bat`.

### Option 2: The installed command (a pip install)

```powershell
inventor-to-radan "W:\path\to\BOM.csv"
```

### Option 3: Direct Python

```powershell
python bom_converter.py "W:\path\to\BOM.csv"
```

You can also pass an Excel BOM:

```powershell
python bom_converter.py "W:\path\to\BOM.xlsx"
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
