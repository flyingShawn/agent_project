$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  构建后端基础镜像 (agent-backend-base)" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

docker --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: Docker 未安装或未启动" -ForegroundColor Red
    exit 1
}

Write-Host "开始构建基础镜像（包含系统依赖 + Python 包 + fastembed 模型）..." -ForegroundColor Yellow
Write-Host "此过程耗时较长，请耐心等待（约 5-10 分钟）" -ForegroundColor Yellow
Write-Host ""

docker build -f docker/Dockerfile.backend.base -t agent-backend-base:latest .

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "错误: 基础镜像构建失败" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host "  基础镜像构建成功！" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
Write-Host "镜像名称: agent-backend-base:latest" -ForegroundColor White
Write-Host ""
Write-Host "后续步骤:" -ForegroundColor White
Write-Host "  1. 运行 docker compose up -d --build 构建并启动服务" -ForegroundColor White
Write-Host "  2. 代码变更时只需 docker compose up -d --build，无需重建基础镜像" -ForegroundColor White
Write-Host ""
