@echo off
setlocal

REM Builds the verification-only exe handed to designers: a single file, no
REM Python needed on the target machine.
REM
REM Builds from .buildvenv, NOT C:\Tools\.venv. The shared venv carries every
REM other tool's dependencies, and PyInstaller bundles whatever it finds: it
REM was shipping 80 MB of pyarrow because streamlit requires it, plus scipy,
REM matplotlib, PIL and cryptography. A venv of this project's own is the
REM difference between a 235 MB build and a 50 MB one, and it does not grow
REM every time somebody installs something into C:\Tools\.venv.

REM Do not delete dist\ before building. Once the exe has been deployed the CSVs
REM beside it are the live rule tables; PyInstaller only replaces the exe and
REM leaves them alone, which is the behaviour to keep.

set "ROOT=%~dp0"
set "VENV=%ROOT%.buildvenv"
set "PY=%VENV%\Scripts\python.exe"

if not exist "%PY%" (
  echo Creating the build venv at %VENV% ...
  py -3 -m venv "%VENV%" || python -m venv "%VENV%"
  if errorlevel 1 (
    echo ERROR: could not create the build venv.
    pause
    exit /b 1
  )
  "%PY%" -m pip install --upgrade pip
  "%PY%" -m pip install pandas openpyxl pyside6 pyinstaller
  if errorlevel 1 (
    echo ERROR: could not install build dependencies.
    pause
    exit /b 1
  )
)

"%PY%" -m PyInstaller --noconfirm --clean ^
  --distpath "%ROOT%dist" --workpath "%ROOT%build" ^
  "%ROOT%BOM Verify.spec"

echo.
echo Build finished with code %ERRORLEVEL%.
pause
