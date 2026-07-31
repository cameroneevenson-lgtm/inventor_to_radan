@echo off
setlocal

echo Starting Inventor BOM to Radan conversion...
echo.

set "ROOT=%~dp0"
set "PY=C:\Tools\.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo ERROR: venv Python not found at:
  echo   C:\Tools\.venv\Scripts\python.exe
  echo.
  pause
  exit /b 1
)

set "SCRIPT=%ROOT%bom_converter.py"

if not "%~1"=="" (
  cd /d "%~dp1"
)

echo Running with: %PY%
echo.

"%PY%" "%SCRIPT%" "%~1"
set "RC=%ERRORLEVEL%"

echo.
echo Script finished with code %RC%. Press any key to close.
pause
exit /b %RC%
