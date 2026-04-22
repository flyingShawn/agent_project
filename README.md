# 阳途智能助手 (Desk Agent)

为桌面管理系统打造的 AI 智能助手，支持自然语言查询数据库、知识文档问答、图表生成、数据导出与定时任务调度。

基于 LangGraph Agent 编排，LLM 自主决策调用 10 种工具（SQL 查询、RAG 检索、元数据查询、时间、计算器、图表、导出、网络搜索、定时任务创建、定时任务管理），无需硬编码意图路由。

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
CHAT_MODEL=qwen3.5:9b
VISION_MODEL=qwen3.5:9b

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
ollama pull qwen3.5:9b
ollama pull qwen3:14b
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

同步说明：
- 普通安装模式不会在后端启动时自动同步文档或 SQL，需要你手动执行脚本或调用同步 API。
- Docker 模式会在 `backend` 容器启动前自动执行一次 SQL 样本库全量同步，命令是 `python scripts/sync_rag.py --target sql --sql-dir /data/sql --mode full`。
- Docker 模式不会在容器启动时自动同步文档知识库，文档同步仍然建议按需手动触发。

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
│   │   ├── prompts.py          #   系统 Prompt
│   │   ├── stream.py           #   astream_events → SSE 流式适配
│   │   └── tools/              #   10 个工具实现
│   │       ├── sql_tool.py     #     自然语言→SQL
│   │       ├── rag_tool.py     #     知识库检索
│   │       ├── metadata_tool.py#     表结构查询
│   │       ├── time_tool.py    #     当前时间
│   │       ├── calculator_tool.py#   数学计算
│   │       ├── chart_tool.py   #     ECharts 图表
│   │       ├── export_tool.py  #     Excel/CSV 导出
│   │       ├── web_search_tool.py#   Tavily 网络搜索
│   │       ├── scheduler_tool.py#    定时任务创建
│   │       └── scheduler_manage_tool.py # 定时任务管理
│   ├── api/v1/                 # API 路由
│   │   ├── chat.py             #   聊天 API（SSE 流式）
│   │   ├── conversations.py    #   会话管理 API
│   │   ├── scheduler.py        #   定时任务 API
│   │   ├── rag.py              #   RAG 同步接口
│   │   ├── sql_agent.py        #   SQL 代理接口
│   │   ├── metadata.py         #   元数据摘要
│   │   ├── export.py           #   文件下载
│   │   └── health.py           #   健康检查
│   ├── core/                   # 核心基础层（配置/日志/异常/请求ID）
│   │   ├── config.py           #   统一配置加载 + Schema 索引
│   │   ├── schema_models.py    #   14 个 Pydantic Schema 模型
│   │   ├── errors.py           #   AppError + 全局异常处理器
│   │   ├── logging.py          #   彩色日志 + RequestIdFilter
│   │   └── request_id.py       #   ContextVar 请求 ID 中间件
│   ├── llm/                    # LLM 调用层
│   │   ├── clients.py          #   底层 HTTP 客户端（OpenAI 兼容 + Ollama 原生）
│   │   └── factory.py          #   LLM 工厂（get_llm / get_sql_llm）
│   ├── db/                     # 聊天历史持久化（SQLite）
│   │   ├── chat_history.py     #   异步引擎 + 会话工厂
│   │   └── models.py           #   ORM 模型（Conversation/Message/AgentTask/AgentTaskResult）
│   ├── rag_engine/             # RAG 引擎（文档解析/分块/向量化/检索）
│   ├── sql_agent/              # SQL 代理（NL→SQL/安全校验/模板匹配）
│   ├── scheduler/              # 定时任务调度器
│   │   ├── manager.py          #   SchedulerManager（APScheduler 封装）
│   │   └── executor.py         #   TaskExecutor（SQL 执行 + 结果持久化）
│   ├── configs/
│   │   ├── schema_metadata.yaml#   数据库 Schema 元数据配置
│   │   └── scheduled_tasks.yaml#   默认定时任务配置
│   └── main.py                 # 应用入口
├── agent_frontend/             # 前端服务 (Vue 3 + Vite + Tailwind)
│   ├── src/
│   │   ├── components/         #   ChatBox / MessageBubble / Sidebar / ChartBlock / ImageUploader
│   │   ├── api/
│   │   │   ├── chat.js         #   SSE 流式通信
│   │   │   └── conversations.js#   会话 CRUD API
│   │   ├── composables/
│   │   │   └── useConversations.js # 会话状态管理
│   │   ├── config.js           #   前端配置读取与兜底
│   │   ├── App.vue             #   根组件（Sidebar + ChatBox 布局）
│   │   └── main.js             #   入口文件
│   └── public/config.js        #   运行时配置占位文件（Docker 启动时覆盖）
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
├── docs/                       # 项目文档
├── .env.example                # 环境变量模板
├── requirements.txt            # Python 依赖
└── docker-compose.yml          # 容器编排
```

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Vue 3 + Vite + Tailwind CSS | Composition API, SSE 流式渲染, ECharts 图表 |
| 后端 | FastAPI + Uvicorn | 异步 Python Web |
| Agent | LangGraph | StateGraph 状态机编排, Tool Calling |
| LLM | langchain-openai | OpenAI 兼容协议, 支持 Ollama/DashScope/DeepSeek |
| 向量数据库 | Qdrant | 文档和 SQL 样本的向量存储与检索 |
| 文本嵌入 | FastEmbed (BAAI/bge-small-zh-v1.5) | 中文向量模型 |
| 文档解析 | Docling | 支持 docx/xlsx/pdf/txt/md 等 |
| 数据库 | SQLAlchemy 2.0 | 支持 MySQL / PostgreSQL 只读查询 |
| 聊天历史 | SQLite + aiosqlite | 会话/消息持久化, WAL 模式 |
| 定时任务 | APScheduler | AsyncIOScheduler, 支持 interval/cron 两种调度 |
| 部署 | Docker Compose + Nginx | 前后端 + Qdrant 三容器编排 |

---

## 配置文件说明

所有配置在项目根目录 `.env` 文件中，从 `.env.example` 复制后修改。无需修改代码。

### 大模型配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | LLM 服务地址（OpenAI 兼容协议） |
| `LLM_API_KEY` | 空 | API Key（本地 Ollama 留空，云端必填） |
| `CHAT_MODEL` | `qwen3:14b` | 文本对话模型 |
| `VISION_MODEL` | `qwen3.5:9b` | 视觉模型（图片理解/多模态 RAG） |
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
| `qwen3.5:9b` | ~4.7GB | 推荐，平衡性能 |
| `qwen3:14b` | ~9GB | 高配置，效果最好 |

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

### 聊天历史与调度配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CHAT_DB_PATH` | `data/chat_history.db` | 聊天历史 SQLite 数据库路径 |
| `AGENT_NAME` | `desk-agent` | 智能体名称，影响知识库路径 |

### 其他配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CHAT_API_TOKEN` | 空 | API 访问 Token（可选鉴权） |
| `TAVILY_API_KEY` | 空 | Tavily 搜索 API Key（留空禁用网络搜索） |
| `WEB_SEARCH_MAX_RESULTS` | `5` | 网络搜索返回数量 |

### 前端配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VITE_APP_NAME` | `阳途智能助手` | 应用名称（标题栏） |
| `VITE_APP_SUBTITLE` | `阳途智能助手为您服务` | 应用副标题 |
| `VITE_APP_WELCOME_TEXT` | `有什么我能帮您的呢？` | 欢迎语 |
| `VITE_APP_INPUT_PLACEHOLDER` | `给智能助手发消息` | 输入框占位文字 |
| `VITE_QUICK_OPTIONS` | `查看客户端在线状态,...` | 快捷选项（逗号分隔） |

前端显示文案统一维护在仓库根目录 `.env` 的 `VITE_*` 配置项中：
- **本地开发 / 本地构建**：`agent_frontend/vite.config.js` 通过 `envDir` 读取根目录 `.env`
- **Docker 部署**：`docker-compose.yml` 从根目录 `.env` 读取同一批变量，`entrypoint.frontend.sh` 在容器启动时生成 `config.js`
- `agent_frontend/public/config.js` 只是占位文件，不再手动维护业务文案

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

### scheduled_tasks.yaml

路径：`agent_backend/configs/scheduled_tasks.yaml`

定义应用启动时自动加载的默认定时任务。支持 interval（固定间隔）和 cron（Cron 表达式）两种调度类型。应用启动时会自动与数据库中已有任务对比，实现配置热更新。

---

## API 路由

| 路径 | 方法 | 功能 |
|------|------|------|
| `/api/v1/chat` | POST | 统一聊天入口（SSE 流式） |
| `/api/v1/chat/end` | POST | 结束对话，关闭数据库连接 |
| `/api/v1/conversations` | GET | 获取对话列表（分页） |
| `/api/v1/conversations` | POST | 创建新对话 |
| `/api/v1/conversations/{id}` | GET | 获取对话详情及消息 |
| `/api/v1/conversations/{id}/title` | PUT | 更新对话标题 |
| `/api/v1/conversations/{id}` | DELETE | 删除对话 |
| `/api/v1/rag` | POST | RAG 文档问答（独立入口） |
| `/api/v1/rag/sync` | POST | 触发文档知识库同步 |
| `/api/v1/rag/sync-sql` | POST | 触发 SQL 样本库同步 |
| `/api/v1/rag/sync/{job_id}` | GET | 查询同步任务状态 |
| `/api/v1/sql-agent` | POST | SQL 查询代理（独立入口） |
| `/api/v1/sql/generate` | POST | SQL 生成（可选执行） |
| `/api/v1/metadata/summary` | GET | 数据库元数据摘要 |
| `/api/v1/scheduler/tasks` | GET | 获取定时任务列表 |
| `/api/v1/scheduler/tasks/{task_id}/results` | GET | 获取任务执行结果 |
| `/api/v1/scheduler/tasks/{task_id}/run` | POST | 手动触发任务执行 |
| `/api/v1/scheduler/tasks/{task_id}/pause` | PUT | 暂停任务 |
| `/api/v1/scheduler/tasks/{task_id}/resume` | PUT | 恢复任务 |
| `/api/v1/scheduler/tasks/{task_id}` | DELETE | 删除任务 |
| `/api/v1/export/download/{filename}` | GET | 导出文件下载 |
| `/api/v1/health` | GET | 健康检查 |

---

## 核心功能

### Agent 工具体系

LLM 通过 Tool Calling 自主决策调用以下 10 种工具：

| 工具 | 功能 | 入参 |
|------|------|------|
| `sql_query` | 自然语言→SQL 生成并执行查询 | `question: str` |
| `rag_search` | 混合检索知识库文档片段 | `question: str` |
| `metadata_query` | 查询数据库表结构信息 | `table_name: str \| None` |
| `get_current_time` | 获取当前日期时间和常用日期范围 | 无 |
| `calculator` | 安全执行数学表达式计算 | `expression: str` |
| `generate_chart` | 生成 ECharts 图表配置 | `chart_type, title, data, x_field, y_field` |
| `export_data` | 导出数据为 Excel/CSV 文件 | `data, filename, format` |
| `web_search` | 通过 Tavily API 搜索互联网 | `query: str` |
| `schedule_task` | 创建定时任务（自动生成 SQL） | `task_name, interval_seconds/cron_expr, sql_template` |
| `manage_scheduled_task` | 管理定时任务（查看/暂停/恢复/删除/更新） | `action, task_id` |

### 定时任务调度

基于 APScheduler 的定时任务系统，支持通过自然语言创建和管理定时任务：

- **任务创建**：用户通过对话描述需求，LLM 自动生成 SQL 并创建定时任务
- **任务类型**：支持 interval（固定间隔）和 cron（Cron 表达式）两种调度
- **任务管理**：支持暂停、恢复、删除、更新 SQL 模板
- **结果查看**：每次执行结果自动持久化，支持查询历史结果
- **自动清理**：每天凌晨 3:00 自动清理超过 7 天的旧结果
- **配置热更新**：`scheduled_tasks.yaml` 中的默认任务启动时自动与数据库对比更新

### 会话管理

- **多会话支持**：侧边栏展示历史会话列表，支持新建、切换、重命名、删除
- **消息持久化**：所有对话消息自动保存到 SQLite 数据库
- **上下文恢复**：切换会话时自动加载历史消息

### RAG 文档问答

#### 支持的文档格式

- Office 文档：PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx)
- 文本文件：Markdown (.md), 纯文本 (.txt)
- 图片：PNG, JPG, JPEG, WebP（OCR 识别）

#### 文档与 SQL 同步

`mode` 可选：
- `incremental`：基于 `.rag_state/*.json` 中记录的 SHA-256 指纹跳过未变更文件。
- `full`：先重建目标集合，再重新导入全部文件。

普通安装模式下，后端启动不会自动同步，按需在 PowerShell 执行：

```powershell
python scripts/sync_rag.py --target all --mode incremental
python scripts/sync_rag.py --target docs --mode full
python scripts/sync_rag.py --target sql --mode full
```

Docker 模式下，可直接在 PowerShell 执行：

```powershell
docker compose exec backend python scripts/sync_rag.py --target all --mode incremental
docker compose exec backend python scripts/sync_rag.py --target docs --mode full
docker compose exec backend python scripts/sync_rag.py --target sql --mode full
```

如果你更偏向 API 方式，也可以触发同步接口：

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/rag/sync -ContentType "application/json" -Body '{"mode":"incremental"}'
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/rag/sync-sql -ContentType "application/json" -Body '{"mode":"incremental"}'
```

同步时机说明：
- 普通安装：仅在你手动执行脚本或调用 API 时同步。
- Docker 模式：`backend` 容器每次启动前自动全量同步 SQL 样本库；文档知识库不自动同步。

#### 检索流程

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
| `/app/data` | Docker volume `chat_data` | 聊天历史持久化 |

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
ollama pull qwen3:9b         # 确认模型已下载
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

**定时任务不执行**
- 检查健康检查接口 `/api/v1/health` 返回的调度器状态
- 确认数据库连接正常（定时任务依赖 SQL 执行）
- 查看后端日志中是否有调度器启动信息

---

## 工具脚本

| 脚本 | 说明 |
|------|------|
| `scripts/smoke_demo.py` | 冒烟测试 |
| `scripts/test_chat_api.py` | API 测试 |
| `scripts/测试数据库连接.py` | 数据库连接测试 |
| `scripts/诊断工具.py` | 诊断工具 |
| `scripts/sync_rag.py` | 统一同步文档和 SQL |
| `scripts/sync_sql_samples.py` | SQL 样本同步 |
| `scripts/sync_docs.py` | 文档同步 |
| `scripts/stop_backend.bat` | 停止后端服务 |
