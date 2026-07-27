@echo off
setlocal

cd /d "%~dp0"
set "APP_DIR=%~dp0"
set "VENV_PYTHON=%APP_DIR%.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
  echo [ERROR] Python venv was not found.
  echo         Run install_windows.bat first.
  pause
  exit /b 1
)

"%VENV_PYTHON%" -m uvicorn web_measurement_app.server:app --host 0.0.0.0 --port 9000
pause
exit /b %errorlevel%
