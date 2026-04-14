# Desk Agent 系统架构分析

> 为老 C++ 桌面管理系统开发的智能 Agent 助手，提供自然语言"知识文档问答"及"数据库只读数据智能查询"功能。

---

## 系统架构

```
┌──────────────┐     ┌───────────────────────────────────────────────────────┐
│   Frontend   │────▶│                Backend (FastAPI)                      │
│  Vue 3 + Vite│     │                                                       │
└──────────────┘     │  ┌──────────┐    ┌────────────────────────────────┐  │
                     │  │  Chat    │───▶│     LangGraph Agent            │  │
                     │  │  API     │    │  ┌──────────────────────────┐  │  │
                     │  │  (SSE)   │    │  │  init → agent ─┬─tools──┐│  │  │
                     │  └──────────┘    │  │         ↑      ↓        ││  │  │
                     │                  │  │         └──agent←┘       ││  │  │
                     │                  │  │              ↓ respond   ││  │  │
                     │                  │  │              → END       ││  │  │
                     │                  │  └──────────────────────────┘│  │  │
                     │                  │  Tool Calling 自主决策 8 工具 │  │  │
                     │                  └────────────────────────────────┘  │
                     │                         │                             │
                     │        ┌────────────────┼────────────────┐            │
                     │        ↓                ↓                ↓            │
                     │  ┌───────────┐  ┌────────────┐  ┌──────────────┐    │
                     │  │ SQL Agent │  │ RAG Engine │  │ Other Tools  │    │
                     │  │ NL→SQL    │  │ 混合检索    │  │ 时间/计算/   │    │
                     │  │           │  │            │  │ 图表/导出/   │    │
                     │  └─────┬─────┘  └─────┬──────┘  │ 网络搜索     │    │
                     │        ↓              ↓         └──────────────┘    │
                     │  ┌───────────┐  ┌────────────┐                      │
                     │  │ Database  │  │  Qdrant    │                      │
                     │  │ MySQL/PG  │  │ 向量数据库  │                      │
                     │  └───────────┘  └────────────┘                      │
                     │        │                                              │
                     │  ┌─────┴───────────────────────┐                    │
                     │  │  LLM (OpenAI 兼容协议)       │                    │
                     │  │  Ollama / DashScope / DeepSeek│                    │
                     │  └─────────────────────────────┘                    │
                     └───────────────────────────────────────────────────────┘
```

### 核心架构变化

| 对比项 | 旧架构 | 当前架构 |
|--------|--------|----------|
| **意图路由** | 关键词 + 正则评分 → 硬路由到 SQL/RAG | LangGraph Tool Calling → LLM 自主决策调用工具 |
| **Agent 编排** | 无 | LangGraph StateGraph（init → agent → tools 循环 → respond） |
| **工具数量** | 2（SQL 查询 + RAG 检索） | 8（SQL/RAG/元数据/时间/计算器/图表/导出/网络搜索） |
| **LLM 客户端** | Ollama 原生协议为主 | OpenAI 兼容协议为主，支持 Ollama/DashScope/DeepSeek 切换 |
| **流式输出** | Ollama NDJSON 流 | LangGraph astream_events v2 → SSE |
| **聊天模块** | chat/ 目录 | 迁移至 api/v1/chat.py + agent/ 编排层 |

---

## 技术栈

| **层级** | **技术** | **版本** | **说明** |
|----------|----------|----------|----------|
| **前端框架** | Vue 3 | ^3.4.21 | Composition API (`<script setup>`) |
| **构建工具** | Vite | ^5.4.21 | 快速 HMR 开发体验 |
| **样式** | Tailwind CSS | ^3.4.19 | 原子化 CSS |
| **Markdown** | marked + highlight.js | ^12.0.0 / ^11.9.0 | 消息渲染 + 代码高亮 |
| **安全** | DOMPurify | ^3.0.9 | HTML 净化防 XSS |
| **后端框架** | FastAPI | >=0.110 | 异步 Python Web |
| **ASGI** | Uvicorn | >=0.27 | 高性能异步服务器 |
| **数据校验** | Pydantic v2 | >=2.6 | 请求/响应模型 |
| **配置管理** | pydantic-settings | >=2.2 | 环境变量自动绑定 |
| **Agent 框架** | LangGraph | >=0.2, <0.3 | StateGraph 状态机编排 |
| **LLM 调用** | langchain-openai | >=0.3 | OpenAI 兼容协议统一调用 |
| **大模型** | Qwen2.5 (Ollama) | 7b 默认 | 本地部署，支持文本和视觉模型 |
| **向量数据库** | Qdrant | latest | 文档和 SQL 样本的向量存储与检索 |
| **文本嵌入** | FastEmbed (BAAI/bge-m3) | >=0.3 | 中文向量模型，回退 bge-small-zh-v1.5 |
| **文档解析** | Docling | >=2.0 | 支持 docx/xlsx/txt/md/pdf 等格式 |
| **数据库** | SQLAlchemy 2.0 | >=2.0 | 支持 MySQL / PostgreSQL 只读查询 |
| **部署** | Docker Compose + Nginx | - | 前后端 + Qdrant 三容器编排 |

---

## 核心模块

### 1. LangGraph Agent (`agent/`)

**基于 LangGraph StateGraph 的智能体编排，通过 Tool Calling 实现 LLM 自主决策，取代了旧版关键词+正则的硬路由方案。**

#### 图拓扑

```
init → agent → [should_continue]
                    ├── "tools" → tool_result → agent（循环，最多 5 次）
                    └── "respond" → respond → END
```

#### 4 个节点

| 节点 | 函数 | 职责 |
|------|------|------|
| `init` | `init_node` | 注入系统 Prompt，初始化状态字段 |
| `agent` | `agent_node` | LLM 决策节点，`bind_tools(ALL_TOOLS)` 让 LLM 选择工具 |
| `tools` | `tool_result_node` | 执行工具调用，收集结果到对应列表 |
| `respond` | `respond_node` | 终止节点（回答已通过流式输出） |

#### 条件路由 `should_continue`

- `tool_call_count >= max_tool_calls` → `"respond"`（防死循环）
- AIMessage 含 `tool_calls` → `"tools"`
- 否则 → `"respond"`

#### AgentState 状态定义

| 字段 | 类型 | 说明 |
|------|------|------|
| `messages` | `Annotated[list, add_messages]` | 对话消息列表（reducer 自动合并） |
| `question` | `str` | 用户原始问题 |
| `session_id` | `str` | 数据库连接会话 ID |
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
| `max_tool_calls` | `int` | 最大工具调用次数限制（默认 5） |
| `data_tables` | `list[str]` | SQL 结果的 Markdown 表格列表 |
| `references` | `list[str]` | RAG 参考来源列表 |

#### 8 个工具

| 工具 | 文件 | 功能 | 入参 |
|------|------|------|------|
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
|----------|----------|----------|
| `delta` | 文本片段 | LLM 逐 token 输出 |
| `chart` | echarts_option | 图表工具执行完成 |
| `export` | download_url | 导出工具执行完成 |
| `error` | `{"error": "..."}` | 异常发生 |

#### LLM 客户端 (`llm.py`)

| 函数 | 用途 | 特点 |
|------|------|------|
| `get_llm` | Agent 主 LLM | 流式、temperature=0.3、支持 Tool Calling |
| `get_sql_llm` | SQL 生成专用 | 同步、temperature=0.0、确保确定性 |

**思考关闭策略**（根据 base_url 自动判断后端类型，减少响应延迟）：
- DashScope → `enable_thinking: False`
- DeepSeek → `thinking.type: disabled`
- Ollama 等 → `reasoning_effort: none`

---

### 2. SQL Agent (`sql_agent/`)

**自然语言转 SQL 的安全查询引擎，支持模板优先匹配和 RAG 辅助生成。**

#### 模块组成

| 文件 | 职责 |
|------|------|
| `service.py` | 编排层：模板匹配 → RAG 检索 → Prompt 构建 → LLM 生成 → 安全校验 |
| `patterns.py` | 模板匹配：基于 query_patterns 的关键字重叠评分，命中则直接返回预定义 SQL |
| `prompt_builder.py` | Prompt 构建：注入表结构、同义词、安全规则和 SQL 样本 |
| `sql_safety.py` | 安全校验：仅允许 SELECT、禁止危险关键字/受限表/敏感列 |
| `executor.py` | SQL 执行：强制 LIMIT、自动重试、连接异常自动重建 |
| `connection_manager.py` | 连接管理：单例、会话级复用、60 分钟过期、健康检查+自动重连 |
| `types.py` | 类型定义：SqlGenRequest / SqlGenResult |

#### SQL 生成流程

```
用户问题 → generate_secure_sql()
  ├─ 1. 模板匹配 (patterns.py) ──命中──→ 直接返回预定义 SQL
  └─ 2. 未命中 → RAG 检索 SQL 样本 (retrieval.py)
           → 构建 Prompt (prompt_builder.py)
           → LLM 生成 SQL (clients.py, temperature=0.0)
           → 安全校验 (sql_safety.py)
           → 返回安全 SQL
```

#### 安全防护

- **SQL 注入防护**：仅允许 SELECT 语句，禁止 INSERT/UPDATE/DELETE/DROP 等
- **敏感列过滤**：`enforce_deny_select_columns` 禁止查询密码等敏感字段
- **受限表管控**：`enforce_restricted_tables` 限制访问管理员相关表
- **权限控制**：基于 `admin_department_scope_v1` 规则，按管理员工号限制可见部门与设备
- **结果限制**：强制添加 LIMIT，默认最大 500 行

---

### 3. RAG Engine (`rag_engine/`)

**文档知识库的检索增强问答引擎，支持混合检索和增量更新。**

#### 模块组成

| 文件 | 职责 |
|------|------|
| `ingest.py` | 导入主流程：收集文件 → 计算指纹 → 增量判断 → 解析 → 分块 → 向量化 → 写入 Qdrant |
| `retrieval.py` | 混合检索：向量检索 + BM25 关键词检索加权融合（alpha 可配） |
| `qdrant_store.py` | Qdrant 封装：collection 管理、upsert、search、delete |
| `embedding.py` | 文本向量化：FastEmbed (BAAI/bge-m3)，回退 bge-small-zh-v1.5 |
| `chunking.py` | Markdown 分块：按标题分节 → 按段落分割 → 按字符强制分割 → 块间 overlap |
| `docling_parser.py` | 文档解析：Docling 解析 docx/xlsx/pdf 等，视觉模型解析图片 |
| `vision.py` | 视觉模型客户端：OpenAI 兼容协议 / Ollama 原生协议 |
| `settings.py` | 配置定义：pydantic-settings 环境变量自动绑定 |
| `state.py` | 增量状态：JSON 文件持久化文件 SHA-256 指纹 |
| `cli.py` | CLI 入口：命令行执行文档/SQL 样本同步 |

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

### 4. LLM 客户端 (`llm/clients.py`)

**统一封装大语言模型 HTTP 调用，支持多后端切换。**

| 客户端 | 协议 | 推荐度 | 说明 |
|--------|------|--------|------|
| `OpenAICompatibleClient` | OpenAI 兼容 `/v1/chat/completions` | ★★★ 推荐 | 支持 Ollama/DashScope/DeepSeek 切换 |
| `OllamaChatClient` | Ollama 原生 `/api/chat` | 兼容保留 | 旧版客户端 |

**自动模型切换**：消息含图片时自动切换到视觉模型（如 qwen2.5-vl:7b）。

---

### 5. 核心基础层 (`core/`)

| 文件 | 职责 |
|------|------|
| `config_loader.py` | 加载 schema_metadata.yaml，构建内存索引（lru_cache 缓存） |
| `config_helper.py` | 环境变量加载，提供数据库 URL / LLM 配置 / SQL 限制等接口 |
| `schema_models.py` | 14 个 Pydantic 模型，定义数据库元数据的完整校验规则 |
| `errors.py` | AppError 异常类 + 全局异常处理器，统一 JSON 错误格式 + request_id |
| `logging.py` | 彩色日志格式化器 + RequestIdFilter，SQL 日志紫色、错误日志红色 |
| `request_id.py` | ContextVar 请求 ID + Starlette 中间件，贯穿日志和错误响应 |

---

### 6. 前端 (`agent_frontend/`)

**Vue 3 SPA 聊天界面，支持 SSE 流式对话、图片上传、Markdown 渲染。**

#### 组件树

```
App.vue (根组件)
├── header — 标题栏（"AI 智能助手 - 桌管系统智能问答" + 用户名）
└── ChatBox.vue (主聊天组件)
    ├── MessageBubble.vue (消息气泡)
    │   ├── 用户消息（蓝色气泡，右侧对齐）
    │   └── 助手消息（白色气泡，意图标签 + Markdown + 代码高亮）
    └── ImageUploader.vue (图片上传按钮)
```

#### SSE 流式通信

| 事件 | 数据 | 前端处理 |
|------|------|----------|
| `start` | `{intent, session_id}` | 显示意图标签（sql=蓝色, rag=绿色） |
| `delta` | 文本片段 | 追加到消息内容，打字光标动画 |
| `done` | `{route, session_id}` | 停止加载状态 |
| `error` | `{error}` | 显示错误消息 |

---

## API 路由

| **路径** | **方法** | **功能** | **关键依赖** |
|----------|----------|----------|--------------|
| `/api/v1/chat` | POST | 统一聊天入口（SSE 流式） | agent/graph, agent/stream |
| `/api/v1/chat/end` | POST | 结束对话，关闭数据库连接 | connection_manager |
| `/api/v1/rag` | POST | RAG 文档问答（独立入口） | rag_engine |
| `/api/v1/rag/sync` | POST | 触发文档知识库同步 | rag_engine/ingest |
| `/api/v1/rag/sync-sql` | POST | 触发 SQL 样本库同步 | rag_engine/ingest |
| `/api/v1/rag/sync/{job_id}` | GET | 查询同步任务状态 | rag_engine/state |
| `/api/v1/sql-agent` | POST | SQL 查询代理（独立入口） | sql_agent/service |
| `/api/v1/sql/generate` | POST | SQL 生成（可选执行） | sql_agent/service |
| `/api/v1/metadata/summary` | GET | 数据库元数据摘要 | core/config_loader |
| `/api/v1/export/download/{filename}` | GET | 导出文件下载 | 本地文件系统 |
| `/api/v1/health` | GET | 健康检查 | 无 |

---

## 项目结构

```
agent_project/
├── agent_backend/                # 后端服务
│   ├── agent/                    # ★ LangGraph Agent 编排层（核心变更）
│   │   ├── graph.py              #   StateGraph 构建（init→agent→tools→respond）
│   │   ├── nodes.py              #   节点函数 + 条件路由
│   │   ├── state.py              #   AgentState TypedDict 定义
│   │   ├── llm.py                #   LLM 客户端（get_llm / get_sql_llm）
│   │   ├── prompts.py            #   系统 Prompt + 工具使用规则
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
│   │   ├── routes.py             #   路由总入口（统一 /api/v1 前缀）
│   │   └── v1/                   #   各功能路由
│   │       ├── chat.py           #     聊天 API（SSE 流式）
│   │       ├── export.py         #     文件下载
│   │       ├── health.py         #     健康检查
│   │       ├── metadata.py       #     元数据摘要
│   │       ├── rag.py            #     RAG 同步接口
│   │       └── sql_agent.py      #     SQL 代理接口
│   ├── chat/                     # （遗留空模块，功能已迁移至 agent/）
│   ├── configs/
│   │   └── schema_metadata.yaml  #   数据库 Schema 元数据配置
│   ├── core/                     # 核心基础层
│   │   ├── config_loader.py      #   Schema YAML 加载 + 内存索引
│   │   ├── config_helper.py      #   环境变量配置助手
│   │   ├── schema_models.py      #   14 个 Pydantic Schema 模型
│   │   ├── errors.py             #   AppError + 全局异常处理器
│   │   ├── logging.py            #   彩色日志 + RequestIdFilter
│   │   └── request_id.py         #   ContextVar 请求 ID 中间件
│   ├── llm/
│   │   └── clients.py            #   LLM 客户端（OpenAI 兼容 + Ollama 原生）
│   ├── rag_engine/               # RAG 检索增强生成引擎
│   │   ├── ingest.py             #   文档导入主流程
│   │   ├── retrieval.py          #   混合检索（向量 + BM25）
│   │   ├── qdrant_store.py       #   Qdrant 向量数据库封装
│   │   ├── embedding.py          #   FastEmbed 文本向量化
│   │   ├── chunking.py           #   Markdown 文档分块
│   │   ├── docling_parser.py     #   多格式文档解析
│   │   ├── vision.py             #   视觉模型客户端
│   │   ├── settings.py           #   pydantic-settings 配置
│   │   ├── state.py              #   增量导入状态管理
│   │   └── cli.py                #   CLI 命令行入口
│   ├── sql_agent/                # SQL 代理模块
│   │   ├── service.py            #   SQL 生成编排层
│   │   ├── patterns.py           #   查询模板匹配
│   │   ├── prompt_builder.py     #   SQL Prompt 构建
│   │   ├── sql_safety.py         #   SQL 安全校验
│   │   ├── executor.py           #   SQL 执行器
│   │   ├── connection_manager.py #   数据库连接管理
│   │   └── types.py              #   类型定义
│   └── main.py                   # 应用入口（工厂模式）
├── agent_frontend/               # 前端服务
│   └── src/
│       ├── App.vue               #   根组件
│       ├── main.js               #   入口文件
│       ├── style.css             #   全局样式 + Markdown 渲染样式
│       ├── api/
│       │   └── chat.js           #   SSE 流式通信封装
│       └── components/
│           ├── ChatBox.vue       #   主聊天组件
│           ├── MessageBubble.vue #   消息气泡（Markdown + 代码高亮）
│           └── ImageUploader.vue #   图片上传
├── data/desk-agent/              # 知识库数据
│   ├── docs/                     #   文档知识库（docx/xlsx/txt/md）
│   └── sql/                      #   SQL 样本库
├── docker/                       # Docker 构建文件
│   ├── Dockerfile.backend        #   后端镜像
│   ├── Dockerfile.frontend       #   前端镜像
│   ├── nginx.conf                #   Nginx 反向代理配置
│   ├── deploy.bat / deploy.sh    #   部署脚本
│   └── README.md                 #   部署说明
├── scripts/                      # 工具脚本
│   ├── smoke_demo.py             #   冒烟测试
│   ├── test_chat_api.py          #   API 测试
│   ├── sync_sql_samples.py       #   SQL 样本同步
│   └── ...                       #   其他诊断/测试脚本
├── .env.example                  # 环境变量模板
├── requirements.txt              # Python 依赖
├── docker-compose.yml            # 容器编排（backend + frontend + qdrant）
└── PROJECT.md                    # 本文件
```

---

## 核心数据流

### 聊天主流程

```
前端 → POST /api/v1/chat (SSE)
  → chat.py 构建 AgentState
  → get_agent_graph() 获取 LangGraph 单例
  → stream_graph_response() 异步生成器
    → LangGraph 执行: init → agent
      → LLM bind_tools(8 tools) 自主决策
      ├── 调用工具 → tool_result_node → 回到 agent（循环）
      └── 不调用工具 → respond → END
    → astream_events v2 捕获:
      ├── on_chat_model_stream → SSE delta（逐 token）
      └── on_tool_end → SSE chart / export
  → 前端渲染完整回答
```

### SQL 生成流程

```
sql_query 工具被调用
  → get_schema_runtime() 加载 Schema 元数据
  → search_sql_samples() RAG 检索相似 SQL 样本
  → build_sql_prompt() 构建 Prompt（表结构 + 同义词 + 样本 + 安全规则）
  → get_sql_llm() 生成 SQL（temperature=0.0）
  → validate_sql_basic() 安全校验（仅允许 SELECT）
  → enforce_deny_select_columns() 敏感列过滤
  → execute_sql() 执行查询（强制 LIMIT + 自动重试）
  → 格式化结果（Markdown 表格，最多 50 行展示）
```

### RAG 文档导入流程

```
POST /rag/sync 或 CLI
  → ingest_directory()
    → 1. 递归收集文件（按扩展名过滤）
    → 2. 计算 SHA-256 指纹（增量判断，跳过未变更文件）
    → 3. 解析文档（Docling / 视觉模型）
    → 4. Markdown 分块（保留标题层级 + overlap）
    → 5. 向量化（FastEmbed bge-m3）
    → 6. 写入 Qdrant（稳定 ID = hash + chunk_index）
    → 7. 保存状态（JSON 持久化指纹）
```

---

## 环境变量配置

| **模块** | **变量** | **默认值** | **说明** |
|----------|----------|------------|----------|
| **智能体** | `AGENT_NAME` | `desk-agent` | 智能体名称，影响知识库路径 |
| **LLM** | `LLM_BASE_URL` | `http://localhost:11434/v1` | LLM 服务地址（OpenAI 兼容） |
| | `LLM_API_KEY` | `ollama` | API Key（本地留空，云端必填） |
| | `CHAT_MODEL` | `qwen2.5:7b` | 文本对话模型 |
| | `VISION_MODEL` | `qwen2.5-vl:7b` | 视觉模型 |
| | `ENABLE_CLOUD_FALLBACK` | `0` | 云端 API 兜底开关 |
| **数据库** | `DB_TYPE` | `mysql` | 数据库类型（mysql/postgresql） |
| | `DATABASE_URL` | - | 完整连接 URL（优先级更高） |
| **RAG** | `RAG_QDRANT_URL` | `http://localhost:6333` | Qdrant 地址 |
| | `RAG_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 嵌入模型 |
| | `RAG_HYBRID_ALPHA` | `0.7` | 混合检索权重（越大向量权重越高） |
| | `RAG_TOP_K` | `5` | 返回文档数 |
| | `RAG_VECTOR_MIN_SCORE` | `0.5` | 最低相似度阈值 |
| **SQL** | `RAG_SQL_HYBRID_ALPHA` | `0.8` | SQL 检索更偏重语义 |
| | `RAG_SQL_TOP_K` | `3` | SQL 样本返回数 |
| | `SQL_MAX_ROWS` | `500` | SQL 查询最大行数 |
| **其他** | `CHAT_API_TOKEN` | - | API 访问 Token（可选鉴权） |
| | `TAVILY_API_KEY` | - | Tavily 网络搜索 API Key |
| | `WEB_SEARCH_MAX_RESULTS` | `5` | 网络搜索返回数量 |

---

## 部署架构

```
Docker Compose 编排 3 个服务:

┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   frontend      │  │   backend       │  │   qdrant        │
│   Nginx :80     │  │   Uvicorn :8000 │  │   REST :6333    │
│   Vue 3 SPA     │  │   FastAPI       │  │   gRPC :6334    │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                     │
         │   /api/* 代理      │  向量读写            │
         └───────────────────>└────────────────────>│
                              │
                              │  LLM 调用
                              └─────────> Ollama (Docker 外部)
                              │
                              │  数据库查询
                              └─────────> MySQL/PostgreSQL (外部)
```

---

## 关键设计总结

| 设计要点 | 说明 |
|----------|------|
| **LangGraph 编排** | StateGraph 定义节点和条件路由，支持工具循环调用，LLM 自主决策替代硬路由 |
| **Tool Calling 意图路由** | LLM 通过 bind_tools 自主选择工具，无需关键词匹配，支持多工具组合调用 |
| **模板优先** | SQL 生成优先匹配预定义模板，命中则绕过 LLM，降低延迟和成本 |
| **混合检索** | 向量检索（语义）+ BM25（关键词）加权融合，alpha 参数控制权重 |
| **增量同步** | RAG 导入基于文件 SHA-256 指纹跳过未变更文件，避免重复处理 |
| **SSE 流式输出** | astream_events v2 实现逐 token 流式推送，前端实时渲染 |
| **多后端 LLM** | OpenAI 兼容协议统一调用，支持 Ollama/DashScope/DeepSeek 无缝切换 |
| **安全防护** | SQL 安全校验 + 计算器 AST 白名单 + 文件名安全化 + 工具调用次数限制 |
| **连接管理** | 单例 ConnectionManager，会话级连接复用，60 分钟自动过期，健康检查+自动重连 |
| **链路追踪** | request_id 通过 ContextVar 贯穿日志和错误响应 |
| **统一异常** | AppError + 全局异常处理器，所有错误统一 JSON 格式 + request_id |
| **权限控制** | 基于管理员工号的部门级数据可见范围限制 |
