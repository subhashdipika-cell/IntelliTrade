@echo off
setlocal EnableExtensions
REM ============================================================
REM  IntelliTrade launcher
REM  BEFORE running: open the Vantage MT5 terminal and log in to
REM  your DEMO account (the app attaches to the running terminal).
REM ============================================================

echo Starting IntelliTrade...

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "LOGDIR=%ROOT%work\launcher-logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

if not exist "%BACKEND%\.venv\Scripts\python.exe" (
    echo ERROR: IntelliTrade backend Python environment is missing.
    exit /b 1
)
where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo ERROR: npm.cmd is not available in PATH.
    exit /b 1
)

REM --- Reuse IntelliTrade listeners and preserve unrelated port owners. ---
set "BACKEND_STATE=missing"
powershell.exe -NoLogo -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort 8100 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if(-not $c){exit 2}; $p=Get-CimInstance Win32_Process -Filter \"ProcessId=$($c.OwningProcess)\" -ErrorAction SilentlyContinue; $cmd=''; for($i=0; $p -and $i -lt 4; $i++){ $cmd += ' ' + $p.CommandLine; if(-not $p.ParentProcessId){break}; $p=Get-CimInstance Win32_Process -Filter \"ProcessId=$($p.ParentProcessId)\" -ErrorAction SilentlyContinue }; if($cmd -match 'IntelliTrade.+uvicorn main:app'){exit 0}; exit 1" >nul 2>&1
if not errorlevel 1 set "BACKEND_STATE=ready"
if errorlevel 1 if not errorlevel 2 set "BACKEND_STATE=conflict"

set "FRONTEND_STATE=missing"
powershell.exe -NoLogo -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort 3001 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if(-not $c){exit 2}; $p=Get-CimInstance Win32_Process -Filter \"ProcessId=$($c.OwningProcess)\" -ErrorAction SilentlyContinue; $cmd=''; for($i=0; $p -and $i -lt 4; $i++){ $cmd += ' ' + $p.CommandLine; if(-not $p.ParentProcessId){break}; $p=Get-CimInstance Win32_Process -Filter \"ProcessId=$($p.ParentProcessId)\" -ErrorAction SilentlyContinue }; if($cmd -match 'IntelliTrade.+next'){exit 0}; exit 1" >nul 2>&1
if not errorlevel 1 set "FRONTEND_STATE=ready"
if errorlevel 1 if not errorlevel 2 set "FRONTEND_STATE=conflict"

if "%BACKEND_STATE%"=="conflict" (
    echo ERROR: Port 8100 belongs to another application. Nothing was stopped.
    exit /b 1
)
if "%FRONTEND_STATE%"=="conflict" (
    echo ERROR: Port 3001 belongs to another application. Nothing was stopped.
    exit /b 1
)

REM Backend (FastAPI + MT5 + monitor) on http://localhost:8100
REM Port 8100 (not 8000) so it doesn't clash with Smart Money Trader's backend.
if "%BACKEND_STATE%"=="ready" (
    echo Backend is already running.
) else if /i "%TRADING_LAB_HIDDEN%"=="1" (
    start "" /b "%BACKEND%\.venv\Scripts\python.exe" -m uvicorn main:app --app-dir "%BACKEND%" --host 127.0.0.1 --port 8100 1^>^>"%LOGDIR%\backend.log" 2^>^&1
) else (
    start "IntelliTrade Backend" cmd.exe /k "cd /d ""%BACKEND%"" && .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8100"
)

REM Wait until FastAPI has completed startup before Next.js begins proxying API calls.
echo Waiting for IntelliTrade backend health check...
powershell -NoProfile -Command "$deadline=(Get-Date).AddSeconds(120); do { try { $response=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8100/api/health' -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 goto backend_failed
echo Backend is healthy.

REM Frontend (Next.js UI) on http://localhost:3001
if "%FRONTEND_STATE%"=="ready" (
    echo Frontend is already running.
) else if /i "%TRADING_LAB_HIDDEN%"=="1" (
    start "" /b cmd.exe /d /c "cd /d ""%FRONTEND%"" && npm.cmd run dev -- --port 3001 --turbopack 1^>^>""%LOGDIR%\frontend.log"" 2^>^&1"
) else (
    start "IntelliTrade Frontend" cmd.exe /k "cd /d ""%FRONTEND%"" && npm.cmd run dev -- --port 3001 --turbopack"
)

REM Give the servers a moment, then open the dashboard in your browser
powershell.exe -NoLogo -NoProfile -Command "$deadline=(Get-Date).AddSeconds(120); do { try { $response=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3001/' -TimeoutSec 2; if ($response.StatusCode -eq 200) { Start-Process 'http://127.0.0.1:3001/'; exit 0 } } catch {}; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 goto frontend_failed

echo.
echo IntelliTrade is running in two windows:
echo   Backend  - http://localhost:8100
echo   Frontend - http://localhost:3001
echo.
echo To STOP IntelliTrade, close those two windows.
echo This launcher window will now close.
exit

:frontend_failed
echo.
echo ERROR: IntelliTrade frontend did not become healthy within 120 seconds.
if /i "%TRADING_LAB_HIDDEN%"=="1" (
    echo Review work\launcher-logs\frontend.log for the startup error.
) else (
    echo Review the IntelliTrade Frontend window for the startup error.
)
if /i not "%TRADING_LAB_HIDDEN%"=="1" pause
exit /b 1

:backend_failed
echo.
echo ERROR: IntelliTrade backend did not become healthy within 120 seconds.
echo Review the IntelliTrade Backend window for the startup error.
echo The frontend was not started because its API would be unavailable.
echo.
if /i not "%TRADING_LAB_HIDDEN%"=="1" pause
exit /b 1
