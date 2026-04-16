# 阳途智能助手 (Desk Agent)

为桌面管理系统打造的 AI 智能助手，支持自然语言查询数据库、知识文档问答、图表生成与数据导出。

基于 LangGraph Agent 编排，LLM 自主决策调用 8 种工具（SQL 查询、RAG 检索、元数据查询、时间、计算器、图表、导出、网络搜索），无需硬编码意图路由。

---

## 快速开始

### 前置条件

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 后端运行 |
| Node.js | 18+ | 前端构建 |
| Ollama | 最新 | 本地大模型服务 |
| Docker Desktop | 最新 | Docker 部署（可选） |

### 1. 配置环境

```bash
copy .env.example .env
notepad .env
```

最小配置（修改 `.env` 中以下项即可运行）：

```env
LLM_BASE_URL=http://localhost:11434/v1
CHAT_MODEL=qwen2.5:7b
VISION_MODEL=qwen2.5-vl:7b

DB_TYPE=mysql
DB_HOST=localhost
DB_PORT=3306
DB_NAME=your_database
DB_USER=root
DB_PASSWORD=your_password
```

### 2. 启动 Ollama 并下载模型

```bash
ollama serve
ollama pull qwen2.5:7b
ollama pull qwen2.5-vl:7b
```

### 3. 启动后端

```bash
pip install -r requirements.txt
python -m uvicorn agent_backend.main:app --reload --host 0.0.0.0 --port 8000
```

验证：访问 http://localhost:8000/api/v1/health 应返回 `{"status":"ok"}`

### 4. 启动前端

```bash
cd agent_frontend
npm install
npm run dev
```

访问 http://localhost:3000 即可使用。

---

## Docker 部署

Ollama 运行在 Docker 外部，Docker Compose 编排前端、后端、Qdrant 三个服务。

```bash
copy .env.example .env
notepad .env
docker\deploy.bat
```

或手动执行：

```bash
docker compose build
docker compose up -d
```

部署后访问地址：

| 服务 | 地址 |
|------|------|
| 前端界面 | http://localhost |
| 后端 API 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/api/v1/health |
| Qdrant 控制台 | http://localhost:6333/dashboard |

常用 Docker 命令：

```bash
docker compose logs -f          # 查看日志
docker compose logs -f backend  # 查看后端日志
docker compose down             # 停止服务
docker compose restart backend  # 重启后端
```

---

## 项目结构

```
agent_project/
├── agent_backend/              # 后端服务 (FastAPI)
│   ├── agent/                  # LangGraph Agent 编排层
│   │   ├── graph.py            #   StateGraph 构建
│   │   ├── nodes.py            #   节点函数 + 条件路由
│   │   ├── state.py            #   AgentState 定义
│   │   ├── llm.py              #   LLM 客户端
│   │   ├── prompts.py          #   系统 Prompt
│   │   ├── stream.py           #   astream_events → SSE 流式适配
│   │   └── tools/              #   8 个工具实现
│   │       ├── sql_tool.py     #     自然语言→SQL
│   │       ├── rag_tool.py     #     知识库检索
│   │       ├── metadata_tool.py#     表结构查询
│   │       ├── time_tool.py    #     当前时间
│   │       ├── calculator_tool.py#   数学计算
│   │       ├── chart_tool.py   #     ECharts 图表
│   │       ├── export_tool.py  #     Excel/CSV 导出
│   │       └── web_search_tool.py#   Tavily 网络搜索
│   ├── api/v1/                 # API 路由
│   ├── core/                   # 核心基础层（配置/日志/异常/请求ID）
│   ├── llm/clients.py          # LLM 客户端（OpenAI 兼容协议）
│   ├── rag_engine/             # RAG 引擎（文档解析/分块/向量化/检索）
│   ├── sql_agent/              # SQL 代理（NL→SQL/安全校验/模板匹配）
│   ├── configs/
│   │   └── schema_metadata.yaml#   数据库 Schema 元数据配置
│   └── main.py                 # 应用入口
├── agent_frontend/             # 前端服务 (Vue 3 + Vite + Tailwind)
│   ├── src/
│   │   ├── components/         #   ChatBox / MessageBubble / ImageUploader
│   │   ├── api/chat.js         #   SSE 流式通信
│   │   └── config.js           #   运行时配置
│   └── public/config.js        #   Docker 环境注入配置
├── data/desk-agent/            # 知识库数据
│   ├── docs/                   #   文档知识库
│   └── sql/                    #   SQL 样本库
├── docker/                     # Docker 构建文件
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   ├── nginx.conf
│   ├── deploy.bat / deploy.sh
│   └── entrypoint.frontend.sh
├── scripts/                    # 工具脚本
├── .env.example                # 环境变量模板
├── requirements.txt            # Python 依赖
└── docker-compose.yml          # 容器编排
```

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Vue 3 + Vite + Tailwind CSS | Composition API, SSE 流式渲染 |
| 后端 | FastAPI + Uvicorn | 异步 Python Web |
| Agent | LangGraph | StateGraph 状态机编排, Tool Calling |
| LLM | langchain-openai | OpenAI 兼容协议, 支持 Ollama/DashScope/DeepSeek |
| 向量数据库 | Qdrant | 文档和 SQL 样本的向量存储与检索 |
| 文本嵌入 | FastEmbed (BAAI/bge-small-zh-v1.5) | 中文向量模型 |
| 文档解析 | Docling | 支持 docx/xlsx/pdf/txt/md 等 |
| 数据库 | SQLAlchemy 2.0 | 支持 MySQL / PostgreSQL 只读查询 |
| 部署 | Docker Compose + Nginx | 前后端 + Qdrant 三容器编排 |

---

## 配置文件说明

所有配置在项目根目录 `.env` 文件中，从 `.env.example` 复制后修改。无需修改代码。

### 大模型配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | LLM 服务地址（OpenAI 兼容协议） |
| `LLM_API_KEY` | 空 | API Key（本地 Ollama 留空，云端必填） |
| `CHAT_MODEL` | `qwen2.5:7b` | 文本对话模型 |
| `VISION_MODEL` | `qwen2.5-vl:7b` | 视觉模型（图片理解/多模态 RAG） |
| `ENABLE_CLOUD_FALLBACK` | `0` | 云端 API 兜底开关（0=关, 1=开） |

**LLM 后端选择：**

| 后端 | LLM_BASE_URL | 需要 API Key |
|------|-------------|-------------|
| 本地 Ollama | `http://localhost:11434/v1` | 否 |
| DeepSeek | `https://api.deepseek.com/v1` | 是 |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 是 |

**模型选择建议：**

| 模型 | 大小 | 适用场景 |
|------|------|---------|
| `qwen2.5:3b` | ~2GB | 低配置，快速响应 |
| `qwen2.5:7b` | ~4.7GB | 推荐，平衡性能 |
| `qwen2.5:14b` | ~9GB | 高配置，效果最好 |

### 数据库配置（只读）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DB_TYPE` | `mysql` | 数据库类型（`mysql` / `postgresql`） |
| `DB_HOST` | `localhost` | 数据库主机 |
| `DB_PORT` | `3306` | 数据库端口（PostgreSQL 用 `5432`） |
| `DB_NAME` | - | 数据库名 |
| `DB_USER` | - | 数据库用户名 |
| `DB_PASSWORD` | - | 数据库密码 |
| `DATABASE_URL` | 空 | 完整连接 URL（优先级高于单独配置项） |

`DATABASE_URL` 格式：
- MySQL: `mysql+pymysql://user:password@host:3306/db?charset=utf8mb4`
- PostgreSQL: `postgresql://user:password@host:5432/db`

### RAG 文档问答配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RAG_DOCS_DIR` | `./data/desk-agent/docs` | 文档知识库目录 |
| `RAG_QDRANT_URL` | `http://localhost:6333` | Qdrant 服务地址 |
| `RAG_QDRANT_PATH` | `./.qdrant_local` | Qdrant 本地存储路径 |
| `RAG_QDRANT_COLLECTION` | `desk_agent_docs` | 文档向量集合名称 |
| `RAG_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 文本嵌入模型 |
| `RAG_HYBRID_ALPHA` | `0.7` | 混合检索权重（越大向量权重越高） |
| `RAG_TOP_K` | `5` | 返回文档数 |
| `RAG_CANDIDATE_K` | `30` | 候选文档数（用于重排序） |
| `RAG_VECTOR_MIN_SCORE` | `0.5` | 最低相似度阈值（低于此值过滤） |

### SQL 样本库配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RAG_SQL_DIR` | `./data/desk-agent/sql` | SQL 样本目录 |
| `RAG_SQL_QDRANT_COLLECTION` | `desk_agent_sql` | SQL 向量集合名称 |
| `RAG_SQL_TOP_K` | `3` | SQL 样本返回数 |
| `RAG_SQL_CANDIDATE_K` | `15` | SQL 候选数 |
| `RAG_SQL_HYBRID_ALPHA` | `0.8` | SQL 检索更偏重语义匹配 |
| `SQL_MAX_ROWS` | `500` | SQL 查询最大行数限制 |

### 其他配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AGENT_NAME` | `desk-agent` | 智能体名称，影响知识库路径 |
| `CHAT_API_TOKEN` | 空 | API 访问 Token（可选鉴权） |
| `TAVILY_API_KEY` | 空 | Tavily 搜索 API Key（留空禁用网络搜索） |
| `WEB_SEARCH_MAX_RESULTS` | `5` | 网络搜索返回数量 |

### 前端配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_NAME` | `阳途智能助手` | 应用名称（标题栏） |
| `APP_SUBTITLE` | `阳途智能助手为您服务` | 应用副标题 |
| `APP_WELCOME_TEXT` | `有什么我能帮您的呢？` | 欢迎语 |
| `APP_INPUT_PLACEHOLDER` | `给智能助手发消息` | 输入框占位文字 |
| `QUICK_OPTIONS` | `查看客户端在线状态,...` | 快捷选项（逗号分隔） |

前端配置通过两种方式生效：
- **本地开发**：修改 `agent_frontend/src/config.js`
- **Docker 部署**：通过环境变量注入，`entrypoint.frontend.sh` 生成 `config.js`

### schema_metadata.yaml

路径：`agent_backend/configs/schema_metadata.yaml`

定义数据库表结构、同义词、安全规则、权限控制和查询模板。主要包含：

| 配置项 | 说明 |
|--------|------|
| `tables` | 数据库表结构定义（表名、字段、类型、注释） |
| `relationships` | 表间关联关系（用于 JOIN 推断） |
| `synonyms` | 字段同义词映射（帮助 LLM 理解用户意图） |
| `security` | 安全规则（受限表、禁止查询的敏感列） |
| `permissions` | 权限控制规则（按管理员限制可见部门/设备） |
| `query_patterns` | 预定义 SQL 模板（命中则绕过 LLM 直接返回） |
| `display_fields` | 不同查询场景的展示字段规范 |

---

## API 路由

| 路径 | 方法 | 功能 |
|------|------|------|
| `/api/v1/chat` | POST | 统一聊天入口（SSE 流式） |
| `/api/v1/chat/end` | POST | 结束对话，关闭数据库连接 |
| `/api/v1/rag` | POST | RAG 文档问答（独立入口） |
| `/api/v1/rag/sync` | POST | 触发文档知识库同步 |
| `/api/v1/rag/sync-sql` | POST | 触发 SQL 样本库同步 |
| `/api/v1/rag/sync/{job_id}` | GET | 查询同步任务状态 |
| `/api/v1/sql-agent` | POST | SQL 查询代理（独立入口） |
| `/api/v1/sql/generate` | POST | SQL 生成（可选执行） |
| `/api/v1/metadata/summary` | GET | 数据库元数据摘要 |
| `/api/v1/export/download/{filename}` | GET | 导出文件下载 |
| `/api/v1/health` | GET | 健康检查 |

---

## RAG 文档问答

### 支持的文档格式

- Office 文档：PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx)
- 文本文件：Markdown (.md), 纯文本 (.txt)
- 图片：PNG, JPG, JPEG, WebP（OCR 识别）

### 文档导入

将文档放入 `data/desk-agent/docs/` 目录，然后调用同步接口：

```bash
curl -X POST http://localhost:8000/api/v1/rag/sync \
  -H "Content-Type: application/json" \
  -d '{"mode": "incremental"}'
```

`mode` 可选：`incremental`（增量，基于 SHA-256 指纹跳过未变更文件）或 `full`（全量重建）。

### 检索流程

1. **文档解析**：Docling 将多种格式转为 Markdown
2. **文档分块**：按标题结构分块，支持重叠（1800 字符，200 字符重叠）
3. **向量化**：FastEmbed 生成向量
4. **存储**：写入 Qdrant 向量数据库
5. **检索**：混合检索 = 向量相似度 (alpha=0.7) + BM25 关键词匹配 (0.3)

---

## Docker 部署架构

```
宿主机
├── Ollama :11434 (大模型)
└── MySQL/PostgreSQL (数据库)

Docker 网络
├── frontend (Nginx :80) ──proxy──▶ backend :8000
├── backend  (Uvicorn :8000) ──────▶ qdrant :6333
│                                   └──▶ Ollama (宿主机)
│                                   └──▶ MySQL (宿主机)
└── qdrant   (REST :6333, gRPC :6334)
```

### 端口说明

| 端口 | 服务 | 说明 |
|------|------|------|
| 80 | frontend | 前端页面 |
| 8000 | backend | 后端 API |
| 6333 | qdrant | Qdrant REST API |
| 6334 | qdrant | Qdrant gRPC |
| 11434 | ollama | Ollama API（宿主机外部） |

### 数据卷

| 容器内路径 | 宿主机路径 | 说明 |
|-----------|-----------|------|
| `/data/docs` | `./data/desk-agent/docs` | 文档知识库（只读挂载） |
| `/data/sql` | `./data/desk-agent/sql` | SQL 样本库（只读挂载） |
| `/app/configs` | `./agent_backend/configs` | 配置文件（只读挂载） |
| `/app/.qdrant_local` | Docker volume `qdrant_data` | 向量数据持久化 |

### Docker 环境变量注意

Docker 容器内访问宿主机 Ollama：
- **Windows/macOS**：`LLM_BASE_URL=http://host.docker.internal:11434/v1`
- **Linux**：`LLM_BASE_URL=http://172.17.0.1:11434/v1`

容器内 Qdrant 使用服务名：`RAG_QDRANT_URL=http://qdrant:6333`

---

## 常见问题

**Ollama 连接失败**
```bash
ollama list                    # 检查 Ollama 是否运行
ollama pull qwen2.5:7b         # 确认模型已下载
```

**数据库连接失败**
```bash
python scripts/测试数据库连接.py  # 测试数据库连接
```

**端口被占用**
```bash
netstat -ano | findstr :8000   # 查找占用进程
taskkill /PID <进程ID> /F      # 结束进程
```

**Docker 后端无法连接 Ollama**
- 检查 `.env` 中 `LLM_BASE_URL` 是否使用 `host.docker.internal`（Windows/macOS）或宿主机 IP（Linux）
- 确保 Ollama 启动时监听所有接口：`OLLAMA_HOST=0.0.0.0 ollama serve`

**RAG 检索无结果**
- 确认文档已放入 `data/desk-agent/docs/` 目录
- 调用 `/api/v1/rag/sync` 触发文档同步
- 检查 Qdrant 控制台 http://localhost:6333/dashboard 是否有向量数据

---

## 工具脚本

| 脚本 | 说明 |
|------|------|
| `scripts/smoke_demo.py` | 冒烟测试 |
| `scripts/test_chat_api.py` | API 测试 |
| `scripts/测试数据库连接.py` | 数据库连接测试 |
| `scripts/诊断工具.py` | 诊断工具 |
| `scripts/sync_sql_samples.py` | SQL 样本同步 |
| `scripts/stop_backend.bat` | 停止后端服务 |
