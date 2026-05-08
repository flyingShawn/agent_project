# Docker 配置指南

本文档涵盖 Docker 环境下的完整运维操作，包括安装、部署、日常管理、文档同步、简报生成、日志查看等。

---

## 一、Docker 安装

### 版本要求

建议安装 Docker 19.03 或更高版本，以确保：
- 支持多阶段构建（前端 Dockerfile 使用）
- 支持健康检查指令
- 与 Docker Compose 版本兼容

### 通过 yum 安装（CentOS/RHEL）

```bash
# 1. 卸载旧版本
sudo yum remove docker docker-client docker-client-latest docker-common \
    docker-latest docker-latest-logrotate docker-logrotate docker-engine

# 2. 安装依赖包
sudo yum install -y yum-utils device-mapper-persistent-data lvm2

# 3. 设置 yum 仓库（阿里云镜像）
sudo yum-config-manager \
    --add-repo \
    http://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
sudo sed -i 's/\$releasever/8/g' /etc/yum.repos.d/docker-ce.repo

# 4. 安装 Docker 引擎
sudo yum install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 如果 containerd.io 有冲突，先重置模块：
sudo yum module reset container-tools -y
sudo yum module reset docker -y
sudo yum clean all
sudo yum makecache

# 5. 启动并设置开机自启
sudo systemctl start docker
sudo systemctl enable docker

# 6. 验证安装
docker --version
docker compose version

# 7. 配置非 root 用户（可选）
sudo groupadd docker
sudo usermod -aG docker $USER
newgrp docker
```

---

## 二、首次部署

### 1. 准备配置文件

```bash
# 克隆项目代码到服务器
git clone <仓库地址>
cd agent_project

# 从模板创建环境变量文件
cp .env.example .env

# 编辑 .env，修改以下关键配置：
#   LLM_BASE_URL      — LLM 服务地址
#   LLM_API_KEY       — API 密钥
#   CHAT_MODEL         — 聊天模型名称
#   CHAT_DB_URL        — PostgreSQL 聊天历史数据库连接URL
#   DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD — 业务数据库连接
#   HOST_DOCS_DIR      — 桌面助手文档目录
#   HOST_SQL_DIR       — 桌面助手 SQL 样本目录
```

### 2. 构建基础镜像

基础镜像包含系统依赖和 Python 包，构建耗时较长（5-10 分钟），**仅在依赖变更时需要重建**。

```bash
# 构建后端基础镜像（必须）
# Windows:
powershell -ExecutionPolicy Bypass -File docker/build-base.ps1
# Linux/Mac:
bash docker/build-base.sh

# 构建文档同步基础镜像（可选，需要同步 Office/PDF 文档时才需要）
# Windows CPU 模式:
powershell -ExecutionPolicy Bypass -File docker/build-docling-sync.ps1
# Windows GPU 模式:
powershell -ExecutionPolicy Bypass -File docker/build-docling-sync.ps1 --gpu
# Linux/Mac CPU 模式:
bash docker/build-docling-sync.sh
# Linux/Mac GPU 模式:
bash docker/build-docling-sync.sh --gpu
```

### 3. 启动服务

```bash
# 构建应用镜像并启动所有服务
docker compose up -d --build

# 或者使用一键部署脚本（自动检查 .env、构建镜像、启动服务）
# Windows:
docker\deploy.bat
# Linux/Mac:
bash docker/deploy.sh
```

### 4. 验证服务状态

```bash
# 查看所有容器状态
docker compose ps

# 健康检查
curl http://localhost:8000/api/v1/health

# 访问地址
# 前端界面:    http://localhost:81
# 后端 API 文档: http://localhost:8000/docs
# Qdrant 控制台: http://localhost:6333/dashboard
```

---

## 三、服务管理

### 服务架构

项目包含 5 个 Docker 服务：

| 服务 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| backend | agent-backend | 8000 | 后端 API（FastAPI + Uvicorn） |
| frontend | agent-frontend | 81→80 | 前端 UI（Nginx + Vue） |
| postgres | agent-postgres | 5432 | PostgreSQL 聊天历史数据库 |
| qdrant | agent-qdrant | 6333/6334 | 向量数据库 |
| docling-sync | agent-docling-sync | — | 文档同步（按需启动，完成后自动退出） |

### 启动 / 停止 / 重启

```bash
# 启动所有服务
docker compose up -d

# 停止所有服务
docker compose down

# 重启所有服务
docker compose restart

# 仅启动/重启某个服务
docker compose up -d backend
docker compose restart backend

# 停止但保留数据（不删除容器）
docker compose stop

# 停止并删除容器（数据卷保留）
docker compose down

# 停止并删除容器和数据卷（⚠️ 会清除聊天记录和向量数据）
docker compose down -v
```

### 查看服务状态

```bash
# 查看所有容器状态
docker compose ps

# 查看某个服务详细信息
docker compose ps backend

# 查看容器资源占用
docker stats --no-stream
```

---

## 四、代码变更后重建

项目采用**分层镜像策略**，代码变更只需重建应用镜像（秒级完成），无需重建基础镜像。

### 仅代码变更（最常见）

```bash
# 重建并启动（自动检测变更的层，未变更的层使用缓存）
docker compose up -d --build

# 仅重建后端
docker compose up -d --build backend

# 仅重建前端
docker compose up -d --build frontend
```

### 依赖变更（requirements.txt 变更）

```bash
# 1. 重建后端基础镜像
# Windows:
powershell -ExecutionPolicy Bypass -File docker/build-base.ps1
# Linux/Mac:
bash docker/build-base.sh

# 2. 重建并启动应用
docker compose up -d --build
```

### docling 依赖变更（requirements-docling.txt 变更）

```bash
# 1. 重建文档同步基础镜像
# Windows:
powershell -ExecutionPolicy Bypass -File docker/build-docling-sync.ps1
# Linux/Mac:
bash docker/build-docling-sync.sh

# 2. 下次执行文档同步时会自动重建应用镜像
```

### 配置文件变更（.env 或 configs/ 目录）

```bash
# .env 变更后，重启服务即可（无需重建镜像）
docker compose up -d

# configs/ 目录是挂载的，修改后重启后端生效
docker compose restart backend
```

---

## 五、文档知识库同步

文档同步使用 `docling-sync` 容器，支持 Office（docx/xlsx/pptx）、PDF、Markdown 等格式的解析、分块和向量化。该容器**日常不启动**，仅在需要同步时按需运行，完成后自动退出。

### 使用同步脚本（推荐）

```bash
# 同步所有（文档知识库 + SQL 样本库），增量模式
.\scripts\sync.cmd

# 仅同步文档知识库
.\scripts\sync.cmd docs

# 仅同步 SQL 样本库
.\scripts\sync.cmd sql

# 指定智能体同步
.\scripts\sync.cmd desk-agent
.\scripts\sync.cmd ticket-agent

# 全量重建文档知识库（清除旧数据重新导入）
.\scripts\sync.cmd desk-agent docs full

# 指定智能体 + 仅SQL + 增量
.\scripts\sync.cmd ticket-agent sql inc

# 本地模式运行（不用 Docker，需本地安装 Python 和依赖）
.\scripts\sync.cmd desk-agent docs full local
```

### 直接使用 Docker Compose 命令

```bash
# 同步文档知识库（增量，所有智能体）
docker compose --profile docling up docling-sync --build --force-recreate

# 同步文档知识库（全量重建）
SYNC_MODE=full docker compose --profile docling up docling-sync --build --force-recreate

# 仅同步指定智能体的文档
SYNC_TARGET=docs SYNC_AGENT_TYPE=desk-agent docker compose --profile docling up docling-sync --build --force-recreate

# 同步 SQL 样本库（在 backend 容器内执行，不需要 docling）
docker compose up -d qdrant backend
docker compose exec backend python scripts/sync_rag.py --target sql --mode incremental

# 全量重建 SQL 样本库
docker compose exec backend python scripts/sync_rag.py --target sql --mode full

# 指定智能体同步 SQL
docker compose exec backend python scripts/sync_rag.py --target sql --mode incremental --agent-type ticket-agent
```

### 同步模式说明

| 模式 | 参数 | 说明 |
|------|------|------|
| 增量同步 | `--mode incremental`（默认） | 仅处理新增或修改的文件（基于 SHA256 哈希检测） |
| 全量重建 | `--mode full` | 清除向量集合重新导入所有文件 |

### 同步目标说明

| 目标 | 参数 | 说明 |
|------|------|------|
| 全部 | `--target all`（默认） | 同时同步文档知识库和 SQL 样本库 |
| 文档 | `--target docs` | 仅同步文档知识库（需要 docling-sync 容器） |
| SQL | `--target sql` | 仅同步 SQL 样本库（在 backend 容器内执行） |

### 检查同步结果

```bash
# 查看 docling-sync 容器退出码（0 表示成功）
docker inspect agent-docling-sync --format "{{.State.ExitCode}}"

# 查看同步日志
docker compose logs docling-sync
```

---

## 六、运维简报管理

运维简报支持两种触发方式：**定时自动生成**和**手动触发生成**。

### 手动触发简报生成

#### 使用脚本（推荐）

```bash
# Docker 模式 — 手动生成 desk-agent 简报
.\scripts\ops_report_docker.cmd

# Docker 模式 — 手动生成指定智能体简报
.\scripts\ops_report_docker.cmd ticket-agent

# Docker 模式 — 获取最新简报
.\scripts\ops_report_docker.cmd desk-agent latest

# Docker 模式 — 列出简报
.\scripts\ops_report_docker.cmd desk-agent list

# 本地模式 — 直接调用 API（需后端服务运行在 8000 端口）
.\scripts\ops_report.cmd
.\scripts\ops_report.cmd desk-agent latest
.\scripts\ops_report.cmd desk-agent list

# 本地模式 — 指定服务地址
.\scripts\ops_report.cmd run http://192.168.1.149:8000
```

#### 使用 curl 命令

```bash
# 手动触发生成简报
curl -X POST http://localhost:8000/api/v1/desk-agent/ops/reports/run

# 获取最新简报
curl http://localhost:8000/api/v1/desk-agent/ops/reports/latest

# 列出简报（支持分页和未读筛选）
curl "http://localhost:8000/api/v1/desk-agent/ops/reports?limit=20&unread_only=false"

# 获取指定简报详情
curl http://localhost:8000/api/v1/desk-agent/ops/reports/{report_id}

# 标记简报为已读
curl -X PUT http://localhost:8000/api/v1/desk-agent/ops/reports/{report_id}/read
```

#### 使用 docker compose exec

```bash
# 在 backend 容器内直接调用本地 API 触发简报生成
docker compose exec -T backend python -c "
import urllib.request
req = urllib.request.Request(
    'http://localhost:8000/api/v1/desk-agent/ops/reports/run',
    data=b'{}',
    headers={'Content-Type': 'application/json'},
    method='POST'
)
with urllib.request.urlopen(req) as resp:
    print(resp.read().decode())
"
```

### 定时自动生成

应用启动时会自动加载 `configs/{agent_type}/ops_reports.yaml` 中的简报配置，按 `interval_seconds` 间隔定时生成。默认配置为每 2 小时自动生成一次。只要 Docker 容器保持运行，无需手动干预。

如需调整频率，修改 `configs/desk-agent/ops_reports.yaml` 中的 `interval_seconds` 值，然后重启后端：

```bash
docker compose restart backend
```

---

## 七、日志查看

### 查看服务日志

```bash
# 查看所有服务日志
docker compose logs

# 查看后端日志（最常用）
docker compose logs backend

# 查看前端日志
docker compose logs frontend

# 查看 Qdrant 日志
docker compose logs qdrant

# 查看 PostgreSQL 日志
docker compose logs postgres

# 查看文档同步日志
docker compose logs docling-sync
```

### 实时跟踪日志

```bash
# 实时跟踪后端日志（推荐）
docker compose logs -f backend

# 实时跟踪 + 显示最近 500 行
docker compose logs --tail 500 -f backend

# 不带前缀 + 最近 500 行 + 实时跟踪（推荐格式）
docker compose logs --no-log-prefix --tail 500 -f backend
```

### 过滤日志

```bash
# 查看最近 100 行
docker compose logs --tail 100 backend

# 查看指定时间之后的日志
docker compose logs --since "2024-01-01T00:00:00" backend

# 查看最近 30 分钟的日志
docker compose logs --since 30m backend

# 查看最近 2 小时的日志
docker compose logs --since 2h backend

# 带时间戳显示
docker compose logs -t backend
```

---

## 八、数据管理

### 数据卷说明

| 数据卷 | 挂载点 | 用途 | 持久化 |
|--------|--------|------|--------|
| `pg_data` | `/var/lib/postgresql/data` | PostgreSQL 聊天历史数据库 | ✅ |
| `qdrant_data` | `/qdrant/storage` | 向量数据 | ✅ |
| `${HOST_DOCS_DIR}` | `/data/desk-agent/docs` | 桌面助手文档知识库 | 宿主机目录 |
| `${HOST_SQL_DIR}` | `/data/desk-agent/sql` | 桌面助手 SQL 样本 | 宿主机目录 |
| `${TICKET_HOST_DOCS_DIR}` | `/data/ticket-agent/docs` | 工单助手文档知识库 | 宿主机目录 |
| `${TICKET_HOST_SQL_DIR}` | `/data/ticket-agent/sql` | 工单助手 SQL 样本 | 宿主机目录 |
| `${CONFIG_DIR}` | `/app/configs` | 智能体配置文件 | 宿主机目录 |

### 数据卷操作

```bash
# 查看所有数据卷
docker volume ls

# 查看数据卷详情
docker volume inspect agent_project_pg_data
docker volume inspect agent_project_qdrant_data

# 清除聊天历史数据库（⚠️ 不可恢复）
docker compose down
docker volume rm agent_project_pg_data
docker compose up -d

# 清除向量数据（⚠️ 需要重新同步文档）
docker compose down
docker volume rm agent_project_qdrant_data
docker compose up -d
.\scripts\sync.cmd desk-agent docs full
```

### 进入容器调试

```bash
# 进入后端容器
docker compose exec backend bash

# 进入后端容器并执行单条命令
docker compose exec backend python -c "print('hello')"

# 进入 Qdrant 容器
docker compose exec qdrant sh

# 进入 PostgreSQL 容器
docker compose exec postgres psql -U agent -d agent_chat

# 以 root 身份进入容器
docker compose exec -u root backend bash
```

---

## 九、常见运维操作

### 健康检查

```bash
# 后端健康检查
curl http://localhost:8000/api/v1/health

# 查看容器健康状态
docker compose ps
# 关注 STATUS 列是否显示 "healthy"
```

### 更新配置后生效

| 变更内容 | 操作 |
|----------|------|
| `.env` 环境变量 | `docker compose up -d`（重新创建容器） |
| `configs/` 配置 YAML | `docker compose restart backend` |
| 后端代码 | `docker compose up -d --build backend` |
| 前端代码 | `docker compose up -d --build frontend` |
| Python 依赖 | 先重建基础镜像，再 `docker compose up -d --build` |

### 清理磁盘空间

```bash
# 查看 Docker 磁盘占用
docker system df

# 清理未使用的镜像、容器、网络
docker system prune

# 清理所有未使用资源（包括数据卷，⚠️ 谨慎使用）
docker system prune -a --volumes

# 仅清理悬空镜像（无标签的旧镜像）
docker image prune

# 删除旧版本的基础镜像
docker image ls | grep agent-backend-base
docker rmi <旧镜像ID>
```

### 查看 Ollama 连接状态

```bash
# 在容器内测试 Ollama 连通性
docker compose exec backend python -c "
import urllib.request
try:
    resp = urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=5)
    print('Ollama 连接正常')
    print(resp.read().decode()[:200])
except Exception as e:
    print(f'Ollama 连接失败: {e}')
"
```

---

## 十、注意事项

- **Ollama 大模型服务**需在 Docker 外部部署，通过 `host.docker.internal`（Windows/macOS）或宿主机 IP（Linux）访问
- Linux 服务器需修改 `.env` 中的 `LLM_BASE_URL` 和 `OLLAMA_BASE_URL`，使用宿主机 IP 而非 `host.docker.internal`
- 确保服务器资源充足，特别是 Qdrant 向量数据库和 LLM 服务对内存要求较高
- 文档同步容器（docling-sync）日常不启动，仅同步文档时通过 `--profile docling` 按需运行
- 配置文件（`configs/`）以只读方式挂载，修改后需重启后端生效
- 数据卷（`pg_data`、`qdrant_data`）在 `docker compose down` 时不会删除，需显式使用 `-v` 参数才会清除
- PostgreSQL 聊天历史数据库默认用户 `agent`、密码 `agent123`、数据库 `agent_chat`，可通过 `.env` 中的 `PG_USER`/`PG_PASSWORD`/`PG_DB` 自定义
