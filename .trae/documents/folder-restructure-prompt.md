# 项目文件夹重组 — AI 提示词

> 使用方法：将下方 `---` 之间的全部内容复制，粘贴给任意 AI（ChatGPT / Claude / DeepSeek / GLM 等），即可获得针对本项目的文件夹重组方案。

---

## 提示词正文

你是一位资深的全栈架构师，擅长 Python 后端（FastAPI）和 Vue 前端项目的工程化组织。请你帮我审视并重组我的项目文件夹结构。

### 一、项目概述

这是一个名为"阳途智能助手（Desk Agent）"的 AI 智能助手项目，为桌面管理系统提供自然语言查询数据库、知识文档问答、图表生成与数据导出功能。

**核心架构**：
- 前端：Vue 3 + Vite + Tailwind CSS，SSE 流式对话
- 后端：FastAPI + Uvicorn，异步 Python Web
- Agent：LangGraph StateGraph 编排，LLM 自主决策调用 8 种工具（SQL查询、RAG检索、元数据查询、时间、计算器、图表、导出、网络搜索）
- LLM：langchain-openai，OpenAI 兼容协议，支持 Ollama/DashScope/DeepSeek 切换
- 向量数据库：Qdrant，文档和 SQL 样本的向量存储与检索
- 文本嵌入：FastEmbed（BAAI/bge-small-zh-v1.5）
- 文档解析：Docling（支持 docx/xlsx/pdf/txt/md）
- 业务数据库：SQLAlchemy 2.0，支持 MySQL/PostgreSQL 只读查询
- 聊天历史：SQLite（aiosqlite）
- 部署：Docker Compose + Nginx，前后端 + Qdrant 三容器编排

### 二、功能模块说明

| 模块 | 职责 | 当前位置 |
|------|------|----------|
| **Agent 编排** | LangGraph StateGraph 构建、节点函数、条件路由、状态定义、系统 Prompt、SSE 流式适配 | `agent_backend/agent/` |
| **Agent 工具** | 8 个工具实现（SQL/RAG/元数据/时间/计算器/图表/导出/网络搜索） | `agent_backend/agent/tools/` |
| **SQL Agent** | 自然语言转 SQL：模板匹配、Prompt 构建、安全校验、SQL 执行、数据库连接管理 | `agent_backend/sql_agent/` |
| **RAG Engine** | 文档知识库：导入、分块、向量化、Qdrant 存储、混合检索、增量状态 | `agent_backend/rag_engine/` |
| **LLM 客户端** | 底层 HTTP 客户端（OpenAI 兼容 + Ollama 原生） | `agent_backend/llm/clients.py` |
| **Agent LLM 工厂** | LLM 实例创建（get_llm / get_sql_llm），流式/同步、temperature 配置 | `agent_backend/agent/llm.py` |
| **API 路由** | FastAPI 路由：chat、conversations、rag、sql_agent、metadata、export、health | `agent_backend/api/v1/` |
| **聊天历史 DB** | SQLite 存储 Conversation 和 Message（ORM 模型 + 异步引擎） | `agent_backend/db/` |
| **核心基础层** | 配置加载、环境变量、Schema 模型、异常处理、日志、请求 ID | `agent_backend/core/` |
| **业务配置** | schema_metadata.yaml（数据库表结构、同义词、安全规则、权限、查询模板） | `agent_backend/configs/` |
| **前端组件** | ChatBox、MessageBubble、ImageUploader、ChartBlock、Sidebar | `agent_frontend/src/components/` |
| **前端 API** | SSE 流式通信、会话管理 API | `agent_frontend/src/api/` |
| **前端组合函数** | useConversations | `agent_frontend/src/composables/` |
| **Docker 部署** | Dockerfile.backend、Dockerfile.frontend、nginx.conf、部署脚本 | `docker/` |
| **工具脚本** | 冒烟测试、API 测试、数据同步、诊断工具、停止服务 | `scripts/` |
| **帮助文档** | 操作指南、问题记录、配置说明、任务文档 | `help/` |

### 三、当前文件树

```
agent_project/
├── agent_backend/                    # 后端服务
│   ├── agent/                        # LangGraph Agent 编排层
│   │   ├── __init__.py               #   导出 get_agent_graph
│   │   ├── graph.py                  #   StateGraph 构建
│   │   ├── nodes.py                  #   节点函数 + 条件路由
│   │   ├── state.py                  #   AgentState 定义
│   │   ├── llm.py                    #   LLM 工厂（get_llm / get_sql_llm）
│   │   ├── prompts.py                #   系统 Prompt
│   │   ├── stream.py                 #   astream_events → SSE 流式适配
│   │   └── tools/                    #   8 个工具实现
│   │       ├── __init__.py
│   │       ├── sql_tool.py           #     自然语言→SQL
│   │       ├── rag_tool.py           #     知识库检索
│   │       ├── metadata_tool.py      #     表结构查询
│   │       ├── time_tool.py          #     当前时间
│   │       ├── calculator_tool.py    #     数学计算
│   │       ├── chart_tool.py         #     ECharts 图表
│   │       ├── export_tool.py        #     Excel/CSV 导出
│   │       └── web_search_tool.py    #     Tavily 网络搜索
│   ├── api/                          # API 路由层
│   │   ├── routes.py                 #   路由总入口
│   │   └── v1/                       #   各功能路由
│   │       ├── __init__.py
│   │       ├── chat.py               #     聊天 API（SSE 流式）
│   │       ├── conversations.py      #     会话管理
│   │       ├── export.py             #     文件下载
│   │       ├── health.py             #     健康检查
│   │       ├── metadata.py           #     元数据摘要
│   │       ├── rag.py                #     RAG 同步接口
│   │       └── sql_agent.py          #     SQL 代理接口
│   ├── configs/
│   │   └── schema_metadata.yaml      #   数据库 Schema 元数据配置
│   ├── core/                         # 核心基础层
│   │   ├── __init__.py
│   │   ├── config_helper.py          #   环境变量配置助手
│   │   ├── config_loader.py          #   Schema YAML 加载
│   │   ├── errors.py                 #   异常处理
│   │   ├── logging.py                #   日志配置
│   │   ├── request_id.py             #   请求 ID 中间件
│   │   └── schema_models.py          #   Schema Pydantic 模型
│   ├── db/                           # 聊天历史数据库
│   │   ├── __init__.py
│   │   ├── database.py               #   SQLite 异步引擎
│   │   └── models.py                 #   Conversation / Message ORM
│   ├── llm/                          # LLM 客户端
│   │   ├── __init__.py
│   │   └── clients.py                #   OpenAI 兼容 + Ollama 原生客户端
│   ├── rag_engine/                   # RAG 检索增强引擎
│   │   ├── __init__.py
│   │   ├── chunking.py               #   Markdown 分块
│   │   ├── embedding.py              #   FastEmbed 向量化
│   │   ├── ingest.py                 #   文档导入主流程
│   │   ├── qdrant_store.py           #   Qdrant 封装
│   │   ├── retrieval.py              #   混合检索
│   │   ├── settings.py               #   配置定义
│   │   └── state.py                  #   增量状态
│   ├── sql_agent/                    # SQL 代理模块
│   │   ├── __init__.py
│   │   ├── connection_manager.py     #   数据库连接管理（MySQL/PG）
│   │   ├── executor.py               #   SQL 执行器
│   │   ├── patterns.py               #   查询模板匹配
│   │   ├── prompt_builder.py         #   SQL Prompt 构建
│   │   ├── service.py                #   SQL 生成编排
│   │   ├── sql_safety.py             #   SQL 安全校验
│   │   └── types.py                  #   类型定义
│   └── main.py                       # 应用入口
├── agent_frontend/                   # 前端服务
│   ├── public/
│   │   └── config.js                 #   Docker 环境注入配置
│   ├── src/
│   │   ├── api/
│   │   │   ├── chat.js               #   SSE 流式通信
│   │   │   └── conversations.js      #   会话管理 API
│   │   ├── components/
│   │   │   ├── ChartBlock.vue        #   图表展示
│   │   │   ├── ChatBox.vue           #   主聊天组件
│   │   │   ├── ImageUploader.vue     #   图片上传
│   │   │   ├── MessageBubble.vue     #   消息气泡
│   │   │   └── Sidebar.vue           #   侧边栏
│   │   ├── composables/
│   │   │   └── useConversations.js   #   会话组合函数
│   │   ├── App.vue
│   │   ├── config.js
│   │   ├── main.js
│   │   └── style.css
│   ├── index.html
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   └── vite.config.js
├── data/                             # 数据目录
│   └── chat_history.db               #   聊天历史 SQLite 文件
├── docker/                           # Docker 构建文件
│   ├── .dockerignore
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   ├── README.md
│   ├── deploy.bat
│   ├── deploy.sh
│   ├── entrypoint.frontend.sh
│   └── nginx.conf
├── help/                             # 帮助文档（杂乱）
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
│   └── 测试运行指南.md
├── scripts/                          # 工具脚本（混杂）
│   ├── __init__.py
│   ├── smoke_demo.py                 #   冒烟测试
│   ├── stop_backend.bat              #   停止后端
│   ├── sync_docs.py                  #   文档同步
│   ├── sync_sql_samples.py           #   SQL 样本同步
│   ├── test_chat_api.py              #   API 测试
│   ├── 测试数据库连接.py              #   数据库连接测试
│   └── 诊断工具.py                    #   诊断工具
├── tests/                            # 测试目录（已有但不完善）
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
├── .env.example                      # 环境变量模板
├── .gitignore
├── PROJECT.md                        # 架构文档
├── README.md                         # 项目说明
├── docker-compose.yml                # 容器编排
├── docker_install_guide.md           # Docker 安装指南（散落在根目录）
├── requirements.txt                  # Python 依赖（在根目录）
├── test_llm.py                       # 测试文件（散落在根目录）
├── test_llm2.py                      # 测试文件（散落在根目录）
├── test_llm3.py                      # 测试文件（散落在根目录）
├── log.txt                           # 日志文件（不应入库）
└── tmp.txt                           # 临时文件（不应入库）
```

### 四、我的诉求

1. **审视当前结构**：指出当前文件夹划分中不合理、不优雅的地方，并说明原因
2. **给出重组方案**：提供一个更合理、更优雅的文件夹结构，包含：
   - 完整的目标文件树（用树形结构展示）
   - 每个目录的职责说明（一句话概括放什么、不放什么）
   - 需要移动/重命名/删除的文件清单
3. **制定放置规则**：编写一份「新文件应该放哪里」的规则文档，便于以后新增文件时有据可依，包含：
   - 按文件类型的归属规则（Python 业务代码、Vue 组件、API 路由、配置文件、测试文件、脚本、文档等）
   - 按功能域的归属规则（Agent 相关、SQL 相关、RAG 相关、LLM 相关、数据库相关等）
   - 一个快速判断的决策流程图（文字版树形结构）
   - 命名约定（文件命名、目录命名的规范）
   - 反模式示例（常见错误放置及纠正）

### 五、约束与偏好

- **不考虑向后兼容**：所有文件都可以自由移动和重命名，import 路径可以全部更新
- **后端是 Python 包结构**：通过 `agent_backend.xxx` 形式 import，重组后路径会变
- **Docker 挂载需要**：`configs/` 目录需要独立于代码目录，因为 Docker 部署时单独挂载
- **前端是标准 Vue 3 项目**：遵循 Vue 3 + Vite 的惯例
- **偏好简洁命名**：目录名尽量短且表意，避免冗余前缀（如 `agent_backend` 中的 `agent_` 前缀可考虑去掉）
- **偏好功能域分组**：同一功能域的代码尽量聚合，减少跨目录跳转
- **偏好扁平优于嵌套**：避免过深的目录层级（一般不超过 4 层）
- **预留扩展空间**：目录结构应考虑未来可能新增的模块（如定时任务 Agent、更多工具等）

### 六、输出格式要求

请按以下格式输出：

```
## 1. 当前结构问题诊断
（列出问题，按严重程度排序，说明原因）

## 2. 重组后的目标结构
（完整的树形文件结构 + 每个目录的职责注释）

## 3. 文件变更清单
（表格：原路径 → 新路径 → 变更类型[移动/重命名/删除]）

## 4. 新文件放置规则
### 4.1 按文件类型的归属规则
### 4.2 按功能域的归属规则
### 4.3 快速判断决策流程图
### 4.4 命名约定
### 4.5 反模式示例

## 5. 重组执行建议
（建议的执行顺序和注意事项）
```

---

## 提示词使用说明

### 适用场景
- 新项目初始化时，让 AI 帮你规划文件夹结构
- 老项目重构时，让 AI 审视并给出重组方案
- 团队协作时，作为文件夹规范的讨论基础

### 如何调整
- **增减功能模块**：在"功能模块说明"表格中增减行
- **修改约束**：在"约束与偏好"中调整（如需要兼容性、有特殊的部署要求等）
- **调整输出重点**：在"输出格式要求"中增减章节（如不需要"反模式示例"可删掉）

### 搭配使用
- 获得重组方案后，可以让 AI 继续生成具体的文件移动脚本（PowerShell / Bash）
- 可以让 AI 基于放置规则生成 `.trae/rules/` 下的项目规则文件，让 IDE 中的 AI 助手也遵守
