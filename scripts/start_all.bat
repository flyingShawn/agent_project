@echo off
chcp 65001 > nul
echo ========================================
echo   启动所有服务 (后端8000 + 前端3000)
echo ========================================

echo.
echo [1] 正在停止旧服务...
call "%~dp0stop_all_services.bat"

echo.
echo [2] 启动后端服务 (端口 8000)...
start "Backend" cmd /k "cd /d %~dp0.. && python -m uvicorn agent_backend.main:app --host 0.0.0.0 --port 8000"
echo 后端已启动

echo.
echo [3] 启动前端服务 (端口 3000)...
start "Frontend" cmd /k "cd /d %~dp0..\agent_frontend && npm run dev"
echo 前端已启动

echo.
echo ========================================
echo   所有服务已启动!
echo   后端: http://localhost:8000
echo   前端: http://localhost:3000
echo ========================================
echo.
echo 关闭此窗口不会停止服务
echo 如需停止服务，请运行 stop_all_services.bat
pause
