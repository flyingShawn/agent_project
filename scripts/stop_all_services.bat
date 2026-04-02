@echo off
chcp 65001 > nul
echo ========================================
echo   停止所有相关服务
echo ========================================

echo.
echo [1/3] 检查 8000 端口 (后端)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo 发现进程 PID: %%a 占用 8000 端口
    echo 正在终止...
    taskkill /F /PID %%a > nul 2>&1
    echo 已终止 PID: %%a
)

echo.
echo [2/3] 检查 3000 端口 (前端)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000" ^| findstr "LISTENING"') do (
    echo 发现进程 PID: %%a 占用 3000 端口
    echo 正在终止...
    taskkill /F /PID %%a > nul 2>&1
    echo 已终止 PID: %%a
)

echo.
echo [3/3] 检查 Node.js 进程...
taskkill /F /IM node.exe > nul 2>&1
echo 已终止所有 Node.js 进程

echo.
echo ========================================
echo   所有服务已停止
echo ========================================
pause
