#!/bin/bash
# Docker离线部署脚本 - Linux/Mac版本
# 从离线包中加载镜像并启动服务

set -e

echo "========================================="
echo "  Desk Agent Docker 离线部署脚本"
echo "========================================="
echo ""

if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装，请先安装Docker"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "错误: Docker Compose未安装"
    exit 1
fi

echo "[1/4] 加载Docker镜像（可能需要几分钟）..."
for f in images/*.tar; do
    echo "  加载 $f..."
    docker load -i "$f"
done

echo ""
echo "[2/4] 准备配置文件..."
if [ ! -f config/.env ]; then
    if [ -f config/.env.example ]; then
        cp config/.env.example config/.env
        echo "  已从 .env.example 创建 .env，请根据实际环境修改"
    else
        echo "  警告: 未找到 .env.example，请手动创建 config/.env"
    fi
else
    echo "  已有 .env 配置文件"
fi

if [ ! -f .env ]; then
    cp config/.env .env
fi
if [ ! -f nginx.conf ]; then
    cp config/nginx.conf nginx.conf
fi
if [ ! -f entrypoint.frontend.sh ]; then
    cp config/entrypoint.frontend.sh entrypoint.frontend.sh
    chmod +x entrypoint.frontend.sh
fi

echo ""
echo "[3/4] 停止现有容器..."
docker compose down 2>/dev/null || true

echo ""
echo "[4/4] 启动服务..."
docker compose up -d

echo ""
echo "等待服务启动..."
sleep 10

echo ""
echo "========================================="
echo "  部署完成！"
echo "========================================="
echo ""
echo "访问地址："
echo "  - 前端界面: http://localhost:81"
echo "  - 后端API:  http://localhost:8000/docs"
echo ""
echo "重要提醒："
echo "  1. 请修改 .env 文件中的数据库地址、LLM地址等配置"
echo "  2. 修改后执行: docker compose restart backend"
echo "  3. 查看日志:   docker compose logs -f backend"
echo ""
