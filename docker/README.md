# Docker部署指南（外部Ollama版）

## 一、架构说明

本项目采用前后端分离架构，Docker容器内运行：
- **前端**：Vue3 + Nginx静态站点
- **后端**：FastAPI Python应用
- **Qdrant**：向量数据库

Ollama大模型服务部署在Docker外部，不包含在Docker Compose中。

## 二、部署结构

```
┌─────────────────────────────────────────────────────────┐
│                     宿主机                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐ │
│  │  Ollama  │  │   MySQL  │  │   ./data/docs/       │ │
│  │  :11434  │  │  :3306   │  │   文档目录(挂载)      │ │
│  └──────────┘  └──────────┘  │   ./agent_backend/   │ │
│                               │   configs/(挂载)      │ │
│                               └──────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    Docker网络                           │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │   frontend   │  │    backend   │  │   qdrant    │ │
│  │    :80        │◄─┤   :8000      │◄─┤  :6333      │ │
│  └──────────────┘  └──────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## 三、前置要求

### 3.1 软件要求

- Docker Desktop (Windows) 或 Docker Engine (Linux)
- Docker Compose v2+
- Ollama服务已部署并运行（端口11434）
- MySQL数据库（可选，如使用Text-to-SQL功能）

### 3.2 Ollama验证

确保Ollama服务正常运行：

```bash
curl http://localhost:11434/api/tags
```

确保已下载所需模型：

```bash
ollama list
# 如果模型不存在，执行：
ollama pull qwen2.5:7b-instruct
ollama pull qwen2.5-vl:7b-instruct
```

## 四、部署步骤

### 4.1 配置环境变量

```bash
# 复制环境变量示例文件
cp .env.example .env

# 编辑.env文件，配置必要的参数
notepad .env
```

关键配置项说明：

```env
# Ollama服务地址（容器内访问宿主机）
OLLAMA_BASE_URL=http://host.docker.internal:11434

# 如果是Linux系统，改为：
# OLLAMA_BASE_URL=http://172.17.0.1:11434

# 文本对话模型
CHAT_MODEL=qwen2.5:7b-instruct

# 视觉模型
VISION_MODEL=qwen2.5-vl:7b-instruct

# 数据库配置（如不需要SQL功能可留空）
DATABASE_URL=mysql+pymysql://user:password@host:3306/dbname
```

### 4.2 创建必要目录

```bash
# 创建文档目录（用于RAG检索）
mkdir -p data/docs

# 放入需要检索的文档（PDF、Word、图片等）
# cp your-docs/*.pdf data/docs/
```

### 4.3 构建并启动

```bash
# 构建镜像（首次运行或代码更新后）
docker compose build

# 启动所有服务
docker compose up -d

# 查看服务状态
docker compose ps
```

### 4.4 验证部署

```bash
# 检查后端健康状态
curl http://localhost:8000/api/v1/health

# 检查Qdrant服务
curl http://localhost:6333/

# 访问前端页面
# 浏览器打开 http://localhost
```

## 五、目录挂载说明

为方便更新和维护，以下目录通过volume挂载到宿主机：

| 容器内路径 | 宿主机路径 | 说明 |
|-----------|-----------|------|
| `/data/docs` | `./data/docs` | RAG文档目录，放入PDF/Word等文档 |
| `/app/configs` | `./agent_backend/configs` | 配置文件目录，包含schema_metadata.yaml |

### 5.1 schema_metadata.yaml配置

该文件定义数据库表结构和权限规则，路径：`agent_backend/configs/schema_metadata.yaml`

```yaml
version: "0.1"
db_type: "mysql"

security:
  restricted_tables:
    - admininfo
    - RoleGroupMap
    - g_adminroleright

permissions:
  - name: admin_department_scope_v1
    allowed_group_ids_sql: |
      SELECT g.id FROM s_group g ...
```

### 5.2 更新配置或文档

```bash
# 更新RAG文档后，需要重新索引（进入后端容器执行）
docker compose exec backend bash

# 在容器内执行文档索引
python -m agent_backend.rag_engine.cli --docs-dir /data/docs

# 或者使用API触发
curl -X POST http://localhost:8000/api/v1/rag/reindex
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

# 重启后端（代码更新后）
docker compose restart backend

# 重新构建（代码更新后）
docker compose build --no-cache backend
docker compose up -d

# 进入后端容器
docker compose exec backend bash

# 查看容器内文件
docker compose exec backend ls -la /app/configs/
```

## 七、端口说明

| 端口 | 服务 | 说明 |
|-----|------|------|
| 80 | frontend | 前端页面访问 |
| 8000 | backend | 后端API |
| 6333 | qdrant | Qdrant REST API |
| 6334 | qdrant | Qdrant gRPC |
| 11434 | ollama | Ollama API（宿主机） |

## 八、网络配置

### 8.1 访问宿主机Ollama

- **Windows/macOS**：使用`host.docker.internal`
- **Linux**：使用`172.17.0.1`或宿主机IP

如需修改，编辑`.env`文件：

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

### 8.2 Ollama不在本机

如果Ollama部署在远程服务器：

```env
OLLAMA_BASE_URL=http://远程IP:11434
```

确保远程Ollama服务允许外部访问（启动时加`--host 0.0.0.0`参数）。

## 九、数据持久化

| 数据类型 | 存储位置 | 说明 |
|---------|---------|------|
| 向量数据 | Docker volume `qdrant_data` | Qdrant存储的向量索引 |
| RAG文档 | `./data/docs` | 原始文档文件（需手动备份） |
| 配置文件 | `./agent_backend/configs` | YAML配置文件（需手动备份） |

### 9.1 备份向量数据

```bash
# 备份Qdrant volume
docker run --rm -v desk-agent_qdrant_data:/data -v $(pwd):/backup alpine tar czf /backup/qdrant_backup.tar.gz /data

# 恢复备份
docker run --rm -v desk-agent_qdrant_data:/data -v $(pwd):/backup alpine tar xzf /backup/qdrant_backup.tar.gz -C /
```

## 十、故障排查

### 10.1 后端无法连接Ollama

```bash
# 检查Ollama是否运行
curl http://localhost:11434/api/tags

# 检查后端日志
docker compose logs backend | grep -i ollama
```

### 10.2 Qdrant连接失败

```bash
# 检查Qdrant状态
curl http://localhost:6333/

# 检查Qdrant日志
docker compose logs qdrant
```

### 10.3 前端无法访问后端

```bash
# 检查后端是否正常运行
docker compose ps

# 检查后端健康状态
curl http://localhost:8000/api/v1/health

# 检查Nginx代理配置
docker compose logs frontend | grep -i proxy
```

### 10.4 文档RAG检索无结果

```bash
# 检查文档是否正确挂载
docker compose exec backend ls -la /data/docs/

# 检查向量数据库是否有数据
curl http://localhost:6333/collections

# 重新索引文档
docker compose exec backend python -m agent_backend.rag_engine.cli --docs-dir /data/docs
```

## 十一、环境变量完整参考

```env
# ==================== 大模型配置 ====================
OLLAMA_BASE_URL=http://host.docker.internal:11434
CHAT_MODEL=qwen2.5:7b-instruct
VISION_MODEL=qwen2.5-vl:7b-instruct

# ==================== 数据库配置 ====================
DATABASE_URL=mysql+pymysql://user:password@host:3306/dbname

# ==================== RAG配置 ====================
RAG_DOCS_DIR=./data/docs
RAG_QDRANT_URL=http://qdrant:6333
RAG_QDRANT_PATH=/app/.qdrant_local
RAG_QDRANT_COLLECTION=desk_agent_docs
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_HYBRID_ALPHA=0.7
RAG_TOP_K=5

# ==================== 其他配置 ====================
CHAT_API_TOKEN=
```

## 十二、生产环境建议

1. **安全加固**
   - 修改默认端口
   - 启用HTTPS
   - 设置`CHAT_API_TOKEN`进行接口鉴权
   - 限制数据库访问权限

2. **性能优化**
   - 配置GPU支持（如有NVIDIA GPU）
   - 调整`RAG_HYBRID_ALPHA`和`RAG_TOP_K`参数
   - 使用`--workers 4`增加后端并发

3. **监控告警**
   - 配置日志收集（ELK/Loki）
   - 监控容器健康状态
   - 设置资源限制（CPU/内存）