@echo off
chcp 65001 >nul
REM Docker离线部署脚本 - Windows版本
REM 从离线包中加载镜像并启动服务

setlocal enabledelayedexpansion

echo =========================================
echo   Agent Docker 离线部署脚本
echo =========================================
echo.

REM 检查Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo 错误: Docker未安装，请先安装Docker Desktop
    pause
    exit /b 1
)

REM 检查Docker Compose
docker compose version >nul 2>&1
if errorlevel 1 (
    echo 错误: Docker Compose未安装，请确认Docker Desktop版本是否支持
    pause
    exit /b 1
)

REM 校验镜像文件完整性
echo [1/5] 校验镜像文件完整性...
if exist images\checksums.sha256 (
    echo   发现校验文件，正在验证...
    pushd images
    powershell -Command "$hashes = Get-Content checksums.sha256; $failed = 0; foreach ($line in $hashes) { $parts = $line -split '\s+'; $expected = $parts[0]; $file = $parts[1]; if (Test-Path $file) { $actual = (Get-FileHash -Algorithm SHA256 $file).Hash.ToLower(); if ($actual -ne $expected.ToLower()) { Write-Host '  X 校验失败: ' $file; $failed = 1 } else { Write-Host '  V 校验通过: ' $file } } else { Write-Host '  X 文件不存在: ' $file; $failed = 1 } }; if ($failed -eq 1) { exit 1 } else { exit 0 }"
    if errorlevel 1 (
        echo   镜像文件校验失败，文件可能在传输过程中损坏
        echo   是否继续部署？(Y/N)
        set /p CONTINUE=
        if /i not "!CONTINUE!"=="Y" (
            echo 部署已取消
            pause
            exit /b 1
        )
    ) else (
        echo   所有镜像文件校验通过
    )
    popd
) else (
    echo   未发现校验文件，跳过完整性校验
)

REM 加载镜像
echo.
echo [2/5] 加载Docker镜像（可能需要几分钟）...
set LOAD_FAILED=0
for %%F in (images\*.tar) do (
    echo   加载 %%F...
    docker load -i "%%F"
    if errorlevel 1 (
        echo   X 加载失败: %%F
        set LOAD_FAILED=1
    )
)

if !LOAD_FAILED!==1 (
    echo.
    echo 错误: 部分镜像加载失败，请检查 tar 文件是否完整
    pause
    exit /b 1
)

REM 准备配置文件和数据目录
echo.
echo [3/5] 准备配置文件和数据目录...
if not exist config\.env (
    if exist config\.env.example (
        copy config\.env.example config\.env >nul
        echo   已从 .env.example 创建 .env，请根据实际环境修改
    ) else (
        echo   警告: 未找到 .env.example，请手动创建 config\.env
    )
) else (
    echo   已有 .env 配置文件
)

REM 复制配置文件到工作目录
if not exist .env copy config\.env .env >nul
if not exist nginx.conf copy config\nginx.conf nginx.conf >nul
if not exist entrypoint.frontend.sh copy config\entrypoint.frontend.sh entrypoint.frontend.sh >nul

REM 创建数据目录
if not exist data\desk-agent\docs mkdir data\desk-agent\docs
if not exist data\desk-agent\sql mkdir data\desk-agent\sql
if not exist data\ticket-agent\docs mkdir data\ticket-agent\docs
if not exist data\ticket-agent\sql mkdir data\ticket-agent\sql
echo   已创建数据目录:
echo     data\desk-agent\docs\   — 桌面助手文档知识库（放入 .md/.txt 等文件）
echo     data\desk-agent\sql\    — 桌面助手 SQL 样本库（放入 .sql 文件）
echo     data\ticket-agent\docs\ — 工单助手文档知识库
echo     data\ticket-agent\sql\  — 工单助手 SQL 样本库

REM 停止旧容器
echo.
echo [4/5] 停止现有容器...
docker compose down 2>nul

REM 启动服务
echo.
echo [5/5] 启动服务...
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
echo   2. 修改 CORS_ORIGINS 为实际访问地址，例如：
echo      CORS_ORIGINS=http://目标机器IP:81,http://localhost:81
echo   3. 修改后执行: docker compose restart backend
echo   4. 将文档放入 data\ 目录下对应的 docs\ 子目录
echo   5. 同步文档知识库: docker compose exec backend python scripts/sync_rag.py --target docs
echo   6. 查看日志:   docker compose logs -f backend
echo.
pause
