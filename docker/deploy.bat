@echo off
REM Docker快速部署脚本 - Windows版本

echo =========================================
echo   Desk Agent Docker 快速部署脚本
echo =========================================
echo.

REM 检查Docker是否安装
docker --version >nul 2>&1
if errorlevel 1 (
    echo 错误: Docker未安装，请先安装Docker Desktop
    echo 安装指南: https://docs.docker.com/docker-for-windows/install/
    pause
    exit /b 1
)

REM 检查Docker Compose是否安装
docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo 错误: Docker Compose未安装
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('docker --version') do set DOCKER_VERSION=%%i
for /f "tokens=*" %%i in ('docker-compose --version') do set COMPOSE_VERSION=%%i

echo √ Docker版本: %DOCKER_VERSION%
echo √ Docker Compose版本: %COMPOSE_VERSION%
echo.

REM 检查.env文件
if not exist .env (
    echo ⚠ 未找到.env文件，正在从.env.example创建...
    if exist .env.example (
        copy .env.example .env >nul
        echo √ 已创建.env文件，请根据需要修改配置
    ) else (
        echo 错误: 未找到.env.example文件
        pause
        exit /b 1
    )
) else (
    echo √ 找到.env配置文件
)

echo.
echo =========================================
echo   开始构建和启动服务...
echo =========================================
echo.

REM 停止旧容器
echo 1. 停止现有容器...
docker-compose down 2>nul

REM 构建镜像
echo.
echo 2. 构建Docker镜像...
docker-compose build
if errorlevel 1 (
    echo 错误: 镜像构建失败
    pause
    exit /b 1
)

REM 启动服务
echo.
echo 3. 启动服务...
docker-compose up -d
if errorlevel 1 (
    echo 错误: 服务启动失败
    pause
    exit /b 1
)

REM 等待服务启动
echo.
echo 4. 等待服务启动...
timeout /t 10 /nobreak >nul

REM 检查服务状态
echo.
echo 5. 检查服务状态...
docker-compose ps

echo.
echo =========================================
echo   部署完成！
echo =========================================
echo.
echo 访问地址：
echo   - 前端界面: http://localhost
echo   - 后端API: http://localhost:8000/docs
echo   - Qdrant控制台: http://localhost:6333/dashboard
echo.
echo 常用命令：
echo   - 查看日志: docker-compose logs -f
echo   - 停止服务: docker-compose down
echo   - 重启服务: docker-compose restart
echo.
pause
