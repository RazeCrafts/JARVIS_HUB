@echo off
setlocal
cd /d "%~dp0"
if not exist "venv-windows\Scripts\python.exe" (
  echo Jarvis is not set up yet. Run setup_windows.ps1 first.
  pause
  exit /b 1
)
set PATH=%~dp0venv-windows\Scripts;%PATH%
set PYTHONUNBUFFERED=1
"venv-windows\Scripts\python.exe" "main_dashboard.py" %*
