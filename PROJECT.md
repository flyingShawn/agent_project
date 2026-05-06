# 多智能体系统架构分析

> 为老 C++ 桌面管理系统和工单系统等多业务场景开发的智能 Agent 助手平台，提供自然语言"知识文档问答"、"数据库只读数据智能查询"、"定时运维简报"和"任务模式执行"功能。采用多智能体架构，通过 `agents.yaml` 总控配置管理所有启用的智能体，每个智能体拥有独立的数据库连接、RAG 集合、提示词和 Schema 元数据。

---

## 系统架构

```
┌──────────────┐     ┌───────────────────────────────────────────────────────────┐
│   Frontend   │────▶│                Backend (FastAPI)                          │
│  Vue 3 + Vite│     │                                                           │
└──────────────┘     │  ┌──────────┐    ┌────────────────────────────────────┐  │
                     │  │  Chat    │───▶│     LangGraph Agent                │  │
                     │  │  API     │    │  ┌──────────────────────────────┐  │  │
                     │  │  (SSE)   │    │  │  init → agent ─┬─tools──┐   │  │  │
                     │  └──────────┘    │  │         ↑      ↓        │   │  │  │
                     │                  │  │         └──agent←┘       │   │  │  │
                     │                  │  │              ↓ respond   │   │  │  │
                     │                  │  │              → END       │   │  │  │
                     │                  │  └──────────────────────────────┘  │  │
                     │                  │  Tool Calling 自主决策 8 工具      │  │
                     │                  └────────────────────────────────────┘  │
                     │                         │                                 │
                     │        ┌────────────────┼────────────────┐                │
                     │        ↓                ↓                ↓                │
                     │  ┌───────────┐  ┌────────────┐  ┌──────────────┐         │
                     │  │ SQL Agent │  │ RAG Engine │  │ Other Tools  │         │
                     │  │ NL→SQL    │  │ 混合检索    │  │ 时间/计算/   │         │
                     │  │           │  │            │  │ 图表/导出/   │         │
                     │  └─────┬─────┘  └─────┬──────┘  │ 搜索         │         │
                     │        ↓              ↓         └──────────────┘         │
                     │  ┌───────────┐  ┌────────────┐                           │
                     │  │ Database  │  │  Qdrant    │  ┌──────────────┐         │
                     │  │ MySQL/PG  │  │ 向量数据库  │  │ Task Engine  │         │
                     │  └───────────┘  └────────────┘  │ 任务执行器   │         │
                     │                                  └──────┬───────┘         │
                     │  ┌─────────────────────────────┐        │                 │
                     │  │  LLM (OpenAI 兼容协议)       │        │                 │
                     │  │  Ollama / DashScope / DeepSeek│       │                 │
                     │  └─────────────────────────────┘        │                 │
                     │                                         ↓                 │
                     │                                  ┌────────────┐           │
                     │                                  │  SQLite    │           │
                     │                                  │ 聊天历史/  │           │
                     │                                  │ 简报/任务  │           │
                     │                                  └────────────┘           │
                     │                                                           │
                     │  ┌─────────────────────────────────────────────────────┐  │
                     │  │  AgentRegistry（多智能体注册表）                      │  │
                     │  │  agents.yaml → desk-agent / ticket-agent / ...      │  │
                     │  │  每个智能体：独立数据库 + 独立RAG集合 + 独立提示词    │  │
                     │  └─────────────────────────────────────────────────────┘  │
                     └───────────────────────────────────────────────────────────┘
```

### 核心架构变化

| 对比项 | 旧架构 | 当前架构 |
| ------ | ------ | -------- |
| **智能体架构** | 单一 desk-agent | 多智能体架构，agents.yaml 总控，AgentRegistry 注册表 |
| **意图路由** | 关键词 + 正则评分 → 硬路由到 SQL/RAG | LangGraph Tool Calling → LLM 自主决策调用工具 |
| **Agent 编排** | 无 | LangGraph StateGraph（init → agent → tools 循环 → respond） |
| **工具数量** | 2（SQL 查询 + RAG 检索） | 8（SQL/RAG/元数据/时间/计算器/图表/导出/网络搜索） |
| **任务模式** | APScheduler 定时任务 | Task Engine 任务引擎 + Qt 桌面桥接 |
| **运维简报** | 无 | ops_reports 模块，定时生成简报 + 指标快照趋势对比 |
| **LLM 客户端** | Ollama 原生协议为主 | OpenAI 兼容协议为主，支持 Ollama/DashScope/DeepSeek 切换 |
| **流式输出** | Ollama NDJSON 流 | LangGraph astream_events v2 → SSE |
| **聊天模块** | chat/ 目录 | 迁移至 api/v1/chat.py + agent/ 编排层 |
| **会话管理** | 无 | SQLite 持久化，支持多会话/重命名/删除/上下文恢复 |
| **配置管理** | config_loader.py + config_helper.py 分离 | core/config.py 统一配置 + agents.yaml 多智能体配置 |
| **LLM 调用** | agent/llm.py | llm/factory.py（工厂模式）+ llm/clients.py（底层HTTP） |
| **数据隔离** | 无 | 每个智能体独立数据库连接、独立 RAG 集合、agent_type 字段区分 |
| **外部集成** | 无 | integrations/chat_history_push 第三方会话上报 |
| **知识库管理** | 仅文件系统 | KnowledgeEntry ORM + 文件系统双存储 |

---

## 技术栈

| **层级** | **技术** | **版本** | **说明** |
| -------- | -------- | -------- | -------- |
| **前端框架** | Vue 3 | ^3.4.21 | Composition API (`<script setup>`) |
| **构建工具** | Vite | ^5.4.21 | 快速 HMR 开发体验 |
| **样式** | Tailwind CSS | ^3.4.19 | 原子化 CSS |
| **路由** | Vue Router | ^4.x | 多智能体路由（/:agentType） |
| **图表** | ECharts | ^6.0.0 | 数据可视化图表渲染 |
| **Markdown** | marked + highlight.js | ^12.0.0 / ^11.9.0 | 消息渲染 + 代码高亮 |
| **安全** | DOMPurify | ^3.0.9 | HTML 净化防 XSS |
| **后端框架** | FastAPI | >=0.110 | 异步 Python Web |
| **ASGI** | Uvicorn | >=0.27 | 高性能异步服务器 |
| **数据校验** | Pydantic v2 | >=2.6 | 请求/响应模型 |
| **配置管理** | pydantic-settings | >=2.2 | 环境变量自动绑定 |
| **Agent 框架** | LangGraph | >=0.2, <0.3 | StateGraph 状态机编排 |
| **LLM 调用** | langchain-openai | >=0.3 | OpenAI 兼容协议统一调用 |
| **大模型** | Qwen2.5/Qwen3 (Ollama) | 7b~14b | 本地部署，支持文本和视觉模型 |
| **向量数据库** | Qdrant | v1.17.0 | 文档和 SQL 样本的向量存储与检索 |
| **文本嵌入** | FastEmbed (BAAI/bge-small-zh-v1.5) | >=0.3 | 中文向量模型 |
| **文档解析** | Docling | >=2.0 | 支持 docx/xlsx/txt/md/pdf 等格式 |
| **业务数据库** | SQLAlchemy 2.0 | >=2.0 | 支持 MySQL / PostgreSQL 只读查询 |
| **聊天历史** | SQLite + aiosqlite | >=0.20 | 会话/消息/简报/任务持久化, WAL 模式 |
| **任务引擎** | Task Engine + Qt Bridge | - | 任务注册/执行 + XFAgentBridge 桌面桥接 |
| **部署** | Docker Compose + Nginx | - | 前后端 + Qdrant + Docling-sync 四容器编排 |

---

## 多智能体架构

### 核心机制

项目采用多智能体架构，通过 `agents.yaml` 总控配置管理所有启用的智能体。

| 组件 | 文件 | 职责 |
| ---- | ---- | ---- |
| 总控配置 | `configs/agents.yaml` | 定义启用哪些智能体及其数据库/RAG/LLM/报表配置 |
| 智能体注册表 | `agent/registry.py` | AgentRegistry 单例，按 agent_type 加载独立配置 |
| 上下文传递 | `core/context.py` | contextvars 上下文，跨请求链路传递 agent_type |
| API 路由前缀 | `api/routes.py` | 使用 `/{agent_type}/` 前缀区分不同智能体 |

### 智能体配置目录

每个智能体在 `configs/` 下有独立子目录：

| 智能体 | 配置目录 | 包含文件 |
| ------ | -------- | -------- |
| desk-agent（桌面管理助手） | `configs/desk-agent/` | prompts.yaml、schema_metadata.yaml、ops_reports.yaml |
| ticket-agent（工单系统助手） | `configs/ticket-agent/` | prompts.yaml、schema_metadata.yaml |

### 数据隔离

| 隔离维度 | 机制 |
| -------- | ---- |
| 数据库连接 | 每个智能体在 agents.yaml 中配置独立的数据库连接 |
| RAG 集合 | 每个智能体有独立的 docs_collection / sql_collection |
| 聊天记录 | conversations / messages 表通过 agent_type 字段区分 |
| 运维简报 | ops_report 表通过 agent_type 字段区分 |
| 任务执行 | task_executions 表通过 agent_type 字段区分 |
| 知识库 | knowledge_entries 表通过 agent_type 字段区分 |

---

## 核心模块

### 1. LangGraph Agent (`agent/`)

**基于 LangGraph StateGraph 的智能体编排，通过 Tool Calling 实现 LLM 自主决策，取代了旧版关键词+正则的硬路由方案。**

#### 图拓扑

```
init → agent → [should_continue]
                    ├── "tools" → tool_result → agent（循环，最多 max_tool_calls 次）
                    └── "respond" → respond → END
```

#### 节点

| 节点 | 函数 | 职责 |
| ---- | ---- | ---- |
| `init` | `init_node` | 注入系统 Prompt，初始化状态字段 |
| `agent` | `agent_node` | LLM 决策节点，`bind_tools(ALL_TOOLS)` 让 LLM 选择工具 |
| `tools` | `tool_result_node` | 执行工具调用，收集结果到对应列表 |
| `respond` | `respond_node` | 终止节点（回答已通过流式输出） |

#### 条件路由 `should_continue`

- `tool_call_count >= max_tool_calls` → `"respond"`（防死循环）
- `force_finalize_after_sql` 为 True → `"respond"`（SQL 结果过大时强制收尾）
- AIMessage 含 `tool_calls` → `"tools"`
- 否则 → `"respond"`

#### AgentState 状态定义

| 字段 | 类型 | 说明 |
| ---- | ---- | ---- |
| `messages` | `Annotated[list, add_messages]` | 对话消息列表（reducer 自动合并） |
| `last_llm_input_messages` | `list` | 最近一次传给 LLM 的消息列表快照 |
| `question` | `str` | 用户原始问题 |
| `session_id` | `str` | 数据库连接会话 ID |
| `agent_type` | `str` | 当前智能体类型标识 |
| `lognum` | `str` | 用户工号（权限控制） |
| `images_base64` | `list[str] \| None` | 用户上传图片 |
| `sql_results` | `list[dict]` | SQL 查询结果累积 |
| `rag_results` | `list[dict]` | RAG 检索结果累积 |
| `metadata_results` | `list[dict]` | 元数据查询结果累积 |
| `time_results` | `list[dict]` | 时间查询结果累积 |
| `calculator_results` | `list[dict]` | 计算器结果累积 |
| `chart_configs` | `list[dict]` | 图表配置累积 |
| `export_results` | `list[dict]` | 导出结果累积 |
| `web_search_results` | `list[dict]` | 网络搜索结果累积 |
| `tool_call_count` | `int` | 已执行工具调用次数 |
| `max_tool_calls` | `int` | 最大工具调用次数限制（默认 10） |
| `force_finalize_after_sql` | `bool` | SQL 结果过大时强制收尾 |
| `force_finalize_reason` | `str` | 强制收尾原因 |
| `data_tables` | `list[str]` | SQL 结果的 Markdown 表格列表 |
| `references` | `list[str]` | RAG 参考来源列表 |
| `pre_sql_context` | `dict \| None` | SQL 调用前的上下文快照 |

#### 8 个工具

| 工具 | 文件 | 功能 | 入参 |
| ---- | ---- | ---- | ---- |
| `sql_query` | sql_tool.py | 自然语言→SQL 生成并执行查询 | `question: str` |
| `rag_search` | rag_tool.py | 混合检索知识库文档片段 | `question: str` |
| `metadata_query` | metadata_tool.py | 查询数据库表结构信息 | `table_name: str \| None` |
| `get_current_time` | time_tool.py | 获取当前日期时间和常用日期范围 | 无 |
| `calculator` | calculator_tool.py | 安全执行数学表达式计算 | `expression: str` |
| `generate_chart` | chart_tool.py | 生成 ECharts 图表配置（柱/折/饼） | `chart_type, title, data, x_field, y_field` |
| `export_data` | export_tool.py | 导出数据为 Excel/CSV 文件 | `data, filename, format` |
| `web_search` | web_search_tool.py | 通过 Tavily API 搜索互联网 | `query: str` |

#### 流式输出 (`stream.py`)

将 LangGraph `astream_events` v2 事件流转换为 SSE 格式推送到前端：

| SSE 事件 | 数据格式 | 触发时机 |
| -------- | -------- | -------- |
| `start` | `{intent, session_id, conversation_id}` | 对话开始 |
| `status` | 状态文本 | 工具调用中状态更新 |
| `delta` | 文本片段 | LLM 逐 token 输出 |
| `replace` | 完整文本 | 替换当前消息内容 |
| `chart` | echarts_option | 图表工具执行完成 |
| `export` | download_url | 导出工具执行完成 |
| `done` | `{route, session_id}` | 对话完成 |
| `error` | `{"error": "..."}` | 异常发生 |

#### LLM 工厂 (`llm/factory.py`)

| 函数 | 用途 | 特点 |
| ---- | ---- | ---- |
| `get_llm` | Agent 主 LLM | 流式、temperature=0.3、支持 Tool Calling |
| `get_sql_llm` | SQL 生成专用 | 同步、temperature=0.0、确保确定性 |

**思考关闭策略**（根据 base_url 自动判断后端类型，减少响应延迟）：

- DashScope → `enable_thinking: False`
- DeepSeek → `thinking.type: disabled`
- Ollama 等 → `reasoning_effort: none`

---

### 2. SQL Agent (`sql_agent/`)

**自然语言转 SQL 的安全查询引擎，支持 RAG 辅助生成和多重安全校验。**

#### 模块组成

| 文件 | 职责 |
| ---- | ---- |
| `service.py` | 编排层：RAG 检索 → Prompt 构建 → LLM 生成 → 安全校验 |
| `prompt_builder.py` | Prompt 构建：注入表结构、同义词、安全规则和 SQL 样本 |
| `sql_safety.py` | 安全校验：仅允许 SELECT、禁止危险关键字/受限表/敏感列 |
| `executor.py` | SQL 执行：强制 LIMIT、自动重试、连接异常自动重建 |
| `connection_manager.py` | 连接管理：单例、会话级复用、60 分钟过期、健康检查+自动重连 |
| `types.py` | 类型定义：SqlGenRequest / SqlGenResult |
| `utils.py` | 工具函数 |

#### SQL 生成流程

```
用户问题 → generate_secure_sql()
  → 1. RAG 检索 SQL 样本 (retrieval.py)
       → 构建 Prompt (prompt_builder.py)
       → LLM 生成 SQL (factory.py, temperature=0.0)
       → 安全校验 (sql_safety.py)
       → 返回安全 SQL
```

#### 安全防护

- **SQL 注入防护**：仅允许 SELECT 语句，禁止 INSERT/UPDATE/DELETE/DROP 等
- **敏感列过滤**：`enforce_deny_select_columns` 禁止查询密码等敏感字段
- **受限表管控**：`enforce_restricted_tables` 限制访问管理员相关表
- **权限控制**：基于 `admin_department_scope_v1` 规则，按管理员工号限制可见部门与设备
- **结果限制**：强制添加 LIMIT，默认最大 500 行
- **溢出处理**：结果超过 5000 行自动截断并生成下载链接

---

### 3. RAG Engine (`rag_engine/`)

**文档知识库的检索增强问答引擎，支持混合检索和增量更新。**

#### 模块组成

| 文件 | 职责 |
| ---- | ---- |
| `ingest.py` | 导入主流程：收集文件 → 计算指纹 → 增量判断 → 解析 → 分块 → 向量化 → 写入 Qdrant |
| `retrieval.py` | 混合检索：向量检索 + BM25 关键词检索加权融合（alpha 可配） |
| `qdrant_store.py` | Qdrant 封装：collection 管理、upsert、search、delete |
| `embedding.py` | 文本向量化：FastEmbed (BAAI/bge-small-zh-v1.5) |
| `chunking.py` | Markdown 分块：按标题分节 → 按段落分割 → 按字符强制分割 → 块间 overlap |
| `sql_samples.py` | SQL 样本管理：SQL 样本库的加载与检索辅助 |
| `settings.py` | 配置定义：pydantic-settings 环境变量自动绑定 |
| `state.py` | 增量状态：JSON 文件持久化文件 SHA-256 指纹 |

#### 文档导入流程

```
API/CLI → ingest_directory()
  → 1. 递归收集文件（按扩展名过滤）
  → 2. 计算 SHA-256 指纹（增量判断）
  → 3. 解析文档（Docling / 视觉模型）
  → 4. Markdown 分块（保留标题层级）
  → 5. 向量化（FastEmbed）
  → 6. 写入 Qdrant（稳定 ID = hash + chunk_index）
  → 7. 保存状态（JSON 持久化指纹）
```

#### 混合检索

```
查询文本 → hybrid_search()
  ├─ 向量检索：query → embedding → Qdrant cosine search → 语义相似度排序
  ├─ BM25 检索：query → 中英文分词 → Okapi BM25 → 关键词匹配排序
  └─ 加权融合：final_score = alpha × vector_score + (1-alpha) × bm25_score
      - 文档检索 alpha=0.7（偏重语义）
      - SQL 样本检索 alpha=0.8（更偏重语义匹配）
```

---

### 4. 任务引擎 (`task_engine/`)

**基于注册表模式的任务执行引擎，支持多智能体任务的注册、执行和状态管理。与 Qt 桌面桥接程序（XFAgentBridge）配合实现桌面管理操作。**

#### 模块组成

| 文件 | 职责 |
| ---- | ---- |
| `base.py` | 任务基类：定义任务接口和通用逻辑 |
| `registry.py` | 任务注册表：按 agent_type 注册和查找任务类 |
| `executor.py` | 任务执行器：执行任务并记录结果到 task_executions 表 |
| `schemas.py` | 任务数据模型：任务参数、执行结果的 Pydantic 模型 |
| `tasks/` | 具体任务实现目录 |
| `tasks/desk_agent/` | 桌面管理助手任务（file_push / power_saving / realtime_status / wallpaper_deploy） |

#### 任务执行流程

```
前端任务模式 → POST /{agent_type}/tasks
  → TaskExecutor.execute()
    → 从 TaskRegistry 查找任务类
    → 实例化任务 → 校验参数
    → 执行任务（本地或通过 XFAgentBridge 桥接）
    → 记录执行结果到 task_executions 表
    → 返回执行结果
```

#### 桌面桥接（Qt Bridge）

```
前端 → localDeskBridge.js → XFAgentBridge (http://127.0.0.1:17891)
  → Qt 程序接收任务 → 调用本地 C++ API → 返回结果
```

---

### 5. 运维简报 (`ops_reports/`)

**定时生成运维简报，支持指标快照趋势对比和未读通知。**

#### 模块组成

| 文件 | 职责 |
| ---- | ---- |
| `manager.py` | 简报管理器：定时调度、简报生成、未读管理、生命周期控制 |
| `executor.py` | 简报执行器：执行 SQL 查询 → 生成简报 → 保存指标快照 |

#### 简报生成流程

```
定时触发 / 手动触发 → OpsReportManager.generate_report()
  → 读取 ops_reports.yaml 配置
  → 逐项执行 SQL 查询
  → 与上次指标快照对比趋势
  → LLM 生成简报摘要
  → 保存 OpsReport + OpsMetricSnapshot
  → 前端 OpsReportInbox 展示未读简报
```

---

### 6. 外部集成 (`integrations/`)

**与第三方系统的集成模块。**

| 子模块 | 文件 | 职责 |
| ------ | ---- | ---- |
| chat_history_push | `reporter.py` | 第三方会话上报：将聊天记录推送到外部系统 |
| chat_history_push | `schemas.py` | 推送数据模型定义 |

---

### 7. 聊天历史 (`db/`)

**基于 SQLite 的聊天历史持久化，支持多会话管理、运维简报和任务数据存储。**

#### 模块组成

| 文件 | 职责 |
| ---- | ---- |
| `chat_history.py` | 异步引擎（aiosqlite）、会话工厂、WAL 模式、初始化 |
| `models.py` | ORM 模型：Conversation、Message、OpsReport、OpsMetricSnapshot、TaskExecution、KnowledgeEntry |

#### 数据模型

| 模型 | 表名 | 关键字段 |
| ---- | ---- | -------- |
| `Conversation` | conversations | id(UUID), title, user_id, agent_type, created_at, updated_at, is_deleted |
| `Message` | messages | id(自增), conversation_id(外键), role(user/assistant), content, intent, charts(JSON) |
| `OpsReport` | ops_report | report_id, report_key, title, summary, content_md, severity, unread, agent_type, generated_at |
| `OpsMetricSnapshot` | ops_metric_snapshot | id, report_id(外键), report_key, snapshot_data, created_at |
| `TaskExecution` | task_executions | id, execution_id, agent_type, task_id, user_id, params, status, result, conversation_id |
| `KnowledgeEntry` | knowledge_entries | id, agent_type, kb_type, filename, title, scenario, key_tables, sql_code, answer, is_deleted |

---

### 8. LLM 客户端 (`llm/`)

**统一封装大语言模型调用，支持多后端切换。**

| 文件 | 职责 |
| ---- | ---- |
| `factory.py` | LLM 工厂：get_llm（Agent 主 LLM，流式）、get_sql_llm（SQL 专用，同步温度0） |
| `clients.py` | 底层 HTTP 客户端：OpenAICompatibleClient（推荐）、OllamaChatClient（兼容保留） |

**自动模型切换**：消息含图片时自动切换到视觉模型（如 qwen2.5-vl:7b）。

---

### 9. 核心基础层 (`core/`)

| 文件 | 职责 |
| ---- | ---- |
| `config.py` | 统一配置加载：环境变量、agents.yaml Pydantic 模型、数据库 URL 构建、Schema YAML 加载 + 内存索引 |
| `context.py` | agent_type 上下文变量：contextvars 跨请求链路传递当前智能体类型 |
| `schema_models.py` | Pydantic 模型，定义数据库元数据的完整校验规则 |
| `errors.py` | AppError 异常类 + 全局异常处理器，统一 JSON 错误格式 + request_id |
| `logging.py` | 彩色日志格式化器 + RequestIdFilter，SQL 日志紫色、错误日志红色 |
| `request_id.py` | ContextVar 请求 ID + Starlette 中间件，贯穿日志和错误响应 |
| `sse.py` | SSE 流式响应工具函数 |

---

### 10. 前端 (`agent_frontend/`)

**Vue 3 SPA 聊天界面，支持多智能体切换、SSE 流式对话、图片上传、Markdown 渲染、会话管理、ECharts 图表、任务模式、知识库管理和运维简报。**

#### 路由结构

```
/ → 重定向到上次使用的智能体或默认智能体
/:agentType → AgentLayout.vue（智能体主界面）
/:agentType/knowledge → KnowledgePage.vue（知识库管理页面）
```

#### 组件树

```
App.vue (根组件，RouterView)
├── AgentLayout.vue (智能体布局，Sidebar + ChatBox)
│   ├── Sidebar.vue (侧边栏)
│   │   └── 历史会话列表（新建/切换/重命名/删除）
│   │   └── OpsReportInbox.vue (运维简报收件箱)
│   └── ChatBox.vue (主聊天组件)
│       ├── MessageBubble.vue (消息气泡)
│       │   ├── 用户消息（蓝色气泡，右侧对齐）
│       │   ├── 助手消息（白色气泡，意图标签 + Markdown + 代码高亮）
│       │   └── ChartBlock.vue (ECharts 图表渲染)
│       ├── ImageUploader.vue (图片上传按钮)
│       ├── mode/ModeToggle.vue (对话/任务模式切换)
│       └── task/ (任务模式组件)
│           ├── TaskModePanel.vue (任务面板)
│           ├── TaskWizard.vue (任务向导)
│           ├── TaskCard.vue (任务卡片)
│           ├── TaskResult.vue (任务结果)
│           ├── TaskStepForm.vue (步骤表单)
│           ├── TaskStepIndicator.vue (步骤指示器)
│           └── FileBrowserModal.vue (文件浏览弹窗)
└── KnowledgePage.vue (知识库管理)
    └── KnowledgeBasePanel.vue (知识库面板)
```

#### 状态管理

| 模块 | 职责 |
| ---- | ---- |
| `composables/useConversations.js` | 会话状态管理（模块级单例 ref），提供 CRUD 操作 |
| `composables/useTaskMode.js` | 任务模式状态管理，任务执行和结果展示 |
| `api/agents.js` | 智能体列表 API，获取已启用智能体和默认智能体 |
| `api/chat.js` | SSE 流式通信封装（AbortController 支持中断） |
| `api/conversations.js` | 会话 API 封装（原生 fetch） |
| `api/knowledge.js` | 知识库 API 封装 |
| `api/opsReports.js` | 运维简报 API 封装 |
| `api/tasks.js` | 任务 API 封装 |
| `api/localDeskBridge.js` | 本地桌面桥接 API（直连 XFAgentBridge） |
| `utils/externalIdentity.js` | 外部身份工具（解析 URL 参数中的用户身份） |
| `config.js` | 三层配置覆盖：运行时注入 > 环境变量 > 默认值 |

#### SSE 流式通信

| 事件 | 数据 | 前端处理 |
| ---- | ---- | -------- |
| `start` | `{intent, session_id, conversation_id}` | 显示意图标签（sql=蓝色, rag=绿色） |
| `status` | 状态文本 | 显示工具调用状态 |
| `delta` | 文本片段 | 追加到消息内容，打字光标动画 |
| `replace` | 完整文本 | 替换当前消息内容 |
| `chart` | echarts_option | 渲染 ECharts 图表 |
| `export` | download_url | 显示下载链接 |
| `done` | `{route, session_id}` | 停止加载状态 |
| `error` | `{error}` | 显示错误消息 |

---

## API 路由

### 全局路由（无 agent_type 前缀）

| **路径** | **方法** | **功能** | **关键依赖** |
| -------- | -------- | -------- | ------------ |
| `/api/v1/agents` | GET | 获取已启用智能体列表 | agent/registry |
| `/api/v1/health` | GET | 健康检查 | ops_reports/manager |
| `/api/v1/metadata/summary` | GET | 数据库元数据摘要 | core/config |
| `/api/v1/sql-agent` | POST | SQL 查询代理（独立入口） | sql_agent/service |
| `/api/v1/export/download/{filename}` | GET | 导出文件下载 | 本地文件系统 |

### 智能体路由（/{agent_type}/ 前缀）

| **路径** | **方法** | **功能** | **关键依赖** |
| -------- | -------- | -------- | ------------ |
| `/{agent_type}/chat` | POST | 统一聊天入口（SSE 流式） | agent/graph, agent/stream |
| `/{agent_type}/chat/end` | POST | 结束对话，关闭数据库连接 | connection_manager |
| `/{agent_type}/conversations` | GET | 获取对话列表（分页） | db/chat_history |
| `/{agent_type}/conversations` | POST | 创建新对话 | db/chat_history |
| `/{agent_type}/conversations/{id}` | GET | 获取对话详情及消息 | db/chat_history |
| `/{agent_type}/conversations/{id}/title` | PUT | 更新对话标题 | db/chat_history |
| `/{agent_type}/conversations/{id}` | DELETE | 删除对话 | db/chat_history |
| `/{agent_type}/rag` | POST | RAG 文档问答（独立入口） | rag_engine |
| `/{agent_type}/rag/sync` | POST | 触发文档知识库同步 | rag_engine/ingest |
| `/{agent_type}/rag/sync-sql` | POST | 触发 SQL 样本库同步 | rag_engine/ingest |
| `/{agent_type}/rag/sync/{job_id}` | GET | 查询同步任务状态 | rag_engine/state |
| `/{agent_type}/ops` | GET | 获取运维简报列表 | ops_reports/manager |
| `/{agent_type}/ops/{report_id}` | GET | 获取简报详情 | ops_reports/manager |
| `/{agent_type}/ops/{report_id}/read` | PUT | 标记简报已读 | ops_reports/manager |
| `/{agent_type}/ops/generate` | POST | 手动触发简报生成 | ops_reports/manager |
| `/{agent_type}/knowledge` | GET | 获取知识库条目列表 | db/models |
| `/{agent_type}/knowledge` | POST | 创建知识库条目 | db/models |
| `/{agent_type}/knowledge/{id}` | PUT | 更新知识库条目 | db/models |
| `/{agent_type}/knowledge/{id}` | DELETE | 删除知识库条目 | db/models |
| `/{agent_type}/tasks` | POST | 执行任务 | task_engine/executor |
| `/{agent_type}/tasks/{execution_id}` | GET | 查询任务执行状态 | task_engine/executor |

---

## 项目结构

```
agent_project/
├── agent_backend/                # 后端服务
│   ├── main.py                   #   应用入口（工厂模式 + lifespan）
│   ├── agent/                    # LangGraph Agent 编排层
│   │   ├── graph.py              #   StateGraph 构建（init→agent→tools→respond）
│   │   ├── nodes.py              #   节点函数 + 条件路由
│   │   ├── state.py              #   AgentState TypedDict 定义
│   │   ├── prompts.py            #   系统 Prompt 获取接口（从 AgentRegistry）
│   │   ├── registry.py           #   AgentRegistry 智能体注册表
│   │   ├── history.py            #   历史对话管理（压缩/摘要/话题切换检测）
│   │   ├── stream.py             #   astream_events → SSE 流式适配
│   │   └── tools/                #   8 个工具实现
│   │       ├── sql_tool.py       #     自然语言→SQL 生成并执行
│   │       ├── rag_tool.py       #     知识库混合检索
│   │       ├── metadata_tool.py  #     数据库表结构查询
│   │       ├── time_tool.py      #     当前时间 + 日期范围
│   │       ├── calculator_tool.py#     安全数学计算（AST 白名单）
│   │       ├── chart_tool.py     #     ECharts 图表配置生成
│   │       ├── export_tool.py    #     数据导出 Excel/CSV
│   │       └── web_search_tool.py#     Tavily 网络搜索
│   ├── api/                      # API 路由层
│   │   ├── routes.py             #   路由总入口（统一 /api/v1 前缀 + /{agent_type} 区分）
│   │   ├── external_identity.py  #   外部身份认证（HMAC 签名校验）
│   │   └── v1/                   #   各功能路由
│   │       ├── agents.py         #     智能体列表
│   │       ├── chat.py           #     聊天 API（SSE 流式 + 消息持久化）
│   │       ├── conversations.py  #     会话管理 API
│   │       ├── rag.py            #     RAG 同步接口
│   │       ├── sql_agent.py      #     SQL 代理接口
│   │       ├── metadata.py       #     元数据摘要
│   │       ├── ops.py            #     运维简报接口
│   │       ├── knowledge.py      #     知识库管理接口
│   │       ├── tasks.py          #     任务执行接口
│   │       ├── export.py         #     文件下载
│   │       └── health.py         #     健康检查
│   ├── configs/                  # 业务配置 YAML（Docker 挂载）
│   │   ├── agents.yaml           #   智能体总控配置
│   │   ├── desk-agent/           #   桌面管理助手配置
│   │   │   ├── prompts.yaml      #     系统提示词
│   │   │   ├── schema_metadata.yaml # 数据库元数据
│   │   │   └── ops_reports.yaml  #     运维简报配置
│   │   └── ticket-agent/         #   工单系统助手配置
│   │       ├── prompts.yaml      #     系统提示词
│   │       └── schema_metadata.yaml # 数据库元数据
│   ├── core/                     # 核心基础层
│   │   ├── config.py             #   统一配置加载 + agents.yaml Pydantic 模型
│   │   ├── context.py            #   agent_type 上下文变量
│   │   ├── schema_models.py      #   Schema 元数据 Pydantic 模型
│   │   ├── errors.py             #   AppError + 全局异常处理器
│   │   ├── logging.py            #   彩色日志 + RequestIdFilter
│   │   ├── request_id.py         #   ContextVar 请求 ID 中间件
│   │   └── sse.py                #   SSE 流式响应工具
│   ├── db/                       # 聊天历史持久化
│   │   ├── chat_history.py       #   异步引擎 + 会话工厂（WAL 模式）
│   │   └── models.py             #   ORM 模型（Conversation/Message/OpsReport/OpsMetricSnapshot/TaskExecution/KnowledgeEntry）
│   ├── integrations/             # 外部集成
│   │   └── chat_history_push/    #   第三方会话上报
│   │       ├── reporter.py       #     推送上报器
│   │       └── schemas.py        #     推送数据模型
│   ├── llm/                      # LLM 调用层
│   │   ├── clients.py            #   底层 HTTP 客户端（OpenAI 兼容 + Ollama 原生）
│   │   └── factory.py            #   LLM 工厂（get_llm / get_sql_llm）
│   ├── ops_reports/              # 运维简报
│   │   ├── manager.py            #   简报管理器（定时调度 + 未读管理）
│   │   └── executor.py           #   简报执行器（SQL 查询 + 趋势对比 + LLM 摘要）
│   ├── rag_engine/               # RAG 检索增强生成引擎
│   │   ├── ingest.py             #   文档导入主流程
│   │   ├── retrieval.py          #   混合检索（向量 + BM25）
│   │   ├── qdrant_store.py       #   Qdrant 向量数据库封装
│   │   ├── embedding.py          #   FastEmbed 文本向量化
│   │   ├── chunking.py           #   Markdown 文档分块
│   │   ├── sql_samples.py        #   SQL 样本库管理
│   │   ├── settings.py           #   pydantic-settings 配置
│   │   └── state.py              #   增量导入状态管理
│   ├── sql_agent/                # SQL 代理模块
│   │   ├── service.py            #   SQL 生成编排层
│   │   ├── prompt_builder.py     #   SQL Prompt 构建
│   │   ├── sql_safety.py         #   SQL 安全校验
│   │   ├── executor.py           #   SQL 执行器
│   │   ├── connection_manager.py #   数据库连接管理
│   │   ├── types.py              #   类型定义
│   │   └── utils.py              #   工具函数
│   └── task_engine/              # 任务引擎
│       ├── base.py               #   任务基类
│       ├── registry.py           #   任务注册表
│       ├── executor.py           #   任务执行器
│       ├── schemas.py            #   任务数据模型
│       └── tasks/                #   具体任务实现
│           └── desk_agent/       #     桌面管理助手任务
│               ├── file_push.py  #       文件推送
│               ├── power_saving.py #     节能策略
│               ├── realtime_status.py #  实时状态查询
│               └── wallpaper_deploy.py # 壁纸部署
├── agent_frontend/               # 前端服务
│   └── src/
│       ├── main.js               #   入口文件
│       ├── App.vue               #   根组件（RouterView）
│       ├── AgentLayout.vue       #   智能体布局组件
│       ├── KnowledgePage.vue     #   知识库管理页面
│       ├── config.js             #   运行时配置（三层覆盖）
│       ├── style.css             #   全局样式 + Markdown 渲染样式
│       ├── api/                  #   API 通信层
│       │   ├── agents.js         #     智能体 API
│       │   ├── chat.js           #     SSE 流式通信封装
│       │   ├── conversations.js  #     会话 CRUD API
│       │   ├── knowledge.js      #     知识库 API
│       │   ├── localDeskBridge.js #    本地桌面桥接 API
│       │   ├── opsReports.js     #     运维简报 API
│       │   └── tasks.js          #     任务 API
│       ├── components/           #   UI 组件
│       │   ├── ChatBox.vue       #     主聊天组件
│       │   ├── MessageBubble.vue #     消息气泡（Markdown + 代码高亮）
│       │   ├── Sidebar.vue       #     侧边栏（会话列表）
│       │   ├── ChartBlock.vue    #     ECharts 图表渲染
│       │   ├── ImageUploader.vue #     图片上传
│       │   ├── KnowledgeBasePanel.vue # 知识库面板
│       │   ├── OpsReportInbox.vue #    运维简报收件箱
│       │   ├── mode/             #     模式切换
│       │   │   └── ModeToggle.vue #      对话/任务模式切换
│       │   └── task/             #     任务相关组件
│       │       ├── TaskModePanel.vue  # 任务模式面板
│       │       ├── TaskWizard.vue     # 任务向导
│       │       ├── TaskCard.vue       # 任务卡片
│       │       ├── TaskResult.vue     # 任务结果
│       │       ├── TaskStepForm.vue   # 步骤表单
│       │       ├── TaskStepIndicator.vue # 步骤指示器
│       │       └── FileBrowserModal.vue # 文件浏览弹窗
│       ├── composables/          #   组合函数
│       │   ├── useConversations.js #   会话状态管理
│       │   └── useTaskMode.js    #     任务模式状态管理
│       ├── router/               #   路由
│       │   └── index.js          #     路由配置（/:agentType 多智能体路由）
│       └── utils/                #   工具函数
│           └── externalIdentity.js #   外部身份工具
├── qt/                           # Qt 桌面桥接程序
│   └── XFAgentBridge/            #   桌面管理桥接服务
│       └── src/                  #     C++ 源码（BridgeSettings/HttpServerController/TaskProcessor/TaskReceiver）
├── data/                         # 运行时数据（每个智能体独立子目录）
│   └── desk-agent/
│       └── sql/                  #   SQL 样本库
├── docker/                       # Docker 构建文件
│   ├── Dockerfile.backend        #   后端生产镜像
│   ├── Dockerfile.backend.base   #   后端基础镜像
│   ├── Dockerfile.frontend       #   前端生产镜像（多阶段构建 Node→Nginx）
│   ├── Dockerfile.docling-sync   #   Docling 同步服务镜像
│   ├── Dockerfile.docling-sync.base # Docling 同步基础镜像
│   ├── nginx.conf                #   Nginx 反向代理 + SSE 支持
│   ├── deploy.bat / deploy.sh    #   部署脚本
│   ├── build-base.ps1 / build-base.sh # 基础镜像构建脚本
│   ├── build-docling-sync.ps1 / build-docling-sync.sh # Docling 镜像构建脚本
│   ├── entrypoint.frontend.sh    #   前端入口脚本（运行时配置注入）
│   ├── BASE_IMAGE_GUIDE.md       #   基础镜像构建指南
│   └── README.md                 #   部署说明
├── docs/                         # 项目文档
├── scripts/                      # 工具脚本
│   ├── start_backend.py          #   启动后端服务
│   ├── stop_backend.bat          #   停止后端服务
│   ├── sync.py / sync.cmd / sync.ps1 # 同步脚本
│   ├── sync_docs.py              #   文档同步
│   ├── sync_rag.py               #   RAG 数据同步
│   ├── sync_sql_samples.py       #   SQL 样本同步
│   ├── ops_report.cmd / ops_report.ps1 / ops_report_docker.cmd # 运维简报脚本
│   └── 诊断工具.py / 测试数据库连接.py # 诊断工具
├── .env.example                  # 环境变量模板
├── requirements.txt              # Python 依赖
├── requirements-docling.txt      # Docling 依赖
├── docker-compose.yml            # 容器编排（backend + frontend + docling-sync + qdrant）
└── PROJECT.md                    # 本文件
```

---

## 核心数据流

### 聊天主流程

```
前端 → POST /{agent_type}/chat (SSE)
  → chat.py 解析 agent_type，设置上下文
  → 构建 AgentState（含 agent_type）
  → 自动创建/关联 Conversation 记录
  → get_agent_graph() 获取 LangGraph 单例
  → stream_graph_response() 异步生成器
    → LangGraph 执行: init → agent
      → LLM bind_tools(8 tools) 自主决策
      ├── 调用工具 → tool_result_node → 回到 agent（循环）
      └── 不调用工具 → respond → END
    → astream_events v2 捕获:
      ├── on_chat_model_stream → SSE delta（逐 token）
      └── on_tool_end → SSE chart / export
  → 后台保存用户/助手消息到 DB
  → 前端渲染完整回答
```

### SQL 生成流程

```
sql_query 工具被调用
  → get_schema_runtime(agent_type) 加载对应智能体的 Schema 元数据
  → search_sql_samples() RAG 检索相似 SQL 样本
  → build_sql_prompt() 构建 Prompt（表结构 + 同义词 + 样本 + 安全规则）
  → get_sql_llm() 生成 SQL（temperature=0.0）
  → validate_sql_basic() 安全校验（仅允许 SELECT）
  → enforce_deny_select_columns() 敏感列过滤
  → execute_sql() 执行查询（强制 LIMIT + 自动重试）
  → 格式化结果（Markdown 表格，预览 20 行 + 下载链接）
```

### 任务执行流程

```
前端任务模式 → POST /{agent_type}/tasks
  → tasks.py 解析 agent_type 和任务参数
  → TaskExecutor.execute()
    → 从 TaskRegistry 查找任务类
    → 校验参数 → 实例化任务
    → 执行任务（本地或通过 XFAgentBridge 桥接）
    → 记录到 task_executions 表
    → 返回执行结果
```

### 运维简报生成流程

```
定时触发 / 手动触发 → OpsReportManager.generate_report()
  → 读取 ops_reports.yaml 配置
  → 逐项执行 SQL 查询
  → 与上次 OpsMetricSnapshot 对比趋势
  → LLM 生成简报摘要
  → 保存 OpsReport + OpsMetricSnapshot
  → 前端 OpsReportInbox 展示未读简报
```

### RAG 文档导入流程

```
POST /{agent_type}/rag/sync 或 CLI
  → ingest_directory()
    → 1. 递归收集文件（按扩展名过滤）
    → 2. 计算 SHA-256 指纹（增量判断，跳过未变更文件）
    → 3. 解析文档（Docling / 视觉模型）
    → 4. Markdown 分块（保留标题层级 + overlap）
    → 5. 向量化（FastEmbed bge-small-zh-v1.5）
    → 6. 写入 Qdrant（稳定 ID = hash + chunk_index）
    → 7. 保存状态（JSON 持久化指纹）
```

---

## 应用启动流程

```
main.py → create_app()
  → lifespan 启动:
    1. configure_logging()          # 配置日志
    2. init_db()                    # 初始化 SQLite（创建表 + WAL 模式）
    3. _preload_components()        # 预加载组件
       → get_settings()             # 加载配置
       → get_registry()             # 加载 AgentRegistry（agents.yaml + 各智能体配置）
       → get_schema_runtime()       # 加载各智能体 Schema 元数据
       → get_agent_graph()          # 构建 LangGraph
       → get_or_create_embedding()  # 加载 Embedding 模型
       → get_or_create_store()      # 连接 Qdrant
       → get_llm() / get_sql_llm()  # 缓存 LLM 实例
    4. ops_report_manager.start()   # 启动运维简报调度器
  → lifespan 关闭:
    5. ops_report_manager.shutdown() # 优雅关闭简报调度器
    6. conn_manager.shutdown()       # 清理数据库连接池
    7. reset_llm_cache()             # 清理 LLM 缓存
```

---

## 环境变量配置

| **模块** | **变量** | **默认值** | **说明** |
| -------- | -------- | ---------- | -------- |
| **大模型** | `LLM_BASE_URL` | `http://localhost:11434/v1` | LLM 服务地址（OpenAI 兼容） |
| | `LLM_API_KEY` | 空 | API Key（本地留空，云端必填） |
| | `CHAT_MODEL` | `qwen3.5:9b` | 文本对话模型 |
| | `VISION_MODEL` | `qwen3.5:9b` | 视觉模型 |
| | `ENABLE_CLOUD_FALLBACK` | `0` | 云端 API 兜底开关 |
| **数据库** | `DB_TYPE` | `mysql` | 数据库类型（mysql/postgresql） |
| | `DATABASE_URL` | - | 完整连接 URL（优先级更高） |
| | `DB_HOST` / `DB_PORT` / `DB_NAME` | - | 全局默认数据库连接参数 |
| **智能体专属** | `TICKET_DB_HOST` / `TICKET_DB_PORT` / `TICKET_DB_NAME` | - | 工单智能体数据库（在 agents.yaml 中引用） |
| **任务服务** | `DESK_SERVICE_API_URL` | - | 桌管服务 API 地址 |
| | `TICKET_SERVICE_API_URL` | - | 工单服务 API 地址 |
| | `VITE_LOCAL_DESK_BRIDGE_URL` | `http://127.0.0.1:17891` | 本地桌面桥接地址 |
| | `VITE_LOCAL_DESK_BRIDGE_ENABLED` | `true` | 是否启用本地桥接主链路 |
| **RAG** | `RAG_QDRANT_URL` | `http://localhost:6333` | Qdrant 地址 |
| | `RAG_QDRANT_PATH` | 空 | Qdrant 本地存储路径 |
| | `RAG_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 嵌入模型 |
| | `RAG_HYBRID_ALPHA` | `0.7` | 混合检索权重（越大向量权重越高） |
| | `RAG_TOP_K` | `5` | 返回文档数 |
| | `RAG_CANDIDATE_K` | `30` | 候选文档数 |
| | `RAG_VECTOR_MIN_SCORE` | `0.5` | 最低相似度阈值 |
| **SQL** | `RAG_SQL_HYBRID_ALPHA` | `0.8` | SQL 检索更偏重语义 |
| | `RAG_SQL_TOP_K` | `3` | SQL 样本返回数 |
| | `RAG_SQL_CANDIDATE_K` | `15` | SQL 样本候选数 |
| | `SQL_MAX_ROWS` | `500` | SQL 查询最大行数 |
| | `SQL_LOG_FULL_PROMPT` | `1` | 是否打印完整 SQL Prompt |
| **会话** | `CHAT_MAX_HISTORY_ROUNDS` | `6` | 最大保留历史对话轮数 |
| | `CHAT_HISTORY_COMPRESS_THRESHOLD` | `500` | assistant 消息压缩阈值（字符） |
| | `CHAT_TOPIC_SHIFT_THRESHOLD` | `0.15` | 话题切换检测阈值 |
| **聊天历史** | `CHAT_DB_PATH` | `data/chat_history.db` | SQLite 数据库路径 |
| **外部集成** | `THIRD_PARTY_CHAT_HISTORY_BASE_URL` | - | 第三方会话上报地址 |
| | `THIRD_PARTY_CHAT_HISTORY_TIMEOUT_SECONDS` | `3` | 上报超时秒数 |
| | `EXTERNAL_ENTRY_SECRET` | - | 外部入口 HMAC 密钥 |
| | `EXTERNAL_ENTRY_TTL_SECONDS` | `28800` | 外部签名有效期（秒） |
| **其他** | `CHAT_API_TOKEN` | - | API 访问 Token（可选鉴权） |
| | `TAVILY_API_KEY` | - | Tavily 网络搜索 API Key |
| | `WEB_SEARCH_MAX_RESULTS` | `5` | 网络搜索返回数量 |
| | `CORS_ORIGINS` | `http://localhost:3000` | CORS 允许的前端来源 |
| **前端** | `VITE_APP_NAME` | `阳途智能助手` | 应用名称 |
| | `VITE_APP_SUBTITLE` | `阳途智能助手为您服务` | 应用副标题 |
| | `VITE_APP_WELCOME_TEXT` | `有什么我能帮您的呢？` | 欢迎语 |
| | `VITE_APP_INPUT_PLACEHOLDER` | `给智能助手发消息` | 输入框占位文字 |
| | `VITE_QUICK_OPTIONS` | `查看客户端在线状态,...` | 快捷选项 |

---

## 部署架构

```
Docker Compose 编排 4 个服务:

┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   frontend      │  │   backend       │  │   qdrant        │  │   docling-sync  │
│   Nginx :81     │  │   Uvicorn :8000 │  │   REST :6333    │  │   (按需启动)     │
│   Vue 3 SPA     │  │   FastAPI       │  │   gRPC :6334    │  │   文档同步服务   │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                     │                     │
         │   /api/* 代理      │  向量读写            │                     │
         └───────────────────>└────────────────────>│                     │
                              │                                          │
                              │  LLM 调用                                │ 同步文档
                              └─────────> Ollama (Docker 外部)            │
                              │                                          │
                              │  数据库查询                               │
                              └─────────> MySQL/PostgreSQL (外部)        │
                                                                       │
                              ┌──────────────────────────────────────────┘
                              │  按需启动（docker compose --profile docling up）
                              │  同步完成后自动退出
```

---

## 关键设计总结

| 设计要点 | 说明 |
| -------- | ---- |
| **多智能体架构** | agents.yaml 总控 + AgentRegistry 注册表，每个智能体独立配置、独立数据库、独立 RAG 集合 |
| **LangGraph 编排** | StateGraph 定义节点和条件路由，支持工具循环调用，LLM 自主决策替代硬路由 |
| **Tool Calling 意图路由** | LLM 通过 bind_tools 自主选择工具，无需关键词匹配，支持多工具组合调用 |
| **8 种工具** | SQL/RAG/元数据/时间/计算器/图表/导出/网络搜索 |
| **任务引擎** | Task Engine 注册表模式 + Qt 桌面桥接，支持多智能体任务扩展 |
| **运维简报** | 定时生成简报 + 指标快照趋势对比 + 未读通知 |
| **混合检索** | 向量检索（语义）+ BM25（关键词）加权融合，alpha 参数控制权重 |
| **增量同步** | RAG 导入基于文件 SHA-256 指纹跳过未变更文件，避免重复处理 |
| **SSE 流式输出** | astream_events v2 实现逐 token 流式推送，前端实时渲染 |
| **多后端 LLM** | OpenAI 兼容协议统一调用，支持 Ollama/DashScope/DeepSeek 无缝切换 |
| **安全防护** | SQL 安全校验 + 计算器 AST 白名单 + 文件名安全化 + 工具调用次数限制 + 外部入口 HMAC 签名 |
| **连接管理** | 单例 ConnectionManager，会话级连接复用，60 分钟自动过期，健康检查+自动重连 |
| **会话持久化** | SQLite 存储对话和消息，支持多会话切换、重命名、上下文恢复、历史压缩 |
| **链路追踪** | request_id 通过 ContextVar 贯穿日志和错误响应 |
| **统一异常** | AppError + 全局异常处理器，所有错误统一 JSON 格式 + request_id |
| **权限控制** | 基于管理员工号的部门级数据可见范围限制 |
| **外部身份** | HMAC 签名校验外部入口用户身份，支持 URL 参数和 Header 两种方式 |
| **数据隔离** | 每个智能体通过 agent_type 字段实现聊天记录、简报、任务、知识库的数据隔离 |
