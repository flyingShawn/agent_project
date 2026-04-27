#!/bin/bash
set -e

echo "========================================="
echo "  构建文档同步基础镜像 (agent-docling-sync-base)"
echo "========================================="
echo ""

if ! command -v docker &> /dev/null; then
    echo "错误: Docker 未安装或未启动"
    exit 1
fi

if [[ "$*" == *"--gpu"* ]]; then
    TORCH_INDEX="https://download.pytorch.org/whl/cu126"
    MODE_LABEL="GPU (CUDA 12.6)"
else
    TORCH_INDEX="https://download.pytorch.org/whl/cpu"
    MODE_LABEL="CPU"
fi

echo "构建模式: $MODE_LABEL"
echo "TORCH_INDEX: $TORCH_INDEX"
echo "开始构建文档同步基础镜像（包含 docling + torch + fastembed 模型）..."
echo "此过程耗时较长，请耐心等待（约 10-20 分钟）"
echo ""

docker build --build-arg TORCH_INDEX=$TORCH_INDEX -f docker/Dockerfile.docling-sync.base -t agent-docling-sync-base:latest .

echo ""
echo "========================================="
echo "  文档同步基础镜像构建成功！"
echo "========================================="
echo ""
echo "镜像名称: agent-docling-sync-base:latest"
echo "构建模式: $MODE_LABEL"
echo ""
echo "后续步骤:"
echo "  1. 运行 docker compose --profile docling up docling-sync --build 构建并启动同步"
echo "  2. 同步完成后容器自动退出"
echo ""
