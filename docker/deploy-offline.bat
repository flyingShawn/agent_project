@echo off
REM Docker离线部署脚本 - Windows版本
REM 从离线包中加载镜像并启动服务

setlocal enabledelayedexpansion

echo =========================================
echo   Desk Agent Docker 离线部署脚本
echo =========================================
echo.

REM 检查Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo 错误: Docker未安装，请先安装Docker Desktop
    pause
    exit /b 1
)

REM 加载镜像
echo [1/4] 加载Docker镜像（可能需要几分钟）...
for %%F in (images\*.tar) do (
    echo   加载 %%F...
    docker load -i "%%F"
)

REM 准备配置文件
echo.
echo [2/4] 准备配置文件...
if not exist config\.env (
    if exist config\.env.example (
        copy config\.env.example config\.env >nul
        echo   已从 .env.example 创建 .env，请根据实际环境修改
    ) else (
        echo   警告: 未找到 .env.example，请手动创建 config/.env
    )
) else (
    echo   已有 .env 配置文件
)

REM 复制配置文件到工作目录
if not exist .env copy config\.env .env >nul
if not exist nginx.conf copy config\nginx.conf nginx.conf >nul
if not exist entrypoint.frontend.sh copy config\entrypoint.frontend.sh entrypoint.frontend.sh >nul

REM 停止旧容器
echo.
echo [3/4] 停止现有容器...
docker compose down 2>nul

REM 启动服务
echo.
echo [4/4] 启动服务...
docker compose up -d
if errorlevel 1 (
    echo 错误: 服务启动失败
    pause
    exit /b 1
)

REM 等待启动
timeout /t 10 /nobreak >nul

echo.
echo =========================================
echo   部署完成！
echo =========================================
echo.
echo 访问地址：
echo   - 前端界面: http://localhost:81
echo   - 后端API:  http://localhost:8000/docs
echo.
echo 重要提醒：
echo   1. 请修改 .env 文件中的数据库地址、LLM地址等配置
echo   2. 修改后执行: docker compose restart backend
echo   3. 查看日志:   docker compose logs -f backend
echo.
pause
