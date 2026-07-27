@echo off
setlocal

cd /d "%~dp0"

set "APP_DIR=%~dp0"
set "URL=http://127.0.0.1:9000"
set "SERVER_TITLE=Wi-Fi Measurement App"
set "RUNNER=%APP_DIR%run_server_windows.bat"

if not exist "%APP_DIR%.venv\Scripts\python.exe" (
  echo [ERROR] Initial setup has not been completed.
  echo         Run install_windows.bat first.
  pause
  exit /b 1
)

if not exist "%RUNNER%" (
  echo [ERROR] Internal runner file was not found.
  echo         %RUNNER%
  pause
  exit /b 1
)

call :check_running
if "%SERVER_RUNNING%"=="1" goto :open_browser

echo [INFO] Starting app server...
start "%SERVER_TITLE%" cmd /k call "%RUNNER%"

echo [INFO] Waiting for server startup...
powershell -NoProfile -ExecutionPolicy Bypass -Command "for ($i=0; $i -lt 30; $i++) { try { Invoke-WebRequest -Uri '%URL%/api/status' -UseBasicParsing | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } }; exit 1"
if errorlevel 1 (
  echo [ERROR] Server startup check failed.
  echo         Check the opened console window for details.
  pause
  exit /b 1
)

:open_browser
start "" "%URL%"
echo [OK] Browser opened.
exit /b 0

:check_running
set "SERVER_RUNNING=0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri '%URL%/api/status' -UseBasicParsing | Out-Null; exit 0 } catch { exit 1 }"
if not errorlevel 1 set "SERVER_RUNNING=1"
exit /b 0
