# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Adding to this file

**Be conservative.** This file loads into context in full, every session, so length costs
attention — a file that grows without pruning gets skimmed instead of read. Before adding
anything, check that it changes what somebody would *do*:

- **If a rule already here covers the new discovery, add nothing** — a fresh example of an
  existing rule is the rule working, not new information.
- **Sharpen the line that was almost right; don't append a section beside it.**
- **Dated findings, probe results and campaign history go in `docs/`.** A closed
  investigation earns one sentence: what is settled, and what not to re-try.
- **Don't describe what the code already says** — layout, rendering, field lists and call
  chains are read faster from the source than from here.

Removing a line that no longer earns its place is as valuable as adding one.

## What this app does

Converts an Inventor BOM (`.csv`/`.xlsx`) into a Radan import CSV, with DXF
accountability checks and a text audit report. See `README.md` for the full CLI usage,
output format (`FILE, QTY, MATERIAL, THICKNESS, UNIT, STRATEGY`, no header row), and
row-export rules (DXF must exist, quantity > 0, a description rule must exist).

## Commands

```powershell
.\inventor_to_radan.bat "W:\path\to\BOM.csv"                      # or drag a BOM onto it
C:\Tools\.venv\Scripts\python.exe bom_converter.py "W:\path\to\BOM.xlsx"
C:\Tools\.venv\Scripts\python.exe -m pytest
C:\Tools\.venv\Scripts\python.exe -m pytest tests/test_inventor_to_radan.py -k test_name
```

`PAUSE_ON_START=1` pauses for a keypress before running (debugging aid).

## Architecture

**The headless path is a cross-repo contract, not just a CLI convenience.**
`inline_runner.run_inline()` / `convert_bom_to_radan_csv()` in `bom_converter.py`
provide the no-dialogs conversion path used by `truck_nest_explorer`'s `services.py`
(`run_inventor_to_radan_inline`, called with `allow_prompts=False,
show_summary=False`). With `allow_prompts=False`, missing-DXF/missing-rule prompts and
the Report Review gate are skipped entirely — instead the caller must handle
`InventorToRadanNeedsUi`, `InventorToRadanCancelled`, or
`InventorToRadanReportRejected` being raised. **Changing this function's signature or
exception contract is a cross-repo breaking change.**

**Report Review is a mandatory gate in interactive mode**: after generating
`*_Radan.csv` and `*_report.txt`, `dialogs/report_review_dialog.py` blocks until the
operator accepts or discards; Discard deletes both just-written output files. A run is
not "complete" just because the CSV was written to disk.

**Rule resolution has a specific precedence**: `ftq_parts.csv` membership forces
`MATERIAL` to `Aluminum 3003 CHK FTQ` regardless of the matched description rule
(`description_rules.csv`) — check `ftq_parts.csv` first when a material output looks
wrong. `description_rules.csv` column A is also the sole list of known laser
descriptions; `nonlaser_tokens.csv` classifies known non-laser families. Choosing
Expected Laser for an unknown missing DXF must collect a complete rule immediately —
**never append a description-only row.**

**The two "no DXF is fine" lists key off different columns and are not
interchangeable.** `nonlaser_tokens.csv` matches the first token of the
*Description* - purchased families that were never laser work. `stock_cut_parts.csv`
matches the *Part Number* family (part number minus a trailing `-<length>`, so one
`TIE DOWN` row covers `TIE DOWN-28.75` and every future length) - parts cut to length
off stock strip. Stock-cut parts carry an ordinary sheet description shared with real
laser parts, so a description token cannot express them: adding one would mute every
part on that material.

**Report Review checkboxes are only for red/yellow sections.** Green sections
(non-laser, stock-cut) confirm a classification the operator already wrote and must
not generate a per-line checkbox - burying two real warnings under eighteen
confirmations is how the gate stops being read.

**`truck_nest_explorer/dialogs/inventor_report_review_dialog.py` is a second copy of
`dialogs/report_review_dialog.py`, and it is the one operators actually see** -
conversions reach them through that app, not this repo's launcher. Changing the
report's sections here, or the review gate, means changing both; a fix applied only
here looks like it did nothing.

**Production Inventor BOMs do not contain a Material column.** Material and strategy
come from the Description-keyed `description_rules.csv`. **Do not reintroduce the old
`laser_materials.csv` learning path**; it remained header-only because it had no
production input.

**Local CSV config files (`description_rules.csv`, `ftq_parts.csv`,
`nonlaser_tokens.csv`) are created automatically if missing** — don't add defensive
existence checks around them elsewhere; `rule_store.py` owns that.

**The rule CSVs do not always live in the repo.** `config.DATA_DIR` is the checkout when
one is present (`.git` alongside), so the shop's tables stay version controlled; a pip
install instead reads and writes `%LOCALAPPDATA%\inventor_to_radan`, seeded once from the
packaged copies, because site-packages is replaced on upgrade.
`INVENTOR_TO_RADAN_DATA_DIR` overrides both. Seeding keys off `DATA_DIR`, not the
`RULES_CSV`-style constants - a caller that repoints those wants its own file left alone.

## Branching

All work happens on `main`. Do not create branches for agent work - commit and push straight to `main`. If an agent branch does turn up, fold it into `main`, prune it locally and on the remote, then push.
