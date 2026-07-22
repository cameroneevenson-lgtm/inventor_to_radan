# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this app does

Converts an Inventor BOM (`.csv`/`.xlsx`) into a Radan import CSV, with DXF accountability checks and a text audit report. See `README.md` for the full CLI usage, output format (`FILE, QTY, MATERIAL, THICKNESS, UNIT, STRATEGY`, no header row), and row-export rules (DXF must exist, quantity > 0, a description rule must exist).

## Commands

Batch launcher (drag a BOM file onto it, or run with a path):

```powershell
.\inventor_to_radan.bat "W:\path\to\BOM.csv"
```

Direct Python:

```powershell
C:\Tools\.venv\Scripts\python.exe inventor_to_radan.py "W:\path\to\BOM.xlsx"
```

Tests:

```powershell
C:\Tools\.venv\Scripts\python.exe -m pytest
C:\Tools\.venv\Scripts\python.exe -m pytest tests/test_inventor_to_radan.py -k test_name
```

`PAUSE_ON_START=1` pauses for a keypress before running (debugging aid).

## Architecture

**This app is consumed programmatically by `truck_nest_explorer`, and that headless path is a real contract, not just a CLI convenience.** `inline_runner.run_inline()` / `convert_bom_to_radan_csv()` in `inventor_to_radan.py` provide a no-dialogs conversion path used by the sibling app's `services.py` (`run_inventor_to_radan_inline`, called with `allow_prompts=False, show_summary=False`). With `allow_prompts=False`, missing-DXF/missing-rule prompts and the Report Review gate are skipped entirely — instead the caller must handle `InventorToRadanNeedsUi`, `InventorToRadanCancelled`, or `InventorToRadanReportRejected` being raised. Changing this function's signature or exception contract is a cross-repo breaking change.

**Report Review is a mandatory gate in interactive mode**: after generating `*_Radan.csv` and `*_report.txt`, `dialogs/report_review_dialog.py` blocks until the operator accepts or discards; choosing Discard deletes both just-written output files. A run is not "complete" just because the CSV was written to disk.

**Rule resolution has a specific precedence**: `ftq_parts.csv` membership forces `MATERIAL` to `Aluminum 3003 CHK FTQ` regardless of the matched description rule (`description_rules.csv`) — check `ftq_parts.csv` first when a material output looks wrong. `description_rules.csv` column A is also the sole list of known laser descriptions; `nonlaser_tokens.csv` classifies known non-laser families. Choosing Expected Laser for an unknown missing DXF must collect a complete rule immediately—never append a description-only row.

**Production Inventor BOMs do not contain a Material column.** Material and strategy come from the Description-keyed `description_rules.csv`. Do not reintroduce the old `laser_materials.csv` learning path; it remained header-only because it had no production input.

**Local CSV config files (`description_rules.csv`, `ftq_parts.csv`, `nonlaser_tokens.csv`) are created automatically if missing** — don't add defensive existence checks around them elsewhere; `rule_store.py` owns that.
