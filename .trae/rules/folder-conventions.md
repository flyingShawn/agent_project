---
alwaysApply: true
---
# 项目文件夹规范

本项目遵循以下文件夹组织规则，新增文件时必须遵守。

## 顶层目录

- `agent_backend/` — Python 后端代码 + 配置文件
- `agent_frontend/` — Vue 3 前端代码
- `docker/` — Docker 部署配置
- `scripts/` — 工具脚本
- `docs/` — 项目文档
- `data/` — 运行时数据
- 根目录配置文件：
  - `.env.example` — 环境变量模板
  - `docker-compose.yml` — Docker Compose 编排
  - `requirements.txt` — Python 依赖

## 后端模块归属

- Agent 编排（graph/nodes/state/prompts/stream）→ `agent_backend/agent/`
- Agent 工具（@tool 装饰器）→ `agent_backend/agent/tools/`
- SQL 生成/执行/校验/连接管理 → `agent_backend/sql_agent/`
- RAG 检索/向量化/分块/导入 → `agent_backend/rag_engine/`
  - `chunking.py` — 文档分块
  - `embedding.py` — 向量化
  - `ingest.py` — 文档导入
  - `qdrant_store.py` — Qdrant 向量存储
  - `retrieval.py` — 检索
  - `settings.py` — RAG 配置
  - `state.py` — RAG 状态管理
- LLM 调用（底层HTTP客户端 + LangChain工厂）→ `agent_backend/llm/`
  - `clients.py` — 底层 HTTP 客户端（OpenAI 兼容 + Ollama 原生）
  - `factory.py` — LLM 工厂（get_llm / get_sql_llm）
- 定时任务调度 → `agent_backend/scheduler/`
  - `manager.py` — 任务管理（CRUD + 调度注册）
  - `executor.py` — 任务执行器
- API 路由 → `agent_backend/api/`
  - `routes.py` — 路由注册汇总
  - `v1/` — v1 版本路由（chat/conversations/export/health/metadata/rag/scheduler/sql_agent）
- 聊天历史 SQLite → `agent_backend/db/`
  - `chat_history.py` — SQLite 异步引擎（原 database.py）
  - `models.py` — ORM 模型
- 基础设施（配置/异常/日志/中间件）→ `agent_backend/core/`
  - `config.py` — 统一配置加载（原 config_helper.py + config_loader.py 合并）
  - `errors.py` — 统一异常定义
  - `logging.py` — 日志配置
  - `request_id.py` — 请求 ID 中间件
  - `schema_models.py` — Schema 元数据模型
  - `sse.py` — SSE 流式响应工具
- 业务配置 YAML → `agent_backend/configs/`（Docker 挂载，独立于代码）

## 前端文件归属

- API 通信 → `agent_frontend/src/api/`
- UI 组件 → `agent_frontend/src/components/`
- 组合函数 → `agent_frontend/src/composables/`
- 应用入口 → `agent_frontend/src/`（main.js / App.vue / config.js / style.css）

## 命名约定

- 目录名：小写+下划线（rag_engine、sql_agent）
- Python 文件：小写+下划线（chat_history.py、config.py）
- Vue 文件：PascalCase（ChatBox.vue）
- JS 文件：camelCase（useConversations.js）

## 禁止事项

- ❌ 不要在 `agent/` 下放 LLM 相关代码 → 放 `llm/`
- ❌ 不要在 `db/` 下放业务数据库连接 → 放 `sql_agent/`
- ❌ 不要在根目录放测试/临时文件 → 放 `scripts/` 或删除
- ❌ 不要新建 `agent/llm.py` → 放 `llm/factory.py`
- ❌ 不要新建 `core/config_xxx.py` → 合并到 `core/config.py`
- ❌ 不要把配置 YAML 放在代码目录 → 放 `configs/`（Docker 挂载需要）
- ❌ 不要在 `agent/` 下放调度逻辑 → 放 `scheduler/`
- ❌ 不要新建 `agent/scheduler.py` → 放 `scheduler/manager.py` 或 `scheduler/executor.py`
