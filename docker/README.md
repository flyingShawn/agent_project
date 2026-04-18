# Docker 部署指南

## 一、架构说明

本项目采用前后端分离架构，Docker 容器内运行：
- **前端**：Vue 3 + Nginx 静态站点
- **后端**：FastAPI Python 应用
- **Qdrant**：向量数据库

Ollama 大模型服务部署在 Docker 外部，不包含在 Docker Compose 中。

## 二、部署结构

```
┌─────────────────────────────────────────────────────────┐
│                     宿主机                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐ │
│  │  Ollama  │  │   MySQL  │  │   ./data/desk-agent/ │ │
│  │  :11434  │  │  :3306   │  │   docs/ + sql/       │ │
│  └──────────┘  └──────────┘  │   ./agent_backend/   │ │
│                               │   configs/(挂载)      │ │
│                               └──────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    Docker 网络                           │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │   frontend   │  │    backend   │  │   qdrant    │ │
│  │    :80       │◄─┤   :8000      │◄─┤  :6333      │ │
│  │   Nginx      │  │   FastAPI    │  │  :6334      │ │
│  └──────────────┘  └──────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────┘
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
ollama pull qwen2.5:7b
ollama pull qwen2.5-vl:7b
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
CHAT_MODEL=qwen2.5:7b

# 视觉模型
VISION_MODEL=qwen2.5-vl:7b

# 数据库配置
DATABASE_URL=mysql+pymysql://user:password@host:3306/dbname?charset=utf8mb4

# 聊天历史数据库路径（容器内）
CHAT_DB_PATH=/app/data/chat_history.db
```

### 4.2 构建并启动

```bash
# 构建镜像
docker compose build

# 启动所有服务
docker compose up -d

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
# 浏览器打开 http://localhost
```

## 五、目录挂载说明

| 容器内路径 | 宿主机路径 | 说明 |
|-----------|-----------|------|
| `/data/docs` | `./data/desk-agent/docs` | 文档知识库（只读挂载） |
| `/data/sql` | `./data/desk-agent/sql` | SQL 样本库（只读挂载） |
| `/app/configs` | `./agent_backend/configs` | 配置文件（只读挂载，含 schema_metadata.yaml 和 scheduled_tasks.yaml） |
| `/app/.qdrant_local` | Docker volume `qdrant_data` | 向量数据持久化 |
| `/app/data` | Docker volume `chat_data` | 聊天历史和定时任务数据持久化 |

### 更新配置或文档

```bash
# 更新 RAG 文档后，触发重新索引
curl -X POST http://localhost:8000/api/v1/rag/sync \
  -H "Content-Type: application/json" \
  -d '{"mode": "incremental"}'

# 更新 SQL 样本库
curl -X POST http://localhost:8000/api/v1/rag/sync-sql \
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
| 80 | frontend | 前端页面访问 |
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
| 聊天历史 | Docker volume `chat_data` | 会话、消息和定时任务数据 |
| RAG 文档 | `./data/desk-agent/docs` | 原始文档文件（需手动备份） |
| SQL 样本 | `./data/desk-agent/sql` | SQL 样本文件 |
| 配置文件 | `./agent_backend/configs` | YAML 配置文件（需手动备份） |

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
# 检查文档是否正确挂载
docker compose exec backend ls -la /data/docs/

# 检查向量数据库是否有数据
curl http://localhost:6333/collections

# 触发文档同步
curl -X POST http://localhost:8000/api/v1/rag/sync \
  -H "Content-Type: application/json" \
  -d '{"mode": "incremental"}'
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
CHAT_MODEL=qwen2.5:7b
VISION_MODEL=qwen2.5-vl:7b
ENABLE_CLOUD_FALLBACK=0

# ==================== 数据库配置 ====================
DATABASE_URL=mysql+pymysql://user:password@host:3306/dbname?charset=utf8mb4
DB_TYPE=mysql
DB_HOST=localhost
DB_PORT=3306
DB_NAME=desk_management
DB_USER=root
DB_PASSWORD=your_password
SQL_MAX_ROWS=500

# ==================== RAG 配置 ====================
RAG_DOCS_DIR=/data/docs
RAG_SQL_DIR=/data/sql
RAG_QDRANT_URL=http://qdrant:6333
RAG_QDRANT_PATH=/app/.qdrant_local
RAG_QDRANT_COLLECTION=desk_agent_docs
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_HYBRID_ALPHA=0.7
RAG_TOP_K=5
RAG_CANDIDATE_K=30
RAG_VECTOR_MIN_SCORE=0.5
RAG_SQL_QDRANT_COLLECTION=desk_agent_sql
RAG_SQL_TOP_K=3
RAG_SQL_CANDIDATE_K=15
RAG_SQL_HYBRID_ALPHA=0.8

# ==================== 聊天历史 ====================
CHAT_DB_PATH=/app/data/chat_history.db
AGENT_NAME=desk-agent

# ==================== 其他配置 ====================
CHAT_API_TOKEN=
TAVILY_API_KEY=
WEB_SEARCH_MAX_RESULTS=5

# ==================== 前端配置 ====================
APP_NAME=阳途智能助手
APP_SUBTITLE=阳途智能助手为您服务
APP_WELCOME_TEXT=有什么我能帮您的呢？
APP_INPUT_PLACEHOLDER=给智能助手发消息
QUICK_OPTIONS=查看客户端在线状态,今日远程操作记录,近期开关机日志,老旧资产设备查询,部门设备数量统计,USB使用记录查询
```

## 十二、生产环境建议

1. **安全加固**
   - 修改默认端口
   - 启用 HTTPS
   - 设置 `CHAT_API_TOKEN` 进行接口鉴权
   - 限制数据库访问权限（使用只读账号）

2. **性能优化**
   - 配置 GPU 支持（如有 NVIDIA GPU）
   - 调整 `RAG_HYBRID_ALPHA` 和 `RAG_TOP_K` 参数
   - 使用 `--workers 4` 增加后端并发

3. **监控告警**
   - 配置日志收集（ELK/Loki）
   - 监控容器健康状态
   - 设置资源限制（CPU/内存）
