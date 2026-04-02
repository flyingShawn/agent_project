@echo off
chcp 65001 > nul
echo ========================================
echo   启动后端服务 (端口 8000)
echo ========================================
cd /d %~dp0..
echo 后端目录: %CD%
echo.
echo 按 Ctrl+C 停止服务
echo.
python -m uvicorn agent_backend.main:app --host 0.0.0.0 --port 8000 --reload
pause
