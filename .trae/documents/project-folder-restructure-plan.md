# 项目文件夹重组与规范计划

## 一、当前结构问题诊断

### 🔴 严重问题

1. **根目录散落临时/测试文件**
   - `test_llm.py`, `test_llm2.py`, `test_llm3.py` — 测试文件不应在根目录
   - `tmp.txt`, `log.txt` — 临时/日志文件不应入库
   - `package-lock.json` — 根目录的 npm 锁文件（前端已有自己的）
   - `docker_install_guide.md` — 文档应归入 docs 目录

2. **LLM 模块职责分裂**
   - `agent_backend/llm/clients.py` — 底层 LLM HTTP 客户端
   - `agent_backend/agent/llm.py` — Agent 层 LLM 封装（get_llm / get_sql_llm）
   - 两个 LLM 相关模块，命名容易混淆，职责边界不清

3. **数据库模块概念混淆**
   - `agent_backend/db/` — 仅管理聊天历史的 SQLite（database.py + models.py）
   - `agent_backend/sql_agent/connection_manager.py` — 管理业务数据库的 MySQL/PG 连接
   - 两个"数据库"概念混在不同位置，新人难以理解

4. **help/ 目录是杂物堆**
   - 混合了：任务文档（task.md, task_need.md, plan04.md）、操作指南（快速测试指南.md）、问题记录（PROBLEM_SOLVED.md, 桌管问题文档.md）、配置说明（配置文件说明.md, 数据库配置指南.md）
   - 无分类、无层次

### 🟡 中等问题

5. **scripts/ 职责混杂**
   - 测试脚本（test_chat_api.py, smoke_demo.py）
   - 运维脚本（stop_backend.bat, 诊断工具.py）
   - 数据同步脚本（sync_docs.py, sync_sql_samples.py）
   - 测试数据库连接.py — 到底是测试还是运维？

6. **configs/ 目录过于单薄**
   - 仅含 `schema_metadata.yaml` 一个文件，独立成目录意义不大

7. **前端缺少分层目录**
   - 无 `views/`、`stores/`、`utils/`、`assets/`、`constants/` 等标准目录
   - 随着功能增长，所有东西会堆在 components/ 里

8. **缺少正式的 tests/ 目录**
   - 测试散落在 scripts/ 和根目录

### 🟢 现有优点

- 后端 `agent/`、`sql_agent/`、`rag_engine/` 三大业务模块边界清晰
- `api/v1/` 路由层结构合理
- `core/` 基础层抽象得当
- 前后端分离的顶层结构正确

---

## 二、重组后的目标结构

```
agent_project/
├── backend/                          # 后端服务（原 agent_backend/，去掉前缀更简洁）
│   ├── app/                          # 应用核心代码
│   │   ├── agent/                    # LangGraph Agent 编排层
│   │   │   ├── __init__.py
│   │   │   ├── graph.py              # StateGraph 构建
│   │   │   ├── nodes.py              # 节点函数 + 条件路由
│   │   │   ├── state.py              # AgentState 定义
│   │   │   ├── prompts.py            # 系统 Prompt
│   │   │   ├── stream.py             # SSE 流式适配
│   │   │   └── tools/                # Agent 工具
│   │   │       ├── __init__.py
│   │   │       ├── sql_tool.py
│   │   │       ├── rag_tool.py
│   │   │       ├── metadata_tool.py
│   │   │       ├── time_tool.py
│   │   │       ├── calculator_tool.py
│   │   │       ├── chart_tool.py
│   │   │       ├── export_tool.py
│   │   │       └── web_search_tool.py
│   │   ├── sql_agent/                # SQL 代理模块
│   │   │   ├── __init__.py
│   │   │   ├── service.py
│   │   │   ├── patterns.py
│   │   │   ├── prompt_builder.py
│   │   │   ├── sql_safety.py
│   │   │   ├── executor.py
│   │   │   ├── connection_manager.py
│   │   │   └── types.py
│   │   ├── rag_engine/               # RAG 检索增强引擎
│   │   │   ├── __init__.py
│   │   │   ├── ingest.py
│   │   │   ├── retrieval.py
│   │   │   ├── qdrant_store.py
│   │   │   ├── embedding.py
│   │   │   ├── chunking.py
│   │   │   ├── settings.py
│   │   │   └── state.py
│   │   ├── llm/                      # LLM 统一模块（合并原 llm/ + agent/llm.py）
│   │   │   ├── __init__.py
│   │   │   ├── clients.py            # 底层 HTTP 客户端（OpenAI 兼容 + Ollama 原生）
│   │   │   └── factory.py            # LLM 工厂（原 agent/llm.py，get_llm/get_sql_llm）
│   │   ├── api/                      # API 路由层
│   │   │   ├── __init__.py
│   │   │   ├── routes.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── chat.py
│   │   │       ├── conversations.py
│   │   │       ├── export.py
│   │   │       ├── health.py
│   │   │       ├── metadata.py
│   │   │       ├── rag.py
│   │   │       └── sql_agent.py
│   │   ├── db/                       # 数据库模块（统一管理所有数据库）
│   │   │   ├── __init__.py
│   │   │   ├── chat_history.py       # 聊天历史 SQLite（原 database.py）
│   │   │   └── models.py             # ORM 模型（Conversation, Message）
│   │   └── core/                     # 核心基础层
│   │       ├── __init__.py
│   │       ├── config.py             # 配置加载（合并 config_loader + config_helper）
│   │       ├── schema_models.py      # Schema Pydantic 模型
│   │       ├── errors.py             # 异常处理
│   │       ├── logging.py            # 日志配置
│   │       └── request_id.py         # 请求 ID 中间件
│   ├── configs/                      # 配置文件（独立于代码，Docker 挂载需要）
│   │   └── schema_metadata.yaml
│   ├── main.py                       # 应用入口
│   └── requirements.txt              # Python 依赖（从根目录移入）
│
├── frontend/                         # 前端服务（原 agent_frontend/）
│   ├── public/
│   │   └── config.js
│   ├── src/
│   │   ├── api/                      # API 通信层
│   │   │   ├── chat.js
│   │   │   └── conversations.js
│   │   ├── components/               # 可复用 UI 组件
│   │   │   ├── chat/
│   │   │   │   ├── ChatBox.vue
│   │   │   │   └── MessageBubble.vue
│   │   │   ├── common/
│   │   │   │   └── ImageUploader.vue
│   │   │   └── chart/
│   │   │       └── ChartBlock.vue
│   │   ├── composables/              # Vue 组合式函数
│   │   │   └── useConversations.js
│   │   ├── views/                    # 页面级组件（预留）
│   │   ├── stores/                   # 状态管理（预留，如需 Pinia）
│   │   ├── utils/                    # 工具函数（预留）
│   │   ├── constants/                # 常量定义（预留）
│   │   ├── assets/                   # 静态资源（预留）
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
│   └── desk-agent/
│       ├── docs/                     # 文档知识库
│       └── sql/                      # SQL 样本库
│
├── deploy/                           # 部署相关（原 docker/）
│   ├── docker/
│   │   ├── Dockerfile.backend
│   │   ├── Dockerfile.frontend
│   │   └── entrypoint.frontend.sh
│   ├── nginx/
│   │   └── nginx.conf
│   ├── scripts/
│   │   ├── deploy.bat
│   │   └── deploy.sh
│   └── README.md
│
├── scripts/                          # 工具脚本（按用途分类）
│   ├── dev/                          # 开发辅助
│   │   └── stop_backend.bat
│   ├── sync/                         # 数据同步
│   │   ├── sync_docs.py
│   │   └── sync_sql_samples.py
│   └── debug/                        # 诊断调试
│       ├── 诊断工具.py
│       └── 测试数据库连接.py
│
├── tests/                            # 测试目录（统一管理）
│   ├── api/                          # API 测试
│   │   └── test_chat_api.py
│   ├── llm/                          # LLM 测试
│   │   ├── test_llm.py
│   │   ├── test_llm2.py
│   │   └── test_llm3.py
│   └── smoke/                        # 冒烟测试
│       └── smoke_demo.py
│
├── docs/                             # 项目文档（原 help/）
│   ├── guides/                       # 操作指南
│   │   ├── 快速测试指南.md
│   │   ├── Node.js安装指南.md
│   │   ├── 数据库配置指南.md
│   │   ├── 配置文件说明.md
│   │   └── Docker安装指南.md         # 原根目录 docker_install_guide.md
│   ├── troubleshooting/              # 问题排查
│   │   ├── PROBLEM_SOLVED.md
│   │   └── 桌管问题文档.md
│   └── references/                   # 参考资料
│       ├── sql-example.md
│       └── 测试运行指南.md
│
├── .env.example                      # 环境变量模板
├── .gitignore
├── docker-compose.yml                # 容器编排
├── README.md                         # 项目说明
├── PROJECT.md                        # 架构文档
└── FOLDER_CONVENTIONS.md             # 📌 文件夹规范（新增，AI 放置文件的规则）
```

---

## 三、核心变更说明

### 变更 1：`agent_backend/` → `backend/app/`

**原因**：`agent_backend` 前缀冗余，项目内只有这一个后端。引入 `app/` 子目录将代码与配置文件（configs/）、入口文件（main.py）、依赖文件（requirements.txt）分离，结构更清晰。

**影响**：所有 Python import 路径从 `agent_backend.xxx` 变为 `backend.app.xxx`。

### 变更 2：合并 LLM 模块

**原因**：`agent/llm.py`（工厂函数）和 `llm/clients.py`（底层客户端）职责相关但物理分离，容易混淆。

**方案**：
- `llm/clients.py` 保持不变（底层 HTTP 客户端）
- `agent/llm.py` 重命名为 `llm/factory.py`（工厂函数，创建 LLM 实例）
- 统一放在 `backend/app/llm/` 下

### 变更 3：数据库模块重命名

**原因**：`db/database.py` 名称过于泛化，实际只管聊天历史 SQLite。

**方案**：`database.py` → `chat_history.py`，明确表达职责。

### 变更 4：core/ 配置合并

**原因**：`config_loader.py` 和 `config_helper.py` 职责高度重叠，都是"配置加载"。

**方案**：合并为 `config.py`，减少文件数，降低认知负担。

### 变更 5：`docker/` → `deploy/`

**原因**：部署不仅包含 Docker，还包含 nginx 配置和部署脚本。`deploy/` 更准确表达"部署"这一关注点，内部再按类型分子目录。

### 变更 6：`help/` → `docs/`

**原因**：`help/` 命名不专业，且内容杂乱。改为 `docs/` 并按 `guides/`、`troubleshooting/`、`references/` 分类。

### 变更 7：`scripts/` 按用途分类

**原因**：当前 scripts/ 混合了测试、同步、调试脚本，找特定脚本需要逐个查看。

**方案**：分为 `dev/`（开发辅助）、`sync/`（数据同步）、`debug/`（诊断调试）。

### 变更 8：新增 `tests/` 目录

**原因**：测试文件散落在根目录和 scripts/ 中，缺少统一管理。

**方案**：创建 `tests/` 并按测试类型分类（api/、llm/、smoke/）。

### 变更 9：前端组件按功能域分组

**原因**：当前所有组件平铺在 `components/`，随功能增长会变得混乱。

**方案**：按功能域分为 `chat/`、`common/`、`chart/`，并预留 `views/`、`stores/`、`utils/`、`constants/`、`assets/` 目录。

### 变更 10：根目录清理

**删除/移动**：
- `test_llm*.py` → `tests/llm/`
- `tmp.txt` → 删除
- `log.txt` → 删除（已在 .gitignore）
- `package-lock.json`（根目录） → 删除
- `docker_install_guide.md` → `docs/guides/Docker安装指南.md`

---

## 四、新增 FOLDER_CONVENTIONS.md 规范文件

此文件将作为 AI 和开发者放置新文件的规则指南，内容涵盖：

1. **顶层目录职责定义** — 每个顶层目录放什么、不放什么
2. **后端模块归属规则** — 新增功能模块应放在哪个目录
3. **前端文件归属规则** — 组件、API、工具函数等放置规则
4. **配置文件归属规则** — 环境配置 vs 业务配置 vs 部署配置
5. **测试文件归属规则** — 单元测试、集成测试、冒烟测试
6. **脚本归属规则** — 开发脚本 vs 运维脚本 vs 数据脚本
7. **文档归属规则** — 操作指南 vs 架构文档 vs 问题记录
8. **命名约定** — 文件命名、目录命名规范
9. **决策流程图** — "新文件应该放哪里"的快速判断流程

---

## 五、执行步骤

### 阶段 1：创建目标目录结构
1. 创建 `backend/app/` 目录树
2. 创建 `frontend/src/` 子目录（views/, stores/, utils/, constants/, assets/）
3. 创建 `deploy/docker/`, `deploy/nginx/`, `deploy/scripts/`
4. 创建 `scripts/dev/`, `scripts/sync/`, `scripts/debug/`
5. 创建 `tests/api/`, `tests/llm/`, `tests/smoke/`
6. 创建 `docs/guides/`, `docs/troubleshooting/`, `docs/references/`

### 阶段 2：移动后端文件
1. `agent_backend/` → `backend/app/`（保留 configs/ 和 main.py 在 backend/ 下）
2. `agent_backend/agent/llm.py` → `backend/app/llm/factory.py`
3. `agent_backend/llm/clients.py` → `backend/app/llm/clients.py`
4. `agent_backend/db/database.py` → `backend/app/db/chat_history.py`
5. `agent_backend/core/config_loader.py` + `config_helper.py` → `backend/app/core/config.py`
6. `requirements.txt` → `backend/requirements.txt`

### 阶段 3：移动前端文件
1. `agent_frontend/` → `frontend/`
2. 组件按功能域分组到子目录

### 阶段 4：移动部署/脚本/测试/文档
1. `docker/` 内容拆分到 `deploy/` 子目录
2. `scripts/` 内容按用途分类
3. 根目录测试文件 → `tests/`
4. `help/` → `docs/` 并分类
5. 清理根目录临时文件

### 阶段 5：更新所有引用
1. 更新 Python import 路径（`agent_backend.` → `backend.app.`）
2. 更新 Docker 配置（Dockerfile、docker-compose.yml 中的路径）
3. 更新 .gitignore 中的路径
4. 更新 README.md 和 PROJECT.md 中的项目结构描述

### 阶段 6：创建 FOLDER_CONVENTIONS.md
1. 编写完整的文件夹规范文档
2. 包含决策流程图和示例

### 阶段 7：验证
1. 后端启动测试
2. 前端构建测试
3. Docker 构建测试
4. 运行现有测试脚本

---

## 六、FOLDER_CONVENTIONS.md 内容大纲

```markdown
# 文件夹规范（Folder Conventions）

## 快速判断：新文件放哪里？

```
新文件是什么类型？
├── Python 业务代码 → backend/app/
│   ├── Agent 相关 → backend/app/agent/
│   ├── SQL 相关 → backend/app/sql_agent/
│   ├── RAG 相关 → backend/app/rag_engine/
│   ├── API 路由 → backend/app/api/v1/
│   ├── LLM 调用 → backend/app/llm/
│   ├── 数据库操作 → backend/app/db/
│   └── 基础设施 → backend/app/core/
├── Vue 前端代码 → frontend/src/
│   ├── 页面组件 → frontend/src/views/
│   ├── 可复用组件 → frontend/src/components/{domain}/
│   ├── API 调用 → frontend/src/api/
│   ├── 组合式函数 → frontend/src/composables/
│   ├── 工具函数 → frontend/src/utils/
│   ├── 常量定义 → frontend/src/constants/
│   └── 静态资源 → frontend/src/assets/
├── 配置文件 → backend/configs/ 或 deploy/
├── 测试文件 → tests/
├── 脚本 → scripts/{dev|sync|debug}/
├── 文档 → docs/{guides|troubleshooting|references}/
└── 部署 → deploy/{docker|nginx|scripts}/
```

## 详细规则...

（完整内容在实施阶段编写）
```
