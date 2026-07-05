@echo off
REM ============================================================
REM  IntelliTrade launcher
REM  BEFORE running: open the Vantage MT5 terminal and log in to
REM  your DEMO account (the app attaches to the running terminal).
REM ============================================================

echo Starting IntelliTrade...

REM --- Clean up any previous IntelliTrade instance so ports 8100/3000 are free
REM     (closes old windows AND kills orphaned node/python holding the ports). ---
taskkill /fi "WindowTitle eq IntelliTrade Backend*" /f >nul 2>&1
taskkill /fi "WindowTitle eq IntelliTrade Frontend*" /f >nul 2>&1
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8100,3000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 2 /nobreak >nul

REM Backend (FastAPI + MT5 + monitor) on http://localhost:8100
REM Port 8100 (not 8000) so it doesn't clash with Smart Money Trader's backend.
start "IntelliTrade Backend" cmd /k "cd /d D:\IntelliTrade\backend && .venv\Scripts\python.exe -m uvicorn main:app --port 8100"

REM Frontend (Next.js UI) on http://localhost:3000
start "IntelliTrade Frontend" cmd /k "cd /d D:\IntelliTrade\frontend && npm run dev"

REM Give the servers a moment, then open the dashboard in your browser
timeout /t 12 /nobreak >nul
start http://localhost:3000

echo.
echo IntelliTrade is running in two windows:
echo   Backend  - http://localhost:8100
echo   Frontend - http://localhost:3000
echo.
echo To STOP IntelliTrade, close those two windows.
echo (You can close this window.)
