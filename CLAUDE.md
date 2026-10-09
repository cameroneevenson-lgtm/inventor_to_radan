# CLAUDE.md
New/changed Python lines must pass Ruff via the pre-commit hook; install it with `C:\Tools\.venv\Scripts\python.exe C:\Tools\tools_bootstrap\install_hooks.py`.

## Adding to this file

This file loads in full every session; one that grows without pruning gets skimmed. Add only what changes what somebody would *do*:

- If a rule here already covers the discovery, add nothing — a fresh example is the rule working.
- Sharpen the line that was almost right rather than appending a section beside it.
- Dated findings, probe results and campaign history go in `docs/`; a closed investigation earns one sentence: what is settled, what not to re-try.
- Don't describe what the code already says (layout, rendering, field lists, call chains).
- A bug fix is not by itself a reason for a new instruction — prefer enforcing the lesson in code structure, validation or a test.
- Before adding, all must hold: durable and non-obvious; not already enforced or documented elsewhere; its absence would realistically cause a consequential mistake; expressible in one precise sentence; no existing line can be sharpened instead.
- This file is not a bug diary, changelog or substitute for reading the code. Removing a line that no longer earns its place is as valuable as adding one.

## What this app does

Converts an Inventor BOM (`.csv`/`.xlsx`) into a Radan import CSV, with DXF accountability checks and a text audit report. `README.md` has the CLI usage, output format (`FILE, QTY, MATERIAL, THICKNESS, UNIT, STRATEGY`, no header row) and row-export rules.

## Commands

```powershell
.\inventor_to_radan.bat "W:\path\to\BOM.csv"                      # or drag a BOM onto it
C:\Tools\.venv\Scripts\python.exe bom_converter.py "W:\path\to\BOM.xlsx"
C:\Tools\.venv\Scripts\python.exe -m pytest
C:\Tools\.venv\Scripts\python.exe -m pytest tests/test_inventor_to_radan.py -k test_name
```

`PAUSE_ON_START=1` pauses for a keypress before running.

## Architecture

**The headless path is a cross-repo contract.** `inline_runner.run_inline()` / `convert_bom_to_radan_csv()` are called by truck_nest_explorer (`inventor_bridge.run_inventor_to_radan_inline`, with `allow_prompts=False, show_summary=False`) and by odd_job_intake (`job_intake_bom`). With `allow_prompts=False` the missing-DXF/missing-rule prompts and the Report Review gate are skipped and the caller must handle `InventorToRadanNeedsUi`, `InventorToRadanCancelled` or `InventorToRadanReportRejected`. **Changing that signature or exception contract is a cross-repo breaking change.**

**Report Review is a mandatory gate in interactive mode:** `dialogs/report_review_dialog.py` blocks until the operator accepts or discards, and Discard deletes both just-written `*_Radan.csv` and `*_report.txt`. A run is not complete just because the CSV is on disk.

**The gate's rules live in `report_review_rules.py`, read by two dialogs:** this repo's Tk `dialogs/report_review_dialog.py` and truck_nest_explorer's Qt `dialogs/inventor_report_review_dialog.py` — the one operators actually see. **Red/yellow lines each demand their own checkbox; green lines never do**, so a section of already-classified parts (non-laser, stock-cut) must be green, or real warnings get buried under confirmations. Changing the report's sections means changing that module plus `report_writer.py`; it must stay stdlib-only and listed in `inline_runner.INLINE_IMPORT_NAMES`. TNE's Qt dialog is TNE's file; only the report content must stay in step.

**Rule precedence:** `ftq_parts.csv` membership forces `MATERIAL` to `Aluminum 3003 CHK FTQ` whatever `description_rules.csv` matched — check it first when a material looks wrong. `description_rules.csv` column A is the sole list of known laser descriptions; `nonlaser_tokens.csv` classifies known non-laser families. Choosing Expected Laser for an unknown missing DXF must collect a complete rule immediately — **never append a description-only row.** The verification build writes nothing instead: `collect_radan_rules=False` skips the prompt and reports the descriptions under *New descriptions*.

**The two "no DXF is fine" lists key off different columns and are not interchangeable.** `nonlaser_tokens.csv` matches the first token of the *Description* (purchased families). `stock_cut_parts.csv` matches the *Part Number* family (minus a trailing `-<length>`) for parts cut from stock strip; those share an ordinary sheet description with real laser parts, so a description token would mute every part on that material.

**Production Inventor BOMs have no Material column;** material and strategy come from `description_rules.csv`. Do not reintroduce the `laser_materials.csv` learning path.

**`rule_store.py` creates missing rule CSVs** — don't add existence checks around them elsewhere.

**Data location:** `config.DATA_DIR` is the checkout when `.git` is alongside (tables stay version controlled); a pip install uses `%LOCALAPPDATA%\inventor_to_radan`, seeded once from the packaged copies; `INVENTOR_TO_RADAN_DATA_DIR` overrides both. Seeding keys off `DATA_DIR`, not the `RULES_CSV`-style constants — a caller that repoints those wants its own file left alone.

**Verification build (`verify_main.py`, frozen by `build_verify_exe.bat`) writes no RADAN CSV:** it passes `write_csv=False` (keyword-only, default `True`, so TNE's contract is untouched), `result.out_path` is `None`, and the report says "not written (verification only)". It builds from `.buildvenv`, never `C:\Tools\.venv` — PyInstaller bundles whatever the venv holds; the `.spec` is committed so exclusions stay reviewable. `_resolve_seed_dir` finds the frozen defaults under `sys._MEIPASS`; a build that omits `--add-data` silently seeds an empty catalog.

**The frozen build keeps its tables in `data\` beside the exe** (`config._resolve_data_dir`), so a copied folder is one shared installation; it falls back to the per-user dir only when that location is read-only. On a deployed copy those files are the live tables:
- `config._migrate_loose_tables` moves them in from the older loose layout — never seed a fresh `data\` over them, or every classification made since deployment is lost.
- `data.backup\` is taken at every launch and preferred over the frozen snapshot when restoring; it must stay *outside* `data\`, or deleting that folder takes the backup with it.

**The frozen build is windowed, so `print()` is a crash, not a no-op** (`sys.stdout`/`sys.stderr` are `None`): use `bom_converter.tell()`.

**The BOM picker's shortlist (`bom_finder`, `config.BOM_SEARCH_*`):**
- `BOM_SEARCH_DEPTH` must stay 3 — whole-job BOMs sit at depth 1, pack BOMs at 2, anything under `PUMP PACK` at 3; a shallower bound still lists job BOMs, so it looks fine while hiding every canonical kit BOM.
- Never offer a `*_Radan.csv` or the app's own rule tables — this tool writes both into the folders it scans.
- The walk runs on a worker thread and is ended by the `BOM_SCAN_SECONDS` budget; `BOM_SHORTLIST_LIMIT` only trims the date-sorted result and must never become a stopping condition (folder timestamps don't track subfolder contents, so discovery order isn't date order).

**The GUI is tkinter (`dialogs/tk_base.py`, keeping the Qt-style `.exec()` returning `ACCEPTED`) and the BOM is a list of dicts read by `bom_reader.py` via `csv`/`openpyxl`;** don't bring pandas or PySide6 back — they were most of the frozen exe. Two pandas behaviours are load-bearing: the classify dialog's order and the output CSV's row order are sorted, and the CSV is written with CRLF.

## Branching

All work happens on `main`. Do not create branches for agent work - commit and push straight to `main`. If an agent branch does turn up, fold it into `main`, prune it locally and on the remote, then push.
