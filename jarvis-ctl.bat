@echo off
setlocal
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo Jarvis is not set up yet. Run setup_windows.ps1 first.
  exit /b 1
)
"venv\Scripts\python.exe" "scripts\jarvis_ctl.py" %*
