#!/bin/bash
# Docker离线打包脚本 - Linux/Mac版本
# 将所有镜像和配置文件打包为一个tar.gz，用于内网离线部署

set -e

OUTPUT_DIR="agent-docker-offline"
OUTPUT_FILE="agent-docker-offline.tar.gz"

REQUIRED_IMAGES=(
    "agent-backend-base:latest"
    "agent-backend:latest"
    "agent-frontend:latest"
    "postgres:14-alpine"
    "qdrant/qdrant:v1.17.0"
)

echo "========================================="
echo "  Agent Docker 离线打包脚本"
echo "========================================="
echo ""

if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装"
    exit 1
fi

echo "[1/6] 检查本地镜像..."
MISSING=0
for img in "${REQUIRED_IMAGES[@]}"; do
    if docker image inspect "$img" &> /dev/null; then
        echo "  ✓ 已有镜像: $img"
    else
        echo "  ✗ 缺少镜像: $img"
        MISSING=1
    fi
done

if [ "$MISSING" -eq 1 ]; then
    echo ""
    echo "部分必需镜像不存在，请先构建："
    echo "  1. 运行 build-base.sh 构建基础镜像"
    echo "  2. 运行 deploy.sh 构建应用镜像"
    echo "  3. 重新运行本打包脚本"
    exit 1
fi

DOCLING_AVAILABLE=0
DOCLING_INCLUDE=0
if docker image inspect "agent-docling-sync-base:latest" &> /dev/null && docker image inspect "agent-docling-sync:latest" &> /dev/null; then
    DOCLING_AVAILABLE=1
    echo ""
    echo "  检测到 docling-sync 镜像（约 12 GB，压缩后约 6 GB）"
    echo "  docling-sync 仅用于解析 Office/PDF 文档（.docx/.xlsx/.pdf/.pptx）"
    echo "  如果只有 .md/.txt 文档则不需要"
    echo ""
    read -p "  是否将 docling-sync 镜像包含在离线包中？(y/N): " DOCLING_ANSWER
    if [ "$DOCLING_ANSWER" = "y" ] || [ "$DOCLING_ANSWER" = "Y" ]; then
        DOCLING_INCLUDE=1
        echo "  → 将包含 docling-sync 镜像"
    else
        echo "  → 不包含 docling-sync 镜像"
    fi
else
    echo ""
    echo "  未检测到 docling-sync 镜像（仅 Office/PDF 文档解析需要，.md/.txt 不需要）"
fi

echo ""
echo "[2/6] 准备打包目录..."
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/images"
mkdir -p "$OUTPUT_DIR/config"
mkdir -p "$OUTPUT_DIR/agent_backend"

echo ""
echo "[3/6] 导出Docker镜像（可能需要几分钟）..."
echo "  导出 agent-backend-base..."
docker save agent-backend-base:latest -o "$OUTPUT_DIR/images/agent-backend-base.tar"
echo "  导出 agent-backend..."
docker save agent-backend:latest -o "$OUTPUT_DIR/images/agent-backend.tar"
echo "  导出 agent-frontend..."
docker save agent-frontend:latest -o "$OUTPUT_DIR/images/agent-frontend.tar"
echo "  导出 qdrant..."
docker save qdrant/qdrant:v1.17.0 -o "$OUTPUT_DIR/images/qdrant.tar"
echo "  导出 postgres..."
docker save postgres:14-alpine -o "$OUTPUT_DIR/images/postgres.tar"

if [ "$DOCLING_INCLUDE" -eq 1 ]; then
    echo "  导出 agent-docling-sync-base..."
    docker save agent-docling-sync-base:latest -o "$OUTPUT_DIR/images/agent-docling-sync-base.tar"
    echo "  导出 agent-docling-sync..."
    docker save agent-docling-sync:latest -o "$OUTPUT_DIR/images/agent-docling-sync.tar"
fi

echo ""
echo "[4/6] 生成镜像校验文件..."
(cd "$OUTPUT_DIR/images" && sha256sum *.tar > checksums.sha256)
echo "  已生成 images/checksums.sha256"

echo ""
echo "[5/6] 复制配置文件..."
cp ../docker-compose.yml "$OUTPUT_DIR/"
cp ../.env.example "$OUTPUT_DIR/config/.env.example"
cp -R ../agent_backend/configs "$OUTPUT_DIR/agent_backend/"
cp nginx.conf "$OUTPUT_DIR/config/"
cp entrypoint.frontend.sh "$OUTPUT_DIR/config/"
cp deploy-offline.sh "$OUTPUT_DIR/"
cp deploy-offline.bat "$OUTPUT_DIR/"

cat > "$OUTPUT_DIR/README.txt" << 'EOF'
# Agent Docker 离线部署包

本部署包包含多智能体助手系统的完整 Docker 镜像和配置文件，支持在无外网的环境中部署。

## 快速开始

1. 将整个目录复制到目标机器
2. Windows: 双击 deploy-offline.bat
   Linux:   chmod +x deploy-offline.sh && ./deploy-offline.sh
3. 修改 .env 文件中的配置（LLM地址、数据库地址、CORS_ORIGINS 等）
4. 修改后执行: docker compose restart backend

## 必须修改的配置项

- LLM_BASE_URL      — LLM 服务地址（如 Ollama）
- OLLAMA_BASE_URL    — Ollama 服务地址
- DB_HOST            — desk-agent 业务数据库地址
- TICKET_DB_HOST     — ticket-agent 业务数据库地址
- CORS_ORIGINS       — 前端访问地址（如 http://目标机器IP:81）

## 数据目录

将文档和 SQL 样本放入以下目录：
- data/desk-agent/docs/   — 桌面助手文档知识库（.md/.txt 等文件）
- data/desk-agent/sql/    — 桌面助手 SQL 样本库（.sql 文件）
- data/ticket-agent/docs/ — 工单助手文档知识库
- data/ticket-agent/sql/  — 工单助手 SQL 样本库

放入文件后，执行以下命令同步到向量数据库：
  docker compose exec backend python scripts/sync_rag.py --target all

## 目录结构

images/                    Docker 镜像 tar 文件
images/checksums.sha256    镜像文件 SHA256 校验
config/                    配置文件目录
agent_backend/configs/     智能体配置目录（agents.yaml + 各智能体子目录）
docker-compose.yml         服务编排文件
deploy-offline.bat         Windows 离线部署脚本
deploy-offline.sh          Linux 离线部署脚本

## 访问地址

- 前端界面: http://目标机器IP:81
- 后端 API: http://目标机器IP:8000/docs
- Qdrant 控制台: http://目标机器IP:6333/dashboard

## 校验镜像完整性

Linux:
  cd images && sha256sum -c checksums.sha256
Windows:
  在 images 目录下运行 PowerShell 校验脚本
EOF

echo ""
echo "[6/6] 压缩打包..."
rm -f "$OUTPUT_FILE"
if tar -czf "$OUTPUT_FILE" "$OUTPUT_DIR"; then
    rm -rf "$OUTPUT_DIR"
else
    echo ""
    echo "⚠ 压缩失败！临时目录 $OUTPUT_DIR 已保留，请手动压缩："
    echo "  tar -czf $OUTPUT_FILE $OUTPUT_DIR"
    exit 1
fi

echo ""
echo "========================================="
echo "  打包完成！"
echo "========================================="
echo ""
echo "输出文件: $OUTPUT_FILE"
echo "文件大小: $(du -h "$OUTPUT_FILE" | cut -f1)"
echo ""
echo "包含内容:"
echo "  - 必需镜像: 5 个"
if [ "$DOCLING_INCLUDE" -eq 1 ]; then
echo "  - 可选镜像: 2 个（docling-sync）"
else
echo "  - 可选镜像: 0 个"
fi
echo "  - 配置文件 + 部署脚本 + SHA256 校验"
echo ""
echo "将 $OUTPUT_FILE 复制到目标机器解压后，运行 deploy-offline.sh 即可部署"
echo ""
