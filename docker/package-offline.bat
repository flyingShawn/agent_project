@echo off
REM Docker离线打包脚本 - Windows版本
REM 将所有镜像和配置文件打包为一个压缩包，用于内网离线部署

setlocal enabledelayedexpansion

set OUTPUT_DIR=agent-docker-offline
set OUTPUT_FILE=agent-docker-offline.zip

echo =========================================
echo   Desk Agent Docker 离线打包脚本
echo =========================================
echo.

REM 检查Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo 错误: Docker未安装
    pause
    exit /b 1
)

REM 检查镜像是否存在
echo [1/5] 检查本地镜像...
set MISSING=0
for %%I in (agent-backend-base:latest agent-backend:latest agent-frontend:latest qdrant/qdrant:v1.17.0) do (
    docker image inspect %%I >nul 2>&1
    if errorlevel 1 (
        echo   ✗ 缺少镜像: %%I
        set MISSING=1
    ) else (
        echo   ✓ 已有镜像: %%I
    )
)

if !MISSING!==1 (
    echo.
    echo 部分镜像不存在，请先构建：
    echo   1. 运行 build-base.ps1 构建基础镜像
    echo   2. 运行 deploy.bat 构建应用镜像
    echo   3. 重新运行本打包脚本
    pause
    exit /b 1
)

REM 创建输出目录
echo.
echo [2/5] 准备打包目录...
if exist %OUTPUT_DIR% rmdir /s /q %OUTPUT_DIR%
mkdir %OUTPUT_DIR%
mkdir %OUTPUT_DIR%\images
mkdir %OUTPUT_DIR%\config

REM 导出镜像
echo.
echo [3/5] 导出Docker镜像（可能需要几分钟）...
echo   导出 agent-backend-base...
docker save agent-backend-base:latest -o %OUTPUT_DIR%\images\agent-backend-base.tar
echo   导出 agent-backend...
docker save agent-backend:latest -o %OUTPUT_DIR%\images\agent-backend.tar
echo   导出 agent-frontend...
docker save agent-frontend:latest -o %OUTPUT_DIR%\images\agent-frontend.tar
echo   导出 qdrant...
docker save qdrant/qdrant:v1.17.0 -o %OUTPUT_DIR%\images\qdrant.tar

REM 复制配置文件
echo.
echo [4/5] 复制配置文件...
copy ..\docker-compose.yml %OUTPUT_DIR%\ >nul
copy ..\.env.example %OUTPUT_DIR%\config\.env.example >nul
copy nginx.conf %OUTPUT_DIR%\config\ >nul
copy entrypoint.frontend.sh %OUTPUT_DIR%\config\ >nul
copy deploy-offline.sh %OUTPUT_DIR%\ >nul
copy deploy-offline.bat %OUTPUT_DIR%\ >nul

REM 生成说明文件
echo # Desk Agent Docker 离线部署包 > %OUTPUT_DIR%\README.txt
echo. >> %OUTPUT_DIR%\README.txt
echo ## 使用方法 >> %OUTPUT_DIR%\README.txt
echo. >> %OUTPUT_DIR%\README.txt
echo 1. 将整个目录复制到目标机器 >> %OUTPUT_DIR%\README.txt
echo 2. Windows: 双击 deploy-offline.bat >> %OUTPUT_DIR%\README.txt
echo    Linux:   chmod +x deploy-offline.sh ^&^& ./deploy-offline.sh >> %OUTPUT_DIR%\README.txt
echo 3. 修改 config/.env 文件中的配置（数据库地址、LLM地址等） >> %OUTPUT_DIR%\README.txt
echo 4. 执行 docker compose up -d 启动服务 >> %OUTPUT_DIR%\README.txt
echo. >> %OUTPUT_DIR%\README.txt
echo ## 目录结构 >> %OUTPUT_DIR%\README.txt
echo. >> %OUTPUT_DIR%\README.txt
echo images/          Docker镜像tar文件 >> %OUTPUT_DIR%\README.txt
echo config/          配置文件目录 >> %OUTPUT_DIR%\README.txt
echo docker-compose.yml  服务编排文件 >> %OUTPUT_DIR%\README.txt
echo deploy-offline.bat  Windows离线部署脚本 >> %OUTPUT_DIR%\README.txt
echo deploy-offline.sh   Linux离线部署脚本 >> %OUTPUT_DIR%\README.txt

REM 压缩打包
echo.
echo [5/5] 压缩打包...
if exist %OUTPUT_FILE% del %OUTPUT_FILE%
powershell -Command "Compress-Archive -Path '%OUTPUT_DIR%' -DestinationPath '%OUTPUT_FILE%' -Force"

echo.
echo =========================================
echo   打包完成！
echo =========================================
echo.
echo 输出文件: %OUTPUT_FILE%
for %%A in (%OUTPUT_FILE%) do echo 文件大小: %%~zA 字节
echo.
echo 将 %OUTPUT_FILE% 复制到目标机器解压后，运行 deploy-offline.bat 即可部署
echo.

rmdir /s /q %OUTPUT_DIR%
pause
