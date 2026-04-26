$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  构建文档同步基础镜像 (agent-docling-sync-base)" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

docker --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: Docker 未安装或未启动" -ForegroundColor Red
    exit 1
}

$torchIndex = if ($args -contains "--gpu") { "https://download.pytorch.org/whl/cu126" } else { "https://download.pytorch.org/whl/cpu" }
$modeLabel = if ($args -contains "--gpu") { "GPU (CUDA 12.6)" } else { "CPU" }

Write-Host "构建模式: $modeLabel" -ForegroundColor Yellow
Write-Host "TORCH_INDEX: $torchIndex" -ForegroundColor Yellow
Write-Host "开始构建文档同步基础镜像（包含 docling + torch + fastembed 模型）..." -ForegroundColor Yellow
Write-Host "此过程耗时较长，请耐心等待（约 10-20 分钟）" -ForegroundColor Yellow
Write-Host ""

docker build --build-arg TORCH_INDEX=$torchIndex -f docker/Dockerfile.docling-sync.base -t agent-docling-sync-base:latest .

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "错误: 文档同步基础镜像构建失败" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host "  文档同步基础镜像构建成功！" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
Write-Host "镜像名称: agent-docling-sync-base:latest" -ForegroundColor White
Write-Host "构建模式: $modeLabel" -ForegroundColor White
Write-Host ""
Write-Host "后续步骤:" -ForegroundColor White
Write-Host "  1. 运行 docker compose --profile docling up docling-sync --build 构建并启动同步" -ForegroundColor White
Write-Host "  2. 同步完成后容器自动退出" -ForegroundColor White
Write-Host ""
