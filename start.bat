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
  echo   Setting up environment (first run only)...
  python -m venv .venv
)

:: Install deps silently into venv
.venv\Scripts\pip install -r requirements.txt -q --disable-pip-version-check

:: Open browser after delay
start "" /b cmd /c "timeout /t 2 >nul && start http://localhost:8080"

:: Start server using venv
.venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8080
pause
