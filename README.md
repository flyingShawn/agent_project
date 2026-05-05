# 阳途智能助手

多智能体架构的 AI 助手系统，支持通过配置文件快速创建新的智能体。

## 架构

```
agent_backend/          Python 后端（FastAPI）
agent_frontend/         Vue 3 前端
docker/                 Docker 部署配置
scripts/                工具脚本
docs/                   项目文档
data/                   运行时数据（每个智能体独立子目录）
```

### 多智能体架构

通过 `agents.yaml` 总控配置管理所有智能体，每个智能体拥有独立的数据库、RAG 集合和提示词配置。

- `configs/agents.yaml` — 总控配置
- `configs/{agent_type}/` — 每个智能体的专属配置（prompts.yaml、schema_metadata.yaml、ops_reports.yaml）
- API 路由使用 `/{agent_type}/` 前缀区分不同智能体

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- Ollama（本地大模型）
- MySQL/PostgreSQL（业务数据库）

### 本地启动

```bash
# 1. 配置环境变量
copy .env.example .env
# 编辑 .env，配置数据库连接和模型名称

# 2. 安装后端依赖
pip install -r requirements.txt

# 3. 启动 Qdrant（向量数据库）
docker compose up -d qdrant

# 4. 启动后端
python -m uvicorn agent_backend.main:app --host 0.0.0.0 --port 8000

# 5. 启动前端
cd agent_frontend
npm install
npm run dev
```

访问 `http://localhost:3000`

### Docker 部署

```bash
# 构建并启动所有服务
docker compose up -d

# 仅启动后端和向量数据库
docker compose up -d backend qdrant
```

详见 [Docker安装指南.md](docs/Docker安装指南.md)

## 常用命令

### 知识库同步

```bash
# 本地模式
python scripts/sync.py                        # 默认增量同步所有
python scripts/sync.py desk-agent             # 同步指定智能体
python scripts/sync.py ticket-agent docs      # 只同步文档
python scripts/sync.py desk-agent sql full    # 全量同步 SQL
python scripts/sync.py full                   # 旧格式仍兼容

# Docker 模式
.\scripts\sync.cmd                            # 默认增量同步所有
.\scripts\sync.cmd desk-agent                 # 同步指定智能体
.\scripts\sync.cmd ticket-agent docs full     # 全量同步文档
.\scripts\sync.cmd docs full                  # 旧格式仍兼容
.\scripts\sync.cmd desk-agent docs docker     # 显式指定 docker 模式
.\scripts\sync.cmd sql local                  # 显式指定本地模式
```

### 运维简报

```bash
# 本地模式
.\scripts\ops_report.cmd desk-agent           # 手动触发
.\scripts\ops_report.cmd desk-agent latest    # 查看最新
.\scripts\ops_report.cmd desk-agent list      # 列表

# Docker 模式
.\scripts\ops_report_docker.cmd desk-agent

# API 方式
curl -X POST http://localhost:8000/api/v1/desk-agent/ops/reports/run
```

## 新增智能体

只需三步：

1. 在 `configs/agents.yaml` 添加配置
2. 在 `configs/` 下创建同名子目录，放入 prompts.yaml 和 schema_metadata.yaml
3. 重启后端

```bash
# 示例：新增资产助手
mkdir agent_backend/configs/asset-agent
cp agent_backend/configs/desk-agent/prompts.yaml agent_backend/configs/asset-agent/
cp agent_backend/configs/desk-agent/schema_metadata.yaml agent_backend/configs/asset-agent/
# 编辑 agents.yaml 添加 asset-agent 配置
```

## 配置说明

项目采用三层配置架构：

| 层级 | 来源 | 说明 |
|------|------|------|
| 1 | `.env` | 全局默认值 |
| 2 | `agents.yaml` | 智能体覆盖值（支持 `${ENV_VAR}` 引用 .env） |
| 3 | `configs/{agent_type}/` | 专属 YAML 配置 |

详见 [配置文件说明.md](docs/配置文件说明.md)

## 文档

| 文档 | 说明 |
|------|------|
| [配置文件说明.md](docs/配置文件说明.md) | 完整配置项说明 |
| [快速测试指南.md](docs/快速测试指南.md) | 核心功能验证 |
| [ops-report-flow-brief.md](docs/ops-report-flow-brief.md) | 运维简报流程 |
| [Docker安装指南.md](docs/Docker安装指南.md) | Docker 部署 |
| [Node.js安装指南.md](docs/Node.js安装指南.md) | Node.js 安装 |
