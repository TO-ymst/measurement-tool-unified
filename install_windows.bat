@echo off
setlocal

cd /d "%~dp0"

set "APP_DIR=%~dp0"
set "VENV_DIR=%APP_DIR%.venv"
set "REQ_FILE=%APP_DIR%web_measurement_app\requirements.txt"
set "PYTHON_CMD="

call :resolve_python
if errorlevel 1 goto :fail

if not exist "%REQ_FILE%" (
  echo [ERROR] requirements.txt was not found.
  echo         %REQ_FILE%
  goto :fail
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [INFO] Creating virtual environment...
  call %PYTHON_CMD% -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    goto :fail
  )
)

echo [INFO] Upgrading pip...
call "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] Failed to upgrade pip.
  goto :fail
)

echo [INFO] Installing packages...
call "%VENV_DIR%\Scripts\python.exe" -m pip install -r "%REQ_FILE%"
if errorlevel 1 (
  echo [ERROR] Failed to install packages.
  goto :fail
)

echo.
echo [OK] Installation completed.
echo      Next time, run start_windows.bat.
pause
exit /b 0

:resolve_python
where py >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=py -3"
  exit /b 0
)

where python >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=python"
  exit /b 0
)

echo [ERROR] Python 3 was not found.
exit /b 1

:fail
echo.
echo [FAILED] Setup aborted.
pause
exit /b 1
