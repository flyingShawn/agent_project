@echo off
chcp 65001 >nul
REM Docker离线打包脚本 - Windows版本
REM 将所有镜像和配置文件打包为一个压缩包，用于内网离线部署

setlocal enabledelayedexpansion

set OUTPUT_DIR=agent-docker-offline
set OUTPUT_FILE=agent-docker-offline.zip

echo =========================================
echo   Agent Docker 离线打包脚本
echo =========================================
echo.

REM 检查Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo 错误: Docker未安装
    pause
    exit /b 1
)

REM 检查必需镜像
echo [1/6] 检查本地镜像...
set MISSING=0
for %%I in (agent-backend-base:latest agent-backend:latest agent-frontend:latest postgres:14-alpine qdrant/qdrant:v1.17.0) do (
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
    echo 部分必需镜像不存在，请先构建：
    echo   1. 运行 build-base.ps1 构建基础镜像
    echo   2. 运行 deploy.bat 构建应用镜像
    echo   3. 重新运行本打包脚本
    pause
    exit /b 1
)

REM 检查 docling-sync 镜像并询问是否包含
set DOCLING_INCLUDE=0
docker image inspect agent-docling-sync-base:latest >nul 2>&1
if not errorlevel 1 (
    docker image inspect agent-docling-sync:latest >nul 2>&1
    if not errorlevel 1 (
        echo.
        echo   检测到 docling-sync 镜像（约 12 GB，压缩后约 6 GB）
        echo   docling-sync 仅用于解析 Office/PDF 文档（.docx/.xlsx/.pdf/.pptx）
        echo   如果只有 .md/.txt 文档则不需要
        echo.
        set /p DOCLING_ANSWER=  是否将 docling-sync 镜像包含在离线包中？(y/N): 
        if /i "!DOCLING_ANSWER!"=="Y" (
            set DOCLING_INCLUDE=1
            echo   → 将包含 docling-sync 镜像
        ) else (
            echo   → 不包含 docling-sync 镜像
        )
    )
)

if !DOCLING_INCLUDE!==0 (
    echo.
    echo   未包含 docling-sync 镜像（仅 Office/PDF 文档解析需要，.md/.txt 不需要）
)

REM 创建输出目录
echo.
echo [2/6] 准备打包目录...
if exist %OUTPUT_DIR% rmdir /s /q %OUTPUT_DIR%
mkdir %OUTPUT_DIR%
mkdir %OUTPUT_DIR%\images
mkdir %OUTPUT_DIR%\config
mkdir %OUTPUT_DIR%\agent_backend

REM 导出必需镜像
echo.
echo [3/6] 导出Docker镜像（可能需要几分钟）...
echo   导出 agent-backend-base...
docker save agent-backend-base:latest -o %OUTPUT_DIR%\images\agent-backend-base.tar
echo   导出 agent-backend...
docker save agent-backend:latest -o %OUTPUT_DIR%\images\agent-backend.tar
echo   导出 agent-frontend...
docker save agent-frontend:latest -o %OUTPUT_DIR%\images\agent-frontend.tar
echo   导出 qdrant...
docker save qdrant/qdrant:v1.17.0 -o %OUTPUT_DIR%\images\qdrant.tar
echo   导出 postgres...
docker save postgres:14-alpine -o %OUTPUT_DIR%\images\postgres.tar

REM 导出可选镜像
if !DOCLING_INCLUDE!==1 (
    echo   导出 agent-docling-sync-base...
    docker save agent-docling-sync-base:latest -o %OUTPUT_DIR%\images\agent-docling-sync-base.tar
    echo   导出 agent-docling-sync...
    docker save agent-docling-sync:latest -o %OUTPUT_DIR%\images\agent-docling-sync.tar
)

REM 生成校验文件
echo.
echo [4/6] 生成镜像校验文件...
pushd %OUTPUT_DIR%\images
powershell -Command "Get-ChildItem -Filter '*.tar' | ForEach-Object { $hash = (Get-FileHash -Algorithm SHA256 $_.Name).Hash.ToLower(); \"$hash  $($_.Name)\" } | Out-File -Encoding utf8 checksums.sha256"
popd
echo   已生成 images\checksums.sha256

REM 复制配置文件
echo.
echo [5/6] 复制配置文件...
copy ..\docker-compose.yml %OUTPUT_DIR%\ >nul
copy ..\.env.example %OUTPUT_DIR%\config\.env.example >nul
xcopy ..\agent_backend\configs %OUTPUT_DIR%\agent_backend\configs\ /E /I /Y >nul
copy nginx.conf %OUTPUT_DIR%\config\ >nul
copy entrypoint.frontend.sh %OUTPUT_DIR%\config\ >nul
copy deploy-offline.sh %OUTPUT_DIR%\ >nul
copy deploy-offline.bat %OUTPUT_DIR%\ >nul

REM 生成说明文件
(
echo # Agent Docker 离线部署包
echo.
echo 本部署包包含多智能体助手系统的完整 Docker 镜像和配置文件，支持在无外网的环境中部署。
echo.
echo ## 快速开始
echo.
echo 1. 将整个目录复制到目标机器
echo 2. Windows: 双击 deploy-offline.bat
echo    Linux:   chmod +x deploy-offline.sh ^&^& ./deploy-offline.sh
echo 3. 修改 .env 文件中的配置（LLM地址、数据库地址、CORS_ORIGINS 等）
echo 4. 修改后执行: docker compose restart backend
echo.
echo ## 必须修改的配置项
echo.
echo - LLM_BASE_URL      — LLM 服务地址（如 Ollama）
echo - OLLAMA_BASE_URL    — Ollama 服务地址
echo - DB_HOST            — desk-agent 业务数据库地址
echo - TICKET_DB_HOST     — ticket-agent 业务数据库地址
echo - CORS_ORIGINS       — 前端访问地址（如 http://目标机器IP:81）
echo.
echo ## 数据目录
echo.
echo 将文档和 SQL 样本放入以下目录：
echo - data\desk-agent\docs\   — 桌面助手文档知识库（.md/.txt 等文件）
echo - data\desk-agent\sql\    — 桌面助手 SQL 样本库（.sql 文件）
echo - data\ticket-agent\docs\ — 工单助手文档知识库
echo - data\ticket-agent\sql\  — 工单助手 SQL 样本库
echo.
echo 放入文件后，执行以下命令同步到向量数据库：
echo   docker compose exec backend python scripts/sync_rag.py --target all
echo.
echo ## 目录结构
echo.
echo images\                    Docker 镜像 tar 文件
echo images\checksums.sha256    镜像文件 SHA256 校验
echo config\                    配置文件目录
echo agent_backend\configs\     智能体配置目录（agents.yaml + 各智能体子目录）
echo docker-compose.yml         服务编排文件
echo deploy-offline.bat         Windows 离线部署脚本
echo deploy-offline.sh          Linux 离线部署脚本
echo.
echo ## 访问地址
echo.
echo - 前端界面: http://目标机器IP:81
echo - 后端 API: http://目标机器IP:8000/docs
echo - Qdrant 控制台: http://目标机器IP:6333/dashboard
echo.
echo ## 校验镜像完整性
echo.
echo Linux:
echo   cd images ^&^& sha256sum -c checksums.sha256
echo Windows:
echo   在 images 目录下运行 PowerShell 校验脚本
) > %OUTPUT_DIR%\README.txt

REM 压缩打包
echo.
echo [6/6] 压缩打包...
if exist %OUTPUT_FILE% del %OUTPUT_FILE%
powershell -Command "Compress-Archive -Path '%OUTPUT_DIR%' -DestinationPath '%OUTPUT_FILE%' -Force"
if errorlevel 1 (
    echo.
    echo ⚠ 压缩失败！临时目录 %OUTPUT_DIR% 已保留，请手动压缩。
    pause
    exit /b 1
)

rmdir /s /q %OUTPUT_DIR%

echo.
echo =========================================
echo   打包完成！
echo =========================================
echo.
echo 输出文件: %OUTPUT_FILE%
for %%A in (%OUTPUT_FILE%) do echo 文件大小: %%~zA 字节
echo.
echo 包含内容:
echo   - 必需镜像: 5 个
if !DOCLING_INCLUDE!==1 (
    echo   - 可选镜像: 2 个（docling-sync）
) else (
    echo   - 可选镜像: 0 个
)
echo   - 配置文件 + 部署脚本 + SHA256 校验
echo.
echo 将 %OUTPUT_FILE% 复制到目标机器解压后，运行 deploy-offline.bat 即可部署
echo.
pause
