@echo off
chcp 65001 > nul
echo ========================================
echo   启动前端服务 (端口 3000)
echo ========================================
cd /d %~dp0..\agent_frontend
echo 前端目录: %CD%
echo.
echo 按 Ctrl+C 停止服务
echo.
npm run dev
pause
