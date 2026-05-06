# 文件夹规范（Folder Conventions）

## 快速判断：新文件放哪里？

```
新文件是什么？
├── Python 业务代码 → agent_backend/
│   ├── Agent 编排/状态/注册表/历史 → agent_backend/agent/
│   ├── Agent 工具 → agent_backend/agent/tools/
│   ├── SQL 生成/执行 → agent_backend/sql_agent/
│   ├── 文档检索/向量化 → agent_backend/rag_engine/
│   ├── LLM 调用 → agent_backend/llm/
│   ├── API 路由 → agent_backend/api/v1/
│   ├── 聊天历史/简报/任务持久化 → agent_backend/db/
│   ├── 任务引擎 → agent_backend/task_engine/
│   ├── 运维简报 → agent_backend/ops_reports/
│   ├── 外部集成 → agent_backend/integrations/
│   └── 配置/异常/日志/上下文 → agent_backend/core/
├── Vue 前端代码 → agent_frontend/src/
│   ├── API 调用 → agent_frontend/src/api/
│   ├── UI 组件 → agent_frontend/src/components/
│   ├── 组合函数 → agent_frontend/src/composables/
│   ├── 路由 → agent_frontend/src/router/
│   └── 工具函数 → agent_frontend/src/utils/
├── YAML 配置 → agent_backend/configs/
│   ├── 总控配置 → agent_backend/configs/agents.yaml
│   └── 智能体配置 → agent_backend/configs/{agent_type}/
├── 测试 → tests/
├── 脚本 → scripts/
├── 文档 → docs/
├── 部署 → docker/
├── Qt 桌面桥接 → qt/
└── 运行时数据 → data/{agent_type}/
```

## 顶层目录职责

| 目录 | 放什么 | 不放什么 |
|------|--------|----------|
| `agent_backend/` | Python 后端全部代码 + 配置文件 | 前端代码、Docker 配置、脚本 |
| `agent_frontend/` | Vue 3 前端全部代码 | 后端代码 |
| `docker/` | Dockerfile、nginx、部署脚本 | 应用代码 |
| `scripts/` | 工具脚本（同步、运维简报、诊断） | 正式测试用例 |
| `tests/` | 自动化测试 | 脚本、文档 |
| `docs/` | 项目文档 | 代码、配置 |
| `data/` | 运行时数据（每个智能体独立子目录） | 代码 |
| `qt/` | Qt 桌面桥接程序（XFAgentBridge） | Python 后端代码 |

## 多智能体架构

项目采用多智能体架构，通过 `agents.yaml` 总控配置管理所有启用的智能体。

### 核心机制
- `agent_backend/configs/agents.yaml` — 总控配置，定义启用哪些智能体及其数据库/RAG/报表配置
- `agent_backend/agent/registry.py` — AgentRegistry 注册表，按 agent_type 加载独立配置
- `agent_backend/core/context.py` — contextvars 上下文，跨请求链路传递 agent_type
- API 路由使用 `/{agent_type}/` 前缀区分不同智能体

### 智能体配置目录
每个智能体在 `configs/` 下有独立子目录：
- `configs/desk-agent/` — 桌面管理助手配置
  - `prompts.yaml` — 系统提示词
  - `schema_metadata.yaml` — 数据库元数据
  - `ops_reports.yaml` — 运维简报配置
- `configs/ticket-agent/` — 工单系统助手配置
  - `prompts.yaml` — 系统提示词
  - `schema_metadata.yaml` — 数据库元数据

### 数据隔离
- 每个智能体有独立的数据库连接（在 agents.yaml 中配置）
- 每个智能体有独立的 RAG 集合（docs_collection / sql_collection）
- 聊天记录通过 agent_type 字段区分
- 运维简报通过 agent_type 字段区分
- 任务执行通过 agent_type 字段区分
- 知识库条目通过 agent_type 字段区分

## 后端模块归属规则

| 功能域 | 目录 | 说明 |
|--------|------|------|
| Agent 编排 | `agent_backend/agent/` | graph、nodes、state、prompts、stream、registry、history |
| Agent 工具 | `agent_backend/agent/tools/` | @tool 装饰器定义的工具（当前 8 个） |
| SQL 生成/执行 | `agent_backend/sql_agent/` | SQL 全流程：生成、校验、执行、连接管理 |
| RAG 检索 | `agent_backend/rag_engine/` | 文档导入、分块、向量化、检索、SQL 样本管理 |
| LLM 调用 | `agent_backend/llm/` | clients.py（底层HTTP）+ factory.py（LangChain工厂） |
| API 路由 | `agent_backend/api/v1/` | FastAPI 路由定义（12 个路由模块） |
| 外部身份 | `agent_backend/api/external_identity.py` | HMAC 签名校验外部入口用户身份 |
| 聊天历史 | `agent_backend/db/` | chat_history.py（SQLite异步引擎）+ models.py（ORM模型：Conversation/Message/OpsReport/OpsMetricSnapshot/TaskExecution/KnowledgeEntry） |
| 任务引擎 | `agent_backend/task_engine/` | base.py（任务基类）+ registry.py（注册表）+ executor.py（执行器）+ schemas.py（数据模型）+ tasks/（具体任务） |
| 运维简报 | `agent_backend/ops_reports/` | manager.py（简报管理器）+ executor.py（简报执行器） |
| 外部集成 | `agent_backend/integrations/` | chat_history_push/（第三方会话上报） |
| 基础设施 | `agent_backend/core/` | config.py（统一配置+agents.yaml模型）、context.py（agent_type上下文）、errors、logging、中间件、sse |
| 业务配置 | `agent_backend/configs/` | agents.yaml 总控 + 各智能体子目录（Docker 挂载） |

## 前端文件归属规则

| 文件类型 | 目录 | 说明 |
|----------|------|------|
| API 通信 | `agent_frontend/src/api/` | agents/chat/conversations/knowledge/localDeskBridge/opsReports/tasks（7 个模块） |
| UI 组件 | `agent_frontend/src/components/` | 顶层组件 + mode/（模式切换）+ task/（任务相关，7 个组件） |
| 组合函数 | `agent_frontend/src/composables/` | useConversations + useTaskMode |
| 路由 | `agent_frontend/src/router/` | index.js（/:agentType 多智能体路由） |
| 工具函数 | `agent_frontend/src/utils/` | externalIdentity.js（外部身份工具） |
| 页面组件 | `agent_frontend/src/` | AgentLayout.vue（智能体布局）+ KnowledgePage.vue（知识库页面） |

## 命名约定

- **目录名**：小写+下划线（`rag_engine/`、`sql_agent/`）
- **Python 文件**：小写+下划线（`chat_history.py`、`config.py`）
- **Vue 文件**：PascalCase（`ChatBox.vue`）
- **JS 文件**：camelCase（`useConversations.js`）
- **配置文件**：小写+下划线/连字符（`schema_metadata.yaml`、`ops_reports.yaml`）
- **智能体标识**：kebab-case（`desk-agent`、`ticket-agent`）

## 根目录清理规则

根目录只允许存在**项目级配置文件**和**顶层目录**，禁止存放任何运行时生成的文件、依赖目录或测试产物。

### 根目录白名单（允许存在的文件/目录）

| 类型 | 示例 | 说明 |
|------|------|------|
| 版本控制 | `.git/`, `.gitignore` | Git 相关 |
| 环境配置 | `.env`, `.env.example` | 环境变量模板 |
| 依赖清单 | `requirements.txt`, `requirements-docling.txt` | Python 依赖 |
| 部署配置 | `docker-compose.yml` | Docker Compose 编排 |
| 项目文档 | `README.md`, `PROJECT.md`, `AGENTS.md`, `FOLDER_CONVENTIONS.md` | 项目级说明文档 |
| 顶层目录 | `agent_backend/`, `agent_frontend/`, `docker/`, `scripts/`, `tests/`, `docs/`, `data/`, `qt/` | 业务代码目录 |

### 根目录禁止出现的内容

| ❌ 禁止项 | 正确位置 | 处理方式 |
|-----------|---------|---------|
| `node_modules/` | `tests/e2e/node_modules/` 或 `agent_frontend/node_modules/` | 移入对应目录后重新 `npm install` |
| `package.json` / `package-lock.json` | `tests/e2e/package.json` 或 `agent_frontend/package.json` | 移入对应目录 |
| `build/` | 按来源分别处理（见下表） | 清理或迁移 |
| `*.log` | `tests/logs/` 或直接删除 | 日志文件不入版本控制 |
| 测试产物（`pw_*.txt`, 截图等） | `tests/e2e/results/` / `tests/e2e/screenshots/` | 移入测试目录 |
| 临时文件 | `tests/temp/` 或直接删除 | 临时文件用完即删 |
| Python 缓存 | 由 `.gitignore` 忽略 | 不提交 |

### `build/` 目录来源处理

根目录出现 `build/` 通常来自以下源头，需分类处理：

| 来源 | 内容示例 | 正确位置 | 处理方式 |
|------|---------|---------|---------|
| Python 编译缓存 | `py_compile_cache/` | 由 `.gitignore` 忽略 | 删除，Python 会自动重建 |
| Qt CMake 构建 | `XFAgentBridge-cmake-check/` | `qt/XFAgentBridge/build/` | 在 Qt 子目录内构建 |
| 前端构建产物 | `dist/`, `assets/` | `agent_frontend/dist/` | Vite 默认输出到 `agent_frontend/dist/` |

### Playwright 规范

Playwright 是 E2E 测试工具，必须按以下规则管理：

**安装位置**：`tests/e2e/package.json`
```bash
cd tests/e2e
npm install --save-dev playwright
```

**目录结构**：
```
tests/
├── e2e/
│   ├── package.json          # Playwright 依赖
│   ├── package-lock.json
│   ├── node_modules/         # npm 依赖（gitignore）
│   ├── playwright.config.js  # Playwright 配置
│   ├── tests/                # 测试用例
│   ├── fixtures/             # 测试数据/图片
│   ├── screenshots/          # 测试截图
│   └── results/              # 测试报告/日志
├── unit/                     # 单元测试
└── integration/              # 集成测试
```

**运行方式**：
```bash
cd tests/e2e
npx playwright test        # 运行测试
npx playwright show-report # 查看报告
```

**禁止**：在根目录执行 `npm install playwright`。

### 临时文件规范

| 场景 | 正确位置 | 清理策略 |
|------|---------|---------|
| 调试日志 | `tests/logs/debug_*.log` | 写入 `.gitignore`，定期清理 |
| 测试输出 | `tests/e2e/results/` | 每次测试前清空 |
| 诊断工具输出 | `tests/temp/` | 用完即删，不入版本控制 |
| 截图对比 | `tests/e2e/screenshots/` | 按测试用例子目录组织 |

### 新增文件自检清单

在根目录新建任何文件前，先问自己：

1. 这是项目级配置文件吗？（如 `docker-compose.yml`）→ 可以放
2. 这是代码吗？→ 放 `agent_backend/` 或 `agent_frontend/`
3. 这是测试吗？→ 放 `tests/`
4. 这是脚本吗？→ 放 `scripts/`
5. 这是文档吗？→ 放 `docs/`
6. 这是运行时数据吗？→ 放 `data/`
7. 这是临时文件吗？→ 放 `tests/temp/` 或用完删除
8. 这是 npm 相关文件吗？→ 放到对应前端或测试子目录

如果以上都不是，**不要放在根目录**。

## 反模式示例

| ❌ 错误 | ✅ 正确 | 原因 |
|---------|---------|------|
| 在 `agent/` 下放 LLM 客户端 | 放 `llm/` | LLM 是独立关注点，不属于 Agent 编排 |
| 在 `db/` 下放业务数据库连接 | 放 `sql_agent/` | `db/` 只管聊天历史和持久化，业务数据库是 SQL 功能的一部分 |
| 在根目录放测试文件 | 放 `tests/` | 根目录应保持整洁 |
| 在根目录放 `node_modules/` | 放 `tests/e2e/node_modules/` 或 `agent_frontend/node_modules/` | 按用途隔离，避免根目录混乱 |
| 在根目录放 `build/` | 按来源放 `agent_frontend/dist/` 或 `qt/XFAgentBridge/build/` | 构建产物不应污染根目录 |
| 在根目录放 `package.json` | 放对应子目录 | 根目录不是 npm 项目 |
| 配置文件与代码混放 | 放 `configs/` | Docker 部署时单独挂载 |
| 新建 `agent/llm.py` | 放 `llm/factory.py` | LLM 模块统一在 `llm/` 下管理 |
| 新建 `core/config_xxx.py` | 合并到 `core/config.py` | 配置相关代码统一管理 |
| 把智能体配置放在 `configs/` 根目录 | 放 `configs/{agent_type}/` 子目录 | 每个智能体需要独立配置目录 |
| 硬编码智能体类型 | 使用 contextvars 的 `current_agent_type` | 多智能体架构下，agent_type 应通过上下文动态获取 |
| 在 `agent/` 下放调度器代码 | 放 `ops_reports/` 或 `task_engine/` | 调度逻辑已拆分为独立模块 |
| 在 `db/` 下放调度器逻辑 | 放 `ops_reports/` 或 `task_engine/` | `db/` 只管 ORM 模型和引擎 |
