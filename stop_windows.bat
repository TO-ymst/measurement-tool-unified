@echo off
setlocal

echo [INFO] Stopping process on port 9000...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":9000" ^| findstr "LISTENING"') do (
  taskkill /PID %%P /F >nul 2>nul
)

echo [OK] Stop command completed.
pause
exit /b 0
