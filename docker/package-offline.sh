#!/bin/bash
# Docker离线打包脚本 - Linux/Mac版本
# 将所有镜像和配置文件打包为一个tar.gz，用于内网离线部署

set -e

OUTPUT_DIR="agent-docker-offline"
OUTPUT_FILE="agent-docker-offline.tar.gz"

echo "========================================="
echo "  Desk Agent Docker 离线打包脚本"
echo "========================================="
echo ""

if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装"
    exit 1
fi

echo "[1/5] 检查本地镜像..."
MISSING=0
for img in agent-backend-base:latest agent-backend:latest agent-frontend:latest qdrant/qdrant:v1.17.0; do
    if docker image inspect "$img" &> /dev/null; then
        echo "  ✓ 已有镜像: $img"
    else
        echo "  ✗ 缺少镜像: $img"
        MISSING=1
    fi
done

if [ "$MISSING" -eq 1 ]; then
    echo ""
    echo "部分镜像不存在，请先构建："
    echo "  1. 运行 build-base.sh 构建基础镜像"
    echo "  2. 运行 deploy.sh 构建应用镜像"
    echo "  3. 重新运行本打包脚本"
    exit 1
fi

echo ""
echo "[2/5] 准备打包目录..."
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/images"
mkdir -p "$OUTPUT_DIR/config"

echo ""
echo "[3/5] 导出Docker镜像（可能需要几分钟）..."
echo "  导出 agent-backend-base..."
docker save agent-backend-base:latest -o "$OUTPUT_DIR/images/agent-backend-base.tar"
echo "  导出 agent-backend..."
docker save agent-backend:latest -o "$OUTPUT_DIR/images/agent-backend.tar"
echo "  导出 agent-frontend..."
docker save agent-frontend:latest -o "$OUTPUT_DIR/images/agent-frontend.tar"
echo "  导出 qdrant..."
docker save qdrant/qdrant:v1.17.0 -o "$OUTPUT_DIR/images/qdrant.tar"

echo ""
echo "[4/5] 复制配置文件..."
cp ../docker-compose.yml "$OUTPUT_DIR/"
cp ../.env.example "$OUTPUT_DIR/config/.env.example"
cp nginx.conf "$OUTPUT_DIR/config/"
cp entrypoint.frontend.sh "$OUTPUT_DIR/config/"
cp deploy-offline.sh "$OUTPUT_DIR/"
cp deploy-offline.bat "$OUTPUT_DIR/"

cat > "$OUTPUT_DIR/README.txt" << 'EOF'
# Desk Agent Docker 离线部署包

## 使用方法

1. 将整个目录复制到目标机器
2. Windows: 双击 deploy-offline.bat
   Linux:   chmod +x deploy-offline.sh && ./deploy-offline.sh
3. 修改 config/.env 文件中的配置（数据库地址、LLM地址等）
4. 执行 docker compose up -d 启动服务

## 目录结构

images/              Docker镜像tar文件
config/              配置文件目录
docker-compose.yml   服务编排文件
deploy-offline.bat   Windows离线部署脚本
deploy-offline.sh    Linux离线部署脚本
EOF

echo ""
echo "[5/5] 压缩打包..."
rm -f "$OUTPUT_FILE"
tar -czf "$OUTPUT_FILE" "$OUTPUT_DIR"

echo ""
echo "========================================="
echo "  打包完成！"
echo "========================================="
echo ""
echo "输出文件: $OUTPUT_FILE"
echo "文件大小: $(du -h "$OUTPUT_FILE" | cut -f1)"
echo ""
echo "将 $OUTPUT_FILE 复制到目标机器解压后，运行 deploy-offline.sh 即可部署"
echo ""

rm -rf "$OUTPUT_DIR"
