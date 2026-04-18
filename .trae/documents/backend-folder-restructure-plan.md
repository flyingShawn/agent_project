# 后端文件夹重组计划

> 设计原则：**聚焦后端核心改动，不过度细分测试/脚本/文档目录，保持结构简洁**
> 约束：**保留 `agent_backend/` 和 `agent_frontend/` 顶层目录名不变**

---

## 1. 当前结构问题诊断

### 🔴 严重问题

| # | 问题 | 原因 |
|---|------|------|
| 1 | **LLM 模块职责分裂** | `agent/llm.py`（LangChain 工厂）和 `llm/clients.py`（urllib 手写客户端）物理分离、命名混淆，新人无法判断该用哪个 |
| 2 | **db/database.py 命名泛化** | 实际只管聊天历史 SQLite，但名称暗示是通用数据库模块，与 `sql_agent/connection_manager.py` 的业务数据库概念混淆 |
| 3 | **core/ 配置文件重叠** | `config_helper.py`（环境变量）和 `config_loader.py`（Schema YAML）都是"配置加载"，职责边界模糊 |

### 🟡 中等问题

| # | 问题 | 原因 |
|---|------|------|
| 4 | **根目录散落临时/测试文件** | `test_llm*.py`、`tmp.txt`、`log.txt` 不应在根目录 |
| 5 | **help/ 命名不专业** | `help/` 不符合行业惯例，且内容杂乱无分类 |

### 🟢 现有优点（保持不变）

- `agent/`、`sql_agent/`、`rag_engine/` 三大业务模块边界清晰
- `api/v1/` 路由层结构合理
- `core/` 基础层抽象得当
- `configs/` 独立于代码，Docker 挂载方便
- `agent_backend/` 与 `agent_frontend/` 命名对称，对应关系清晰

---

## 2. 重组后的目标结构

```
agent_project/
├── agent_backend/                    # 后端服务（保留原名）
│   ├── agent/                        # LangGraph Agent 编排层
│   │   ├── __init__.py               #   导出 get_agent_graph
│   │   ├── graph.py                  #   StateGraph 构建
│   │   ├── nodes.py                  #   节点函数 + 条件路由
│   │   ├── state.py                  #   AgentState 定义
│   │   ├── prompts.py                #   系统 Prompt
│   │   ├── stream.py                 #   astream_events → SSE 流式适配
│   │   └── tools/                    #   Agent 工具
│   │       ├── __init__.py
│   │       ├── sql_tool.py
│   │       ├── rag_tool.py
│   │       ├── metadata_tool.py
│   │       ├── time_tool.py
│   │       ├── calculator_tool.py
│   │       ├── chart_tool.py
│   │       ├── export_tool.py
│   │       └── web_search_tool.py
│   ├── sql_agent/                    # SQL 代理模块
│   │   ├── __init__.py
│   │   ├── service.py
│   │   ├── patterns.py
│   │   ├── prompt_builder.py
│   │   ├── sql_safety.py
│   │   ├── executor.py
│   │   ├── connection_manager.py
│   │   └── types.py
│   ├── rag_engine/                   # RAG 检索增强引擎
│   │   ├── __init__.py
│   │   ├── ingest.py
│   │   ├── retrieval.py
│   │   ├── qdrant_store.py
│   │   ├── embedding.py
│   │   ├── chunking.py
│   │   ├── settings.py
│   │   └── state.py
│   ├── llm/                          # LLM 统一模块（合并原 llm/ + agent/llm.py）
│   │   ├── __init__.py               #   统一导出 get_llm, get_sql_llm, OpenAICompatibleClient 等
│   │   ├── clients.py                #   底层 HTTP 客户端（OpenAI 兼容 + Ollama 原生）
│   │   └── factory.py                #   LLM 工厂（原 agent/llm.py，get_llm / get_sql_llm）
│   ├── api/                          # API 路由层
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── chat.py
│   │       ├── conversations.py
│   │       ├── export.py
│   │       ├── health.py
│   │       ├── metadata.py
│   │       ├── rag.py
│   │       └── sql_agent.py
│   ├── db/                           # 数据库模块
│   │   ├── __init__.py
│   │   ├── chat_history.py           #   聊天历史 SQLite（原 database.py）
│   │   └── models.py                 #   ORM 模型（Conversation, Message）
│   ├── core/                         # 核心基础层
│   │   ├── __init__.py
│   │   ├── config.py                 #   配置加载（合并 config_loader + config_helper）
│   │   ├── schema_models.py          #   Schema Pydantic 模型
│   │   ├── errors.py                 #   异常处理
│   │   ├── logging.py                #   日志配置
│   │   └── request_id.py             #   请求 ID 中间件
│   ├── configs/                      #   配置文件（独立于代码，Docker 挂载需要）
│   │   └── schema_metadata.yaml
│   └── main.py                       #   应用入口
│
├── agent_frontend/                   # 前端服务（保留原名）
│   ├── public/
│   │   └── config.js
│   ├── src/
│   │   ├── api/
│   │   │   ├── chat.js
│   │   │   └── conversations.js
│   │   ├── components/
│   │   │   ├── ChartBlock.vue
│   │   │   ├── ChatBox.vue
│   │   │   ├── ImageUploader.vue
│   │   │   ├── MessageBubble.vue
│   │   │   └── Sidebar.vue
│   │   ├── composables/
│   │   │   └── useConversations.js
│   │   ├── App.vue
│   │   ├── config.js
│   │   ├── main.js
│   │   └── style.css
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   └── vite.config.js
│
├── data/                             # 数据目录
│   └── chat_history.db
│
├── docker/                           # Docker 部署（保持原名）
│   ├── .dockerignore
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   ├── README.md
│   ├── deploy.bat
│   ├── deploy.sh
│   ├── entrypoint.frontend.sh
│   └── nginx.conf
│
├── scripts/                          # 工具脚本（保持扁平）
│   ├── __init__.py
│   ├── smoke_demo.py
│   ├── stop_backend.bat
│   ├── sync_docs.py
│   ├── sync_sql_samples.py
│   ├── test_chat_api.py
│   ├── 测试数据库连接.py
│   └── 诊断工具.py
│
├── tests/                            # 测试目录（保持现有）
│   ├── __init__.py
│   ├── frontend_test.html
│   ├── test_api.py
│   ├── test_chat_router.py
│   ├── test_chat_sse.py
│   ├── test_config_loader.py
│   ├── test_frontend.py
│   ├── test_rag_ingest_unit.py
│   ├── test_rag_parser.py
│   ├── test_rag_retrieval.py
│   ├── test_rag_sync.py
│   ├── test_sql_agent.py
│   ├── test_sql_mode.py
│   └── test_sse_quick.py
│
├── docs/                             # 项目文档（原 help/，保持扁平）
│   ├── Node.js安装指南.md
│   ├── PROBLEM_SOLVED.md
│   ├── plan04.md
│   ├── sql-example.md
│   ├── task.md
│   ├── task_need.md
│   ├── 快速测试指南.md
│   ├── 配置文件说明.md
│   ├── 数据库配置指南.md
│   ├── 桌管问题文档.md
│   ├── 测试运行指南.md
│   └── Docker安装指南.md             # 原根目录 docker_install_guide.md
│
├── .env.example
├── .gitignore
├── PROJECT.md
├── README.md
├── docker-compose.yml
├── requirements.txt
└── FOLDER_CONVENTIONS.md             # 📌 文件夹规范（新增）
```

### 每个目录的职责说明

| 目录 | 放什么 | 不放什么 |
|------|--------|----------|
| `agent_backend/` | Python 后端全部代码 + 配置文件 | 前端代码、Docker 配置、脚本 |
| `agent_backend/agent/` | LangGraph 编排（graph、nodes、state、prompts、stream） | 工具实现、LLM 客户端 |
| `agent_backend/agent/tools/` | Agent 可调用的工具（@tool 装饰器） | 非 Agent 工具的业务逻辑 |
| `agent_backend/sql_agent/` | SQL 生成与执行全流程 | Agent 编排、RAG 逻辑 |
| `agent_backend/rag_engine/` | 文档导入、分块、向量化、检索 | Agent 编排、SQL 逻辑 |
| `agent_backend/llm/` | 所有 LLM 相关：客户端 + 工厂函数 | 业务逻辑 |
| `agent_backend/api/` | FastAPI 路由定义 | 业务逻辑实现 |
| `agent_backend/db/` | 聊天历史 SQLite（ORM + 异步引擎） | 业务数据库连接（那是 sql_agent 的） |
| `agent_backend/core/` | 配置、异常、日志、中间件等基础设施 | 业务逻辑 |
| `agent_backend/configs/` | YAML 等业务配置文件（Docker 挂载） | Python 代码 |
| `agent_frontend/` | Vue 3 前端全部代码 | 后端代码 |
| `docker/` | Dockerfile、nginx、部署脚本 | 应用代码 |
| `scripts/` | 工具脚本（同步、测试、诊断） | 正式测试用例 |
| `tests/` | 自动化测试 | 脚本、文档 |
| `docs/` | 项目文档 | 代码、配置 |

---

## 3. 文件变更清单

### 后端核心变更（3 项结构性改动）

| # | 原路径 | 新路径 | 变更类型 | 说明 |
|---|--------|--------|----------|------|
| 1 | `agent_backend/agent/llm.py` | `agent_backend/llm/factory.py` | 移动+重命名 | LLM 工厂归入 llm/ 统一管理 |
| 2 | `agent_backend/db/database.py` | `agent_backend/db/chat_history.py` | 重命名 | 明确职责是聊天历史，非通用数据库 |
| 3 | `agent_backend/core/config_helper.py` + `agent_backend/core/config_loader.py` | `agent_backend/core/config.py` | 合并 | 两个配置文件合并为一个 |

### Import 路径变更映射

| 旧 import | 新 import |
|-----------|-----------|
| `from agent_backend.agent.llm import get_llm, get_sql_llm` | `from agent_backend.llm.factory import get_llm, get_sql_llm` |
| `from agent_backend.db.database import ...` | `from agent_backend.db.chat_history import ...` |
| `from agent_backend.core.config_helper import ...` | `from agent_backend.core.config import ...` |
| `from agent_backend.core.config_loader import ...` | `from agent_backend.core.config import ...` |

### 需要更新 import 的文件

| 文件 | 需更新的 import |
|------|----------------|
| `agent_backend/agent/nodes.py` | `agent.llm` → `llm.factory` |
| `agent_backend/agent/tools/sql_tool.py` | `agent.llm` → `llm.factory`；`core.config_helper` → `core.config`；`core.config_loader` → `core.config` |
| `agent_backend/agent/tools/metadata_tool.py` | `core.config_loader` → `core.config` |
| `agent_backend/agent/tools/rag_tool.py` | 无变更 |
| `agent_backend/api/v1/chat.py` | `db.database` → `db.chat_history` |
| `agent_backend/api/v1/conversations.py` | `db.database` → `db.chat_history` |
| `agent_backend/api/v1/sql_agent.py` | `core.config_helper` → `core.config` |
| `agent_backend/api/v1/rag.py` | 无变更 |
| `agent_backend/api/v1/metadata.py` | `core.config_loader` → `core.config` |
| `agent_backend/sql_agent/service.py` | `core.config_loader` → `core.config` |
| `agent_backend/sql_agent/executor.py` | `core.config_helper` → `core.config` |
| `agent_backend/sql_agent/prompt_builder.py` | `core.config_loader` → `core.config` |
| `agent_backend/sql_agent/sql_safety.py` | 无变更 |
| `agent_backend/sql_agent/patterns.py` | `core.config_loader` → `core.config` |
| `agent_backend/llm/clients.py` | 无变更 |
| `agent_backend/main.py` | `db.database` → `db.chat_history` |
| `agent_backend/core/__init__.py` | 更新导出 |
| `agent_backend/db/__init__.py` | 更新导出 |
| `agent_backend/llm/__init__.py` | 新增 factory 导出 |
| `agent_backend/agent/__init__.py` | 移除 llm 导出 |

### 其他变更

| 原路径 | 新路径 | 变更类型 |
|--------|--------|----------|
| `help/` | `docs/` | 重命名 |
| `docker_install_guide.md` | `docs/Docker安装指南.md` | 移动+重命名 |
| `test_llm.py` | 删除 | 删除（根目录临时测试） |
| `test_llm2.py` | 删除 | 删除 |
| `test_llm3.py` | 删除 | 删除 |
| `tmp.txt` | 删除 | 删除（临时文件） |
| `log.txt` | 删除 | 删除（日志文件） |

### 配置文件更新

| 文件 | 更新内容 |
|------|----------|
| `docker-compose.yml` | 无需改动（`CONFIG_DIR` 默认值 `./agent_backend/configs` 不变） |
| `docker/Dockerfile.backend` | 无需改动（`COPY agent_backend ./agent_backend` 不变） |
| `docker/Dockerfile.frontend` | 无需改动（`COPY agent_frontend` 不变） |

---

## 4. 执行步骤

### 阶段 1：LLM 模块合并

1. 将 `agent_backend/agent/llm.py` 移动到 `agent_backend/llm/factory.py`
2. 更新 `agent_backend/llm/__init__.py`，新增 factory 导出
3. 更新所有引用 `agent_backend.agent.llm` 的 import → `agent_backend.llm.factory`
4. 删除 `agent_backend/agent/llm.py`

### 阶段 2：db/database.py 重命名

1. 将 `agent_backend/db/database.py` 重命名为 `agent_backend/db/chat_history.py`
2. 更新所有引用 `agent_backend.db.database` 的 import → `agent_backend.db.chat_history`
3. 更新 `agent_backend/db/__init__.py` 的导出

### 阶段 3：core/ 配置合并

1. 合并 `agent_backend/core/config_helper.py` + `agent_backend/core/config_loader.py` → `agent_backend/core/config.py`
2. 更新所有引用 `agent_backend.core.config_helper` 和 `agent_backend.core.config_loader` 的 import → `agent_backend.core.config`
3. 更新 `agent_backend/core/__init__.py` 的导出
4. 删除 `agent_backend/core/config_helper.py` 和 `agent_backend/core/config_loader.py`

### 阶段 4：其他文件整理

1. 重命名 `help/` → `docs/`
2. 移动 `docker_install_guide.md` → `docs/Docker安装指南.md`
3. 删除根目录临时文件（test_llm*.py, tmp.txt, log.txt）

### 阶段 5：创建规范文件

1. 创建 `FOLDER_CONVENTIONS.md`（项目根目录）
2. 创建 `.trae/rules/folder-conventions.md`（IDE AI 规则文件）

### 阶段 6：验证

1. 后端启动测试（`uvicorn agent_backend.main:app --reload`）
2. 前端构建测试（`npm run build`）
3. 运行现有测试脚本

---

## 5. .trae/rules/folder-conventions.md 规则内容

### 5.1 顶层目录职责
- `agent_backend/` — Python 后端代码
- `agent_frontend/` — Vue 前端代码
- `docker/` — 部署配置
- `scripts/` — 工具脚本
- `tests/` — 测试用例
- `docs/` — 项目文档
- `data/` — 运行时数据

### 5.2 后端模块归属规则
- Agent 编排 → `agent_backend/agent/`
- Agent 工具 → `agent_backend/agent/tools/`
- SQL 相关 → `agent_backend/sql_agent/`
- RAG 相关 → `agent_backend/rag_engine/`
- LLM 调用 → `agent_backend/llm/`
  - `clients.py` — 底层 HTTP 客户端
  - `factory.py` — LLM 工厂（get_llm / get_sql_llm）
- API 路由 → `agent_backend/api/v1/`
- 聊天历史 → `agent_backend/db/`
  - `chat_history.py` — SQLite 异步引擎
  - `models.py` — ORM 模型
- 基础设施 → `agent_backend/core/`
  - `config.py` — 统一配置加载
- 业务配置 → `agent_backend/configs/`（Docker 挂载）

### 5.3 前端文件归属规则
- API 通信 → `agent_frontend/src/api/`
- UI 组件 → `agent_frontend/src/components/`
- 组合函数 → `agent_frontend/src/composables/`

### 5.4 快速判断决策流程图
```
新文件是什么？
├── Python 业务代码 → agent_backend/
│   ├── Agent 编排/状态/路由 → agent_backend/agent/
│   ├── Agent 工具 → agent_backend/agent/tools/
│   ├── SQL 生成/执行 → agent_backend/sql_agent/
│   ├── 文档检索/向量化 → agent_backend/rag_engine/
│   ├── LLM 调用 → agent_backend/llm/
│   ├── API 路由 → agent_backend/api/v1/
│   ├── 聊天历史 → agent_backend/db/
│   └── 配置/异常/日志 → agent_backend/core/
├── Vue 前端代码 → agent_frontend/src/
│   ├── API 调用 → agent_frontend/src/api/
│   ├── UI 组件 → agent_frontend/src/components/
│   └── 组合函数 → agent_frontend/src/composables/
├── YAML 配置 → agent_backend/configs/
├── 测试 → tests/
├── 脚本 → scripts/
├── 文档 → docs/
└── 部署 → docker/
```

### 5.5 命名约定
- 目录名：小写+下划线（`rag_engine/`、`sql_agent/`）
- Python 文件：小写+下划线（`chat_history.py`、`config.py`）
- Vue 文件：PascalCase（`ChatBox.vue`）
- JS 文件：camelCase（`useConversations.js`）
- 配置文件：小写+下划线/连字符（`schema_metadata.yaml`）

### 5.6 反模式示例
- ❌ 在 `agent/` 下放 LLM 相关代码 → ✅ 放 `llm/`
- ❌ 在 `db/` 下放业务数据库连接 → ✅ 放 `sql_agent/`
- ❌ 在根目录放测试/临时文件 → ✅ 放 `tests/` 或删除
- ❌ 新建 `agent/llm.py` → ✅ 放 `llm/factory.py`
- ❌ 新建 `core/config_xxx.py` → ✅ 合并到 `core/config.py`
- ❌ 把配置 YAML 放在代码目录 → ✅ 放 `configs/`（Docker 挂载需要）
