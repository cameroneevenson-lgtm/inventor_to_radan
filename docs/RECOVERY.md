# Disaster recovery

## Prerequisites and location

- Clone to `C:\Tools\inventor_to_radan` and recreate the shared Python environment.
- Reinstall/license Autodesk Inventor and RADAN as required by the surrounding production workflow.
- Restore the `W:`/engineering share mappings used for BOM input and report output.

## Install

```powershell
Set-Location C:\Tools\inventor_to_radan
C:\Tools\.venv\Scripts\python.exe -m pip install pandas openpyxl pyside6
```

Ensure `inventor_to_radan.bat` points to `C:\Tools\.venv\Scripts\python.exe` rather than an obsolete
machine-specific interpreter.

## Configuration and state

Classification rules and CSV configuration (`description_rules.csv`, `ftq_parts.csv`, and
`nonlaser_tokens.csv`) are tracked by Git. Missing local CSV configuration is recreated by the app. BOM inputs,
generated reports, and production job material remain authoritative on company shares. Caches, logs, and test
outputs are not backed up, and this repository has no separate live-state entry in the encrypted bundle.

## Restore and verify

1. Review paths/constants in `config.py` against restored drive mappings.
2. Run the tool against a copied known CSV and XLSX BOM.
3. Compare part classification and report output with the source data.
4. Confirm the drag-and-drop `inventor_to_radan.bat` launcher works.
5. Do not process a production BOM until output paths and material rules have been reviewed.
