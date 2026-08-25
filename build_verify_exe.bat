@echo off
setlocal
REM Builds the verification-only exe handed to designers.
REM
REM The four CSVs are frozen into the bundle from this checkout, so the exe
REM carries the shop's rule tables as of build time. Rebuild and redistribute
REM after adding rules here, or point machines at a shared table with
REM INVENTOR_TO_RADAN_DATA_DIR.

set "ROOT=%~dp0"
set "PY=C:\Tools\.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo ERROR: venv Python not found at %PY%
  pause
  exit /b 1
)

"%PY%" -m PyInstaller --noconfirm --clean --onedir --name "BOM Verify" ^
  --distpath "%ROOT%dist" --workpath "%ROOT%build" --specpath "%ROOT%build" ^
  --paths "%ROOT%." ^
  --add-data "%ROOT%description_rules.csv;." ^
  --add-data "%ROOT%ftq_parts.csv;." ^
  --add-data "%ROOT%nonlaser_tokens.csv;." ^
  --add-data "%ROOT%stock_cut_parts.csv;." ^
  "%ROOT%verify_main.py"

echo.
echo Build finished with code %ERRORLEVEL%.
pause
