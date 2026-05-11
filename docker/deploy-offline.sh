#!/bin/bash
# Docker离线部署脚本 - Linux/Mac版本
# 从离线包中加载镜像并启动服务

set -e

echo "========================================="
echo "  Agent Docker 离线部署脚本"
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

echo "[1/5] 校验镜像文件完整性..."
if [ -f images/checksums.sha256 ]; then
    echo "  发现校验文件，正在验证..."
    if (cd images && sha256sum -c checksums.sha256); then
        echo "  ✓ 所有镜像文件校验通过"
    else
        echo "  ✗ 镜像文件校验失败，文件可能在传输过程中损坏"
        echo "  是否继续部署？(y/N)"
        read -r CONTINUE
        if [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ]; then
            echo "部署已取消"
            exit 1
        fi
    fi
else
    echo "  未发现校验文件，跳过完整性校验"
fi

echo ""
echo "[2/5] 加载Docker镜像（可能需要几分钟）..."
LOAD_FAILED=0
for f in images/*.tar; do
    [ -f "$f" ] || continue
    echo "  加载 $f..."
    if ! docker load -i "$f"; then
        echo "  ✗ 加载失败: $f"
        LOAD_FAILED=1
    fi
done

if [ "$LOAD_FAILED" -eq 1 ]; then
    echo ""
    echo "错误: 部分镜像加载失败，请检查 tar 文件是否完整"
    exit 1
fi

echo ""
echo "[3/5] 准备配置文件和数据目录..."
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

mkdir -p data/desk-agent/docs
mkdir -p data/desk-agent/sql
mkdir -p data/ticket-agent/docs
mkdir -p data/ticket-agent/sql
echo "  已创建数据目录:"
echo "    data/desk-agent/docs/   — 桌面助手文档知识库（放入 .md/.txt 等文件）"
echo "    data/desk-agent/sql/    — 桌面助手 SQL 样本库（放入 .sql 文件）"
echo "    data/ticket-agent/docs/ — 工单助手文档知识库"
echo "    data/ticket-agent/sql/  — 工单助手 SQL 样本库"

echo ""
echo "[4/5] 停止现有容器..."
docker compose down 2>/dev/null || true

echo ""
echo "[5/5] 启动服务..."
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
echo "  2. 修改 CORS_ORIGINS 为实际访问地址，例如："
echo "     CORS_ORIGINS=http://目标机器IP:81,http://localhost:81"
echo "  3. 修改后执行: docker compose restart backend"
echo "  4. 将文档放入 data/ 目录下对应的 docs/ 子目录"
echo "  5. 同步文档知识库: docker compose exec backend python scripts/sync_rag.py --target docs"
echo "  6. 查看日志:   docker compose logs -f backend"
echo ""
