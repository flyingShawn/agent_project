# 文件夹规范（Folder Conventions）

## 快速判断：新文件放哪里？

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

## 顶层目录职责

| 目录 | 放什么 | 不放什么 |
|------|--------|----------|
| `agent_backend/` | Python 后端全部代码 + 配置文件 | 前端代码、Docker 配置、脚本 |
| `agent_frontend/` | Vue 3 前端全部代码 | 后端代码 |
| `docker/` | Dockerfile、nginx、部署脚本 | 应用代码 |
| `scripts/` | 工具脚本（同步、测试、诊断） | 正式测试用例 |
| `tests/` | 自动化测试 | 脚本、文档 |
| `docs/` | 项目文档 | 代码、配置 |
| `data/` | 运行时数据（聊天历史等） | 代码 |

## 后端模块归属规则

| 功能域 | 目录 | 说明 |
|--------|------|------|
| Agent 编排 | `agent_backend/agent/` | graph、nodes、state、prompts、stream |
| Agent 工具 | `agent_backend/agent/tools/` | @tool 装饰器定义的工具 |
| SQL 生成/执行 | `agent_backend/sql_agent/` | SQL 全流程：生成、校验、执行、连接管理 |
| RAG 检索 | `agent_backend/rag_engine/` | 文档导入、分块、向量化、检索 |
| LLM 调用 | `agent_backend/llm/` | clients.py（底层HTTP）+ factory.py（LangChain工厂） |
| API 路由 | `agent_backend/api/v1/` | FastAPI 路由定义 |
| 聊天历史 | `agent_backend/db/` | chat_history.py（SQLite异步引擎）+ models.py（ORM模型） |
| 基础设施 | `agent_backend/core/` | config.py（统一配置）、errors、logging、中间件 |
| 业务配置 | `agent_backend/configs/` | YAML 配置文件（Docker 挂载） |

## 前端文件归属规则

| 文件类型 | 目录 | 说明 |
|----------|------|------|
| API 通信 | `agent_frontend/src/api/` | SSE 流式、会话管理 |
| UI 组件 | `agent_frontend/src/components/` | Vue 组件 |
| 组合函数 | `agent_frontend/src/composables/` | Vue Composables |

## 命名约定

- **目录名**：小写+下划线（`rag_engine/`、`sql_agent/`）
- **Python 文件**：小写+下划线（`chat_history.py`、`config.py`）
- **Vue 文件**：PascalCase（`ChatBox.vue`）
- **JS 文件**：camelCase（`useConversations.js`）
- **配置文件**：小写+下划线/连字符（`schema_metadata.yaml`）

## 反模式示例

| ❌ 错误 | ✅ 正确 | 原因 |
|---------|---------|------|
| 在 `agent/` 下放 LLM 客户端 | 放 `llm/` | LLM 是独立关注点，不属于 Agent 编排 |
| 在 `db/` 下放业务数据库连接 | 放 `sql_agent/` | `db/` 只管聊天历史，业务数据库是 SQL 功能的一部分 |
| 在根目录放测试文件 | 放 `tests/` | 根目录应保持整洁 |
| 配置文件与代码混放 | 放 `configs/` | Docker 部署时单独挂载 |
| 新建 `agent/llm.py` | 放 `llm/factory.py` | LLM 模块统一在 `llm/` 下管理 |
| 新建 `core/config_xxx.py` | 合并到 `core/config.py` | 配置相关代码统一管理 |
