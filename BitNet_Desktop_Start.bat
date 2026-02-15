@echo off
setlocal
cd /d %~dp0

if not exist .venv (
  py -m venv .venv
)

call .venv\Scripts\activate
python -m pip install --upgrade pip >nul
python -m pip install -e . >nul

start "" pythonw "%~dp0bitnet_desktop.pyw"
endlocal
