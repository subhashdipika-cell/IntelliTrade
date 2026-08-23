@echo off
REM ============================================================
REM  IntelliTrade launcher
REM  BEFORE running: open the Vantage MT5 terminal and log in to
REM  your DEMO account (the app attaches to the running terminal).
REM ============================================================

echo Starting IntelliTrade...

REM --- Clean up any previous IntelliTrade instance so ports 8100/3001 are free
REM     (closes old windows AND kills orphaned node/python holding the ports). ---
taskkill /fi "WindowTitle eq IntelliTrade Backend*" /f >nul 2>&1
taskkill /fi "WindowTitle eq IntelliTrade Frontend*" /f >nul 2>&1
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8100,3001 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 2 /nobreak >nul

REM Backend (FastAPI + MT5 + monitor) on http://localhost:8100
REM Port 8100 (not 8000) so it doesn't clash with Smart Money Trader's backend.
start "IntelliTrade Backend" cmd /c "cd /d D:\IntelliTrade\backend && .venv\Scripts\python.exe -m uvicorn main:app --port 8100"

REM Wait until FastAPI has completed startup before Next.js begins proxying API calls.
echo Waiting for IntelliTrade backend health check...
powershell -NoProfile -Command "$deadline=(Get-Date).AddSeconds(60); do { try { $response=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8100/api/health' -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 goto backend_failed
echo Backend is healthy.

REM Frontend (Next.js UI) on http://localhost:3001
start "IntelliTrade Frontend" cmd /c "cd /d D:\IntelliTrade\frontend && npm run dev -- --port 3001"

REM Give the servers a moment, then open the dashboard in your browser
timeout /t 12 /nobreak >nul
start http://localhost:3001

echo.
echo IntelliTrade is running in two windows:
echo   Backend  - http://localhost:8100
echo   Frontend - http://localhost:3001
echo.
echo To STOP IntelliTrade, close those two windows.
echo This launcher window will now close.
exit

:backend_failed
echo.
echo ERROR: IntelliTrade backend did not become healthy within 60 seconds.
echo Review the IntelliTrade Backend window for the startup error.
echo The frontend was not started because its API would be unavailable.
echo.
pause
exit /b 1
