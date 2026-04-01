@echo off
cd /d "%~dp0"
title LAN Store

echo.
echo   LAN Store - Starting...
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
  echo   Python 3 is required. Download from https://python.org
  pause
  exit /b 1
)

:: Create virtualenv if needed
if not exist ".venv" (
  echo   Setting up environment - first run only...
  python -m venv .venv
)

:: Install deps silently into venv
.venv\Scripts\pip install -r requirements.txt -q --disable-pip-version-check

:: Ensure a portable writable shared drive exists and is mapped
.venv\Scripts\python bootstrap_portable.py

:: Read port from config.json
set "PORT=8080"
for /f "usebackq delims=" %%P in (`.venv\Scripts\python -c "import json; print(json.load(open('config.json')).get('port', 8080))"`) do set "PORT=%%P"

:: Open browser after delay
start "" /b cmd /c "timeout /t 2 >nul && start http://localhost:%PORT%"

:: Start server using venv
.venv\Scripts\python main.py
pause
