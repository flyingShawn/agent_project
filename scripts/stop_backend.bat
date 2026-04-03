@echo off
echo ========================================
echo   Stopping Backend Service (Port 8000)
echo ========================================
echo.
echo Checking port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "0.0.0.0:8000" ^| findstr "LISTENING"') do (
    echo Found process PID: %%a using port 8000
    echo Killing process...
    taskkill /F /PID %%a > nul 2>&1
    echo Process PID: %%a killed
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "127.0.0.1:8000" ^| findstr "LISTENING"') do (
    echo Found process PID: %%a using port 8000
    echo Killing process...
    taskkill /F /PID %%a > nul 2>&1
    echo Process PID: %%a killed
)
echo.
echo ========================================
echo   Backend Service Stopped
echo ========================================
