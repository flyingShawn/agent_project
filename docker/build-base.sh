#!/bin/bash
set -e

echo "========================================="
echo "  构建后端基础镜像 (agent-backend-base)"
echo "========================================="
echo ""

if ! command -v docker &> /dev/null; then
    echo "错误: Docker 未安装或未启动"
    exit 1
fi

echo "开始构建基础镜像（包含系统依赖 + Python 包 + fastembed 模型）..."
echo "此过程耗时较长，请耐心等待（约 5-10 分钟）"
echo ""

docker build -f docker/Dockerfile.backend.base -t agent-backend-base:latest .

echo ""
echo "========================================="
echo "  基础镜像构建成功！"
echo "========================================="
echo ""
echo "镜像名称: agent-backend-base:latest"
echo ""
echo "后续步骤:"
echo "  1. 运行 docker compose up -d --build 构建并启动服务"
echo "  2. 代码变更时只需 docker compose up -d --build，无需重建基础镜像"
echo ""
