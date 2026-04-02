#!/bin/bash
# Docker快速部署脚本 - Linux/Mac版本

set -e

echo "========================================="
echo "  Desk Agent Docker 快速部署脚本"
echo "========================================="
echo ""

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装，请先安装Docker"
    echo "安装指南: https://docs.docker.com/get-docker/"
    exit 1
fi

# 检查Docker Compose是否安装
if ! command -v docker-compose &> /dev/null; then
    echo "错误: Docker Compose未安装，请先安装Docker Compose"
    echo "安装指南: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✓ Docker版本: $(docker --version)"
echo "✓ Docker Compose版本: $(docker-compose --version)"
echo ""

# 检查.env文件
if [ ! -f .env ]; then
    echo "⚠ 未找到.env文件，正在从.env.example创建..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✓ 已创建.env文件，请根据需要修改配置"
    else
        echo "错误: 未找到.env.example文件"
        exit 1
    fi
else
    echo "✓ 找到.env配置文件"
fi

echo ""
echo "========================================="
echo "  开始构建和启动服务..."
echo "========================================="
echo ""

# 停止旧容器
echo "1. 停止现有容器..."
docker-compose down 2>/dev/null || true

# 构建镜像
echo ""
echo "2. 构建Docker镜像..."
docker-compose build

# 启动服务
echo ""
echo "3. 启动服务..."
docker-compose up -d

# 等待服务启动
echo ""
echo "4. 等待服务启动..."
sleep 10

# 检查服务状态
echo ""
echo "5. 检查服务状态..."
docker-compose ps

# 健康检查
echo ""
echo "6. 执行健康检查..."
if curl -f http://localhost:8000/api/v1/health &> /dev/null; then
    echo "✓ 后端服务正常"
else
    echo "⚠ 后端服务可能未完全启动，请稍后检查"
fi

if curl -f http://localhost/ &> /dev/null; then
    echo "✓ 前端服务正常"
else
    echo "⚠ 前端服务可能未完全启动，请稍后检查"
fi

echo ""
echo "========================================="
echo "  部署完成！"
echo "========================================="
echo ""
echo "访问地址："
echo "  - 前端界面: http://localhost"
echo "  - 后端API: http://localhost:8000/docs"
echo "  - Qdrant控制台: http://localhost:6333/dashboard"
echo ""
echo "常用命令："
echo "  - 查看日志: docker-compose logs -f"
echo "  - 停止服务: docker-compose down"
echo "  - 重启服务: docker-compose restart"
echo ""
