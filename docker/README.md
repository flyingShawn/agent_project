# Docker 部署指南

## 一、架构说明

本项目采用前后端分离架构，Docker 容器内运行：
- **前端**：Vue 3 + Nginx 静态站点
- **后端**：FastAPI Python 应用
- **Qdrant**：向量数据库

Ollama 大模型服务部署在 Docker 外部，不包含在 Docker Compose 中。

## 二、部署结构

```
┌──────────────────────────────────────────────────────────────┐
│                          宿主机                               │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────────────┐ │
│  │  Ollama  │  │   MySQL  │  │  ./data/desk-agent/       │ │
│  │  :11434  │  │  :3306   │  │    docs/ + sql/           │ │
│  └──────────┘  └──────────┘  │  ./data/ticket-agent/     │ │
│                               │    docs/ + sql/           │ │
│                               │  ./agent_backend/         │ │
│                               │    configs/ (挂载)        │ │
│                               └───────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│                       Docker 网络                             │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐       │
│  │   frontend   │  │    backend   │  │   qdrant    │       │
│  │    :80       │◄─┤   :8000      │◄─┤  :6333      │       │
│  │   Nginx      │  │   FastAPI    │  │  :6334      │       │
│  └──────────────┘  └──────────────┘  └─────────────┘       │
└──────────────────────────────────────────────────────────────┘
```

## 三、前置要求

- Docker Desktop (Windows) 或 Docker Engine (Linux)
- Docker Compose v2+
- Ollama 服务已部署并运行（端口 11434）
- MySQL/PostgreSQL 数据库（如使用 Text-to-SQL 功能）

### Ollama 验证

```bash
# 检查 Ollama 是否运行
curl http://localhost:11434/api/tags

# 确认模型已下载
ollama list
ollama pull qwen3.5:9b
ollama pull qwen3:14b
```

## 四、部署步骤

### 4.1 配置环境变量

```bash
# 复制环境变量示例文件
cp .env.example .env

# 编辑 .env 文件
notepad .env
```

关键配置项：

```env
# LLM 服务地址（容器内访问宿主机）
LLM_BASE_URL=http://host.docker.internal:11434/v1

# Linux 系统改为：
# LLM_BASE_URL=http://172.17.0.1:11434/v1

# 文本对话模型
CHAT_MODEL=qwen3.5:9b

# 视觉模型
VISION_MODEL=qwen3.5:9b

# desk-agent 数据库配置
DB_HOST=192.168.1.100
DB_PORT=3306
DB_NAME=desk_management
DB_USER=root
DB_PASSWORD=your_password

# ticket-agent 数据库配置（如果与 desk-agent 不同）
TICKET_DB_HOST=192.168.1.100
TICKET_DB_PORT=3306
TICKET_DB_NAME=ticket_system
TICKET_DB_USER=root
TICKET_DB_PASSWORD=your_password

# 聊天历史数据库连接URL（PostgreSQL）
CHAT_DB_URL=postgresql+asyncpg://agent:agent123@postgres:5432/agent_chat

# Qdrant 在容器内使用服务名
RAG_QDRANT_URL=http://qdrant:6333
```

> **重要**：RAG 的文档目录（`docs_dir`、`sql_dir`）和集合名（`docs_collection`、`sql_collection`）
> 在 `agent_backend/configs/agents.yaml` 中按智能体独立配置，不需要通过环境变量设置。
> 修改 `agents.yaml` 后重启后端容器即可生效（配置文件以只读方式挂载）。

### 4.2 构建并启动

```bash
# 首次先构建主 API 基础镜像
powershell -ExecutionPolicy Bypass -File docker/build-base.ps1

# 构建并启动服务
docker compose up -d --build

# 查看服务状态
docker compose ps
```

### 4.3 验证部署

```bash
# 检查后端健康状态
curl http://localhost:8000/api/v1/health

# 检查 Qdrant 服务
curl http://localhost:6333/

# 访问前端页面
# 浏览器打开 http://localhost:81
```

## 五、目录挂载说明

| 容器内路径 | 宿主机路径 | 说明 |
|-----------|-----------|------|
| `/data/desk-agent/docs` | `./data/desk-agent/docs` | 桌面助手文档知识库（只读挂载） |
| `/data/desk-agent/sql` | `./data/desk-agent/sql` | 桌面助手SQL 样本库（只读挂载） |
| `/data/ticket-agent/docs` | `./data/ticket-agent/docs` | 工单助手文档知识库（只读挂载） |
| `/data/ticket-agent/sql` | `./data/ticket-agent/sql` | 工单助手SQL 样本库（只读挂载） |
| `/app/agent_backend/configs` | `./agent_backend/configs` | 配置文件（只读挂载，含 agents.yaml 和各智能体子目录） |
| `/qdrant/storage` | Docker volume `qdrant_data` | 向量数据持久化 |
| `/app/data` | Docker volume `chat_data` | 聊天历史、RAG状态等数据持久化 |

### 更新配置或文档

推荐使用项目自带的 `sync.cmd` 脚本（支持 Office/PDF 解析）：

```powershell
# 首次同步 Office/PDF 前先构建文档同步基础镜像
powershell -ExecutionPolicy Bypass -File docker/build-docling-sync.ps1

# 同步所有（文档 + SQL 样本）
.\scripts\sync.cmd

# 全量重建
.\scripts\sync.cmd full

# 仅同步文档知识库（自动使用 docling-sync 容器，支持 Office/PDF）
.\scripts\sync.cmd docs

# 仅同步 SQL 样本库
.\scripts\sync.cmd sql

# 本地环境运行（需安装 docling）
.\scripts\sync.cmd docs full local
```

也可直接调用 API 触发同步（仅支持 md/txt，不处理 Office/PDF）：

```bash
# 更新 desk-agent RAG 文档后，触发重新索引
curl -X POST http://localhost:8000/api/v1/desk-agent/rag/sync \
  -H "Content-Type: application/json" \
  -d '{"mode": "incremental"}'

# 更新 desk-agent SQL 样本库
curl -X POST http://localhost:8000/api/v1/desk-agent/rag/sync-sql \
  -H "Content-Type: application/json" \
  -d '{"mode": "incremental"}'

# 更新 ticket-agent SQL 样本库
curl -X POST http://localhost:8000/api/v1/ticket-agent/rag/sync-sql \
  -H "Content-Type: application/json" \
  -d '{"mode": "incremental"}'
```

## 六、常用命令

```bash
# 启动服务
docker compose up -d

# 停止服务
docker compose down

# 查看日志
docker compose logs -f

# 查看后端日志
docker compose logs -f backend

# 重启后端
docker compose restart backend

# 重新构建（代码更新后）
docker compose build --no-cache backend
docker compose up -d

# 进入后端容器
docker compose exec backend bash
```

## 七、端口说明

| 端口 | 服务 | 说明 |
|-----|------|------|
| 81 | frontend | 前端页面访问（Nginx） |
| 8000 | backend | 后端 API |
| 6333 | qdrant | Qdrant REST API |
| 6334 | qdrant | Qdrant gRPC |
| 11434 | ollama | Ollama API（宿主机外部） |

## 八、网络配置

### 访问宿主机 Ollama

- **Windows/macOS**：使用 `host.docker.internal`
- **Linux**：使用 `172.17.0.1` 或宿主机 IP

编辑 `.env` 文件：

```env
LLM_BASE_URL=http://host.docker.internal:11434/v1
```

### Ollama 不在本机

如果 Ollama 部署在远程服务器：

```env
LLM_BASE_URL=http://远程IP:11434/v1
```

确保远程 Ollama 服务允许外部访问（启动时加 `OLLAMA_HOST=0.0.0.0` 参数）。

### 容器内 Qdrant

容器内使用服务名访问 Qdrant：

```env
RAG_QDRANT_URL=http://qdrant:6333
```

## 九、数据持久化

| 数据类型 | 存储位置 | 说明 |
|---------|---------|------|
| 向量数据 | Docker volume `qdrant_data` | Qdrant 存储的向量索引 |
| 聊天历史 | Docker volume `chat_data` | 会话、消息、运维简报、RAG增量状态等 |
| RAG 文档（desk-agent） | `./data/desk-agent/docs` | 原始文档文件（需手动备份） |
| SQL 样本（desk-agent） | `./data/desk-agent/sql` | SQL 样本文件 |
| RAG 文档（ticket-agent） | `./data/ticket-agent/docs` | 原始文档文件（需手动备份） |
| SQL 样本（ticket-agent） | `./data/ticket-agent/sql` | SQL 样本文件 |
| 配置文件 | `./agent_backend/configs` | agents.yaml + 各智能体子目录（需手动备份） |

### 备份向量数据

```bash
# 备份 Qdrant volume
docker run --rm -v desk-agent_qdrant_data:/data -v $(pwd):/backup alpine tar czf /backup/qdrant_backup.tar.gz /data

# 恢复备份
docker run --rm -v desk-agent_qdrant_data:/data -v $(pwd):/backup alpine tar xzf /backup/qdrant_backup.tar.gz -C /
```

### 备份聊天历史

```bash
# 备份聊天历史 volume
docker run --rm -v desk-agent_chat_data:/data -v $(pwd):/backup alpine tar czf /backup/chat_data_backup.tar.gz /data

# 恢复备份
docker run --rm -v desk-agent_chat_data:/data -v $(pwd):/backup alpine tar xzf /backup/chat_data_backup.tar.gz -C /
```

## 十、故障排查

### 后端无法连接 Ollama

```bash
# 检查 Ollama 是否运行
curl http://localhost:11434/api/tags

# 检查后端日志
docker compose logs backend | grep -i ollama

# 确保 .env 中 LLM_BASE_URL 使用正确的宿主机地址
# Windows/macOS: http://host.docker.internal:11434/v1
# Linux: http://172.17.0.1:11434/v1
```

### Qdrant 连接失败

```bash
# 检查 Qdrant 状态
curl http://localhost:6333/

# 检查 Qdrant 日志
docker compose logs qdrant
```

### 前端无法访问后端

```bash
# 检查后端是否正常运行
docker compose ps

# 检查后端健康状态
curl http://localhost:8000/api/v1/health

# 检查 Nginx 代理配置
docker compose logs frontend | grep -i proxy
```

### 文档 RAG 检索无结果

```bash
# 检查文档是否正确挂载（按智能体分目录）
docker compose exec backend ls -la /data/desk-agent/docs/
docker compose exec backend ls -la /data/desk-agent/sql/

# 检查向量数据库是否有数据
curl http://localhost:6333/collections

# 触发文档同步（Office/PDF 需要 docling-sync 镜像）
.\scripts\sync.cmd docs

# 检查配置文件是否正确挂载
docker compose exec backend ls -la /app/agent_backend/configs/
docker compose exec backend cat /app/agent_backend/configs/agents.yaml
```

### 定时任务不执行

```bash
# 检查健康检查接口中的调度器状态
curl http://localhost:8000/api/v1/health

# 检查后端日志中的调度器启动信息
docker compose logs backend | grep -i scheduler

# 确认数据库连接正常（定时任务依赖 SQL 执行）
```

## 十一、环境变量完整参考

```env
# ==================== 大模型配置 ====================
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_API_KEY=
OLLAMA_BASE_URL=http://host.docker.internal:11434
CHAT_MODEL=qwen3.5:9b
VISION_MODEL=qwen3.5:9b

# ==================== 数据库配置（desk-agent） ====================
DB_TYPE=mysql
DB_HOST=192.168.1.100
DB_PORT=3306
DB_NAME=desk_management
DB_USER=root
DB_PASSWORD=your_password
SQL_MAX_ROWS=500

# ==================== 数据库配置（ticket-agent） ====================
TICKET_DB_HOST=192.168.1.100
TICKET_DB_PORT=3306
TICKET_DB_NAME=ticket_system
TICKET_DB_USER=root
TICKET_DB_PASSWORD=your_password

# ==================== RAG 配置 ====================
# Qdrant 连接（容器内使用服务名 qdrant）
RAG_QDRANT_URL=http://qdrant:6333
RAG_QDRANT_PATH=
RAG_QDRANT_API_KEY=
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_HYBRID_ALPHA=0.7
RAG_TOP_K=5
RAG_CANDIDATE_K=30
RAG_VECTOR_MIN_SCORE=0.5
RAG_SQL_TOP_K=3
RAG_SQL_CANDIDATE_K=15
RAG_SQL_HYBRID_ALPHA=0.8

# ==================== 聊天历史 ====================
CHAT_DB_URL=postgresql+asyncpg://agent:agent123@postgres:5432/agent_chat
CHAT_MAX_HISTORY_ROUNDS=6
CHAT_HISTORY_COMPRESS_THRESHOLD=500
CHAT_TOPIC_SHIFT_THRESHOLD=0.15

# ==================== 智能体任务服务 ====================
DESK_SERVICE_API_URL=
TICKET_SERVICE_API_URL=

# ==================== 其他配置 ====================
TAVILY_API_KEY=
WEB_SEARCH_MAX_RESULTS=5
SQL_LOG_FULL_PROMPT=true
CORS_ORIGINS=http://localhost:3000,http://localhost
EXTERNAL_ENTRY_SECRET=
EXTERNAL_ENTRY_TTL_SECONDS=28800
THIRD_PARTY_CHAT_HISTORY_BASE_URL=
THIRD_PARTY_CHAT_HISTORY_TIMEOUT_SECONDS=3

# ==================== 前端配置（VITE_ 前缀） ====================
VITE_APP_NAME=阳途智能助手
VITE_APP_SUBTITLE=阳途智能助手为您服务
VITE_APP_WELCOME_TEXT=有什么我能帮您的呢？
VITE_APP_INPUT_PLACEHOLDER=给智能助手发消息
VITE_QUICK_OPTIONS=查看客户端在线状态,今日远程操作记录,近期开关机日志,老旧资产设备查询,部门设备数量统计,USB使用记录查询
```

> **注意**：RAG 的文档目录和集合名配置在 `agents.yaml` 中按智能体独立定义，不通过环境变量设置。
> 完整的环境变量说明请参考项目根目录的 `.env.example` 文件。

## 十二、离线打包与内网部署

适用于目标机器无法访问外网（无法 `docker pull`）的场景。在有网的机器上打包，然后拷贝到内网机器部署。

### 12.1 打包（在有网机器上操作）

前置条件：已按前文步骤完成基础镜像构建和应用镜像构建。

```bash
# Linux / Mac
cd docker/
chmod +x package-offline.sh
./package-offline.sh

# Windows (PowerShell)
cd docker\
.\package-offline.bat
```

打包脚本会自动完成：
1. 检查 4 个必需镜像是否存在
2. 将镜像导出为 tar 文件
3. 复制配置文件（docker-compose.yml、.env.example、nginx.conf 等）
4. 打包为压缩文件（Linux: `.tar.gz`，Windows: `.zip`）

最终生成文件：

| 平台 | 输出文件 | 包含内容 |
|------|---------|---------|
| Linux/Mac | `agent-docker-offline.tar.gz` | 镜像 + 配置 + 部署脚本 |
| Windows | `agent-docker-offline.zip` | 镜像 + 配置 + 部署脚本 |

打包后的目录结构：

```
agent-docker-offline/
├── images/
│   ├── agent-backend-base.tar    # 后端基础镜像（Python + 依赖 + fastembed）
│   ├── agent-backend.tar         # 后端应用镜像
│   ├── agent-frontend.tar        # 前端镜像（Nginx + Vue）
│   └── qdrant.tar                # Qdrant 向量数据库
├── config/
│   ├── .env.example              # 环境变量模板
│   ├── nginx.conf                # Nginx 配置
│   └── entrypoint.frontend.sh    # 前端启动脚本
├── docker-compose.yml            # 服务编排文件
├── deploy-offline.sh             # Linux 离线部署脚本
├── deploy-offline.bat            # Windows 离线部署脚本
└── README.txt                    # 说明文件
```

> **可选**：如果需要文档同步功能（Office/PDF 解析），还需额外打包 docling-sync 镜像：
> ```bash
> docker save agent-docling-sync-base:latest -o agent-docling-sync-base.tar
> docker save agent-docling-sync:latest -o agent-docling-sync.tar
> ```
> 将这两个 tar 文件放入 `images/` 目录即可。

### 12.2 部署（在内网机器上操作）

前置条件：目标机器已安装 Docker 和 Docker Compose。

**第一步：传输文件**

将打包文件（`.tar.gz` 或 `.zip`）通过 U 盘、内网文件共享等方式拷贝到目标机器。

**第二步：解压**

```bash
# Linux
tar -xzf agent-docker-offline.tar.gz
cd agent-docker-offline/

# Windows: 右键解压 zip 文件，进入解压目录
```

**第三步：运行离线部署脚本**

```bash
# Linux / Mac
chmod +x deploy-offline.sh
./deploy-offline.sh

# Windows
.\deploy-offline.bat
```

部署脚本会自动完成：
1. 从 tar 文件加载所有 Docker 镜像（无需联网）
2. 从 `.env.example` 创建 `.env` 配置文件
3. 复制 nginx.conf 和 entrypoint 脚本到工作目录
4. 启动所有服务

**第四步：修改配置**

离线部署脚本启动后，**必须修改 `.env` 文件**中的以下配置项以匹配内网环境：

```env
# LLM 服务地址（改为内网 Ollama 地址）
LLM_BASE_URL=http://内网Ollama地址:11434/v1
OLLAMA_BASE_URL=http://内网Ollama地址:11434

# 数据库地址（改为内网 MySQL 地址）
DB_HOST=内网MySQL地址
TICKET_DB_HOST=内网MySQL地址

# 其他按需修改...
```

修改后重启后端：

```bash
docker compose restart backend
```

**第五步：验证**

```bash
# 检查服务状态
docker compose ps

# 检查后端健康
curl http://localhost:8000/api/v1/health

# 浏览器访问
# http://目标机器IP:81
```

### 12.3 常见问题

**Q: 目标机器是 Linux，但打包机器是 Windows（或反之），可以吗？**

可以。Docker 镜像本身是跨平台的（Linux 镜像）。但注意：
- 打包脚本和部署脚本要匹配平台（`.sh` 对应 Linux，`.bat` 对应 Windows）
- 如果在 Windows 上打包，部署到 Linux，解压后使用 `deploy-offline.sh`
- 如果在 Linux 上打包，部署到 Windows，解压后使用 `deploy-offline.bat`

**Q: 如何更新离线包？**

在有网机器上拉取最新代码，重新构建镜像，再运行打包脚本即可。内网机器上重新加载镜像后 `docker compose up -d` 会自动使用新镜像。

**Q: 镜像文件很大，如何减小体积？**

- `agent-backend-base.tar` 约 2-3 GB（含 Python 依赖和 fastembed 模型）
- `agent-backend.tar` 约 50-100 MB（仅应用代码）
- `agent-frontend.tar` 约 50 MB（Nginx + 静态文件）
- `qdrant.tar` 约 200 MB

如果目标机器已有相同版本的基础镜像，可以只打包应用镜像和 qdrant，跳过 `agent-backend-base.tar`。

## 十三、生产环境建议

1. **安全加固**
   - 修改默认端口
   - 启用 HTTPS
   - 限制数据库访问权限（使用只读账号）

2. **性能优化**
   - 配置 GPU 支持（如有 NVIDIA GPU）
   - 调整 `RAG_HYBRID_ALPHA` 和 `RAG_TOP_K` 参数
   - 使用 `--workers 4` 增加后端并发

3. **监控告警**
   - 配置日志收集（ELK/Loki）
   - 监控容器健康状态
   - 设置资源限制（CPU/内存）
