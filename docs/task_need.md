
@技术方案

# 桌管智能体技术实现方案文档 (MVP)

## 1. 总体架构设计

本方案采用 **“侧挂式 AI 异步中台”** 架构。AI 服务作为一个独立的容器运行，通过标准的 RESTful API 与原有的 C++ 管理端和数据库进行交互。

### 1.1 逻辑架构

- **管理端 (Qt/MFC)**：负责展示 AI 聊天窗口（WebView），通过 HTTPS 发送用户问题及当前登录用户的 Token（含 `LogNum`）。
- **AI 后端 (Docker + FastAPI)**：处理自然语言、生成 SQL、检索文档。
- **推理引擎 (Ollama/vLLM)**：运行本地大模型（Qwen2.5-VL 系列）。
- **数据层**：连接现有的 MySQL/PostgreSQL 生产库（只读）及本地向量数据库（ChromaDB）。

------

## 2. 数据库智能查询模块 (Text-to-SQL)

针对多数据库（MySQL/PG）及权限限制，采用 **“模板包装法”**。

### 2.1 元数据管理 (`schema_configs/`)

通过一个 YAML 文件管理数据库结构，降低 AI 幻觉。

YAML

```
# database_context.yaml
db_type: "mysql" # 可选 postgresql
tables:
  - name: "s_machine"
    description: "设备资产主表"
    columns:
      - name: "ID"
        comment: "唯一标识"
      - name: "Name_C"
        comment: "设备名称"
    permission_join: "JOIN s_group ON ..." # 预定义的权限关联路径

# 核心：20-30个高频 SQL 范例
sql_shots:
  - user_query: "查询 192.168.1.10 的资产变更"
    sql: "SELECT * FROM s_machine WHERE IP_C = '192.168.1.10'"
```

### 2.2 权限注入与 SQL 包装器

AI 不直接接触底层权限逻辑，后端程序在执行前进行拦截包装：

1. **AI 生成原始 SQL**：`SELECT Name_C FROM s_machine WHERE ID = 1`

2. **后端强制包装**：

   SQL

   ```
   -- 系统自动拼接权限后缀
   SELECT * FROM ( 
       $AI_GENERATED_SQL$ 
   ) AS temp_table
   WHERE temp_table.ID IN (
       SELECT a.id FROM s_group a 
       JOIN RoleGroupMap x ON x.GroupID = a.id 
       JOIN g_adminroleright y ON y.RoleID = x.RoleID 
       JOIN admininfo c ON c.id = y.AdminID 
       WHERE c.LogNum = :current_lognum
   )
   ```

3. **方言自适应**：通过 SQLAlchemy 或轻量级适配器，根据 `db_type` 自动处理 MySQL（反引号）与 PostgreSQL（双引号）的语法差异。

------

## 3. 知识文档与多模态 RAG

### 3.1 截图与多模态处理

- **技术路线**：使用 **Qwen2.5-VL** 视觉模型。
- **流程**：当用户上传“策略设置截图”时，模型直接理解图片中的配置项（如：USB 禁用勾选项是否打开），并结合内部 PDF 文档给出建议，无需经过传统的“OCR -> 文本”二次转换，保留了图片的布局语义。

### 3.2 向量索引策略

- **文档解析**：使用 `Docling` 引擎提取 PDF/Word 中的表格。
- **存储**：几十份文档建议直接使用 **ChromaDB** 内存索引并持久化到 Docker Volume，查询延迟控制在毫秒级。

------

## 4. 部署方案 (Docker 化)

为了实现你提到的“轻松搭建在另一台服务器”，我们将所有组件打包至 `docker-compose`。

### 4.1 容器编排

- **Container A (AI-API)**: FastAPI 业务逻辑、SQL 包装器、RAG 检索。
- **Container B (Ollama-GPU)**: 负责模型推理，通过 `nvidia-container-toolkit` 调用宿主机 GPU。
- **Container C (Vector-DB)**: ChromaDB 存储。

### 4.2 环境迁移

在另一台带有 NVIDIA GPU 的 Linux 服务器上，只需执行：

1. `git clone` 你的方案代码及 YAML 配置。
2. `docker-compose up -d`
3. 修改 `.env` 文件中的数据库连接地址。 **即可完成部署。**

------

## 5. 安全性约束 (MVP)

1. **只读账号**：AI 接入数据库必须使用 **Read-Only** 权限账号，从物理层面禁止写入。
2. **Token 校验**：Qt 客户端每次请求需携带 `X-Access-Token`。AI 服务端通过内存 Cache 或 JWT 校验，确保没有登录的请求无法调用 AI。
3. **结果脱敏**：对于身份证、密码等敏感字段，在 `database_context.yaml` 中标记为 `sensitive`，后端输出前自动掩码。

------

## 6. 后续扩展方向 (非 MVP)

- **图表可视化**：AI 直接返回 ECharts 配置项，Qt WebView 渲染饼图/趋势图。
- **长记忆能力**：记录管理员过去的操作偏好。



@任务安排

### 一、 核心开发任务拆解 (WBS)

我们将整个系统拆解为 6 个核心任务，每个任务都可以独立作为一个 Prompt 喂给编码 AI。

#### 任务 01：后端基础骨架与元数据引擎

- **任务说明**：搭建 FastAPI 基础架构，编写对 `schema_metadata.yaml` 的解析引擎，并在内存中构建“字段-语义”映射树。这是所有后续逻辑的基础。
- **输入**：你编写的 `schema_metadata.yaml` 样例文件（包含表结构和枚举值映射）。
- **输出**：FastAPI 工程骨架、`config_loader.py`（配置加载模块）、统一错误处理与日志模块。
- **建议技术/工具**：Python 3.12, FastAPI, Pydantic (用于 YAML 数据校验), PyYAML。
- **依赖任务**：无。最先开发。

#### 任务 02：安全 Text-to-SQL 代理模块

- **任务说明**：实现从自然语言到安全 SQL 的转换流水线。要求读取任务 01 解析的配置，组装 Few-shot Prompt，调用大模型生成初步 SQL，然后经过“权限包装器”（Permission Wrapper）拼接你定义的鉴权子查询。
- **输入**：用户的自然语言提问（如“多少机器在线”）、当前用户的 `LogNum`。
- **输出**：经过权限包装且语法正确的完整 SQL 语句（或直接返回数据库查询的 JSON 结果数组）。
- **建议技术/工具**：LangGraph (构建生成与校验状态机), SQLAlchemy (处理多数据库方言差异), Ollama/Qwen API。
- **依赖任务**：依赖 任务 01。

#### 任务 03：多模态文档解析与向量入库流水线

- **任务说明**：编写离线/异步脚本，读取指定目录下的 PDF、Word、图片等操作手册，调用解析引擎将其转为 Markdown，切片后存入向量数据库。
- **输入**：本地 `/data/docs` 目录下的混合格式文档。
- **输出**：成功写入 Qdrant 的向量数据，以及一个可触发全量/增量同步的 API 接口。
- **建议技术/工具**：Docling (2025最新多模态文档解析库), Qdrant Python Client, Qwen2.5-VL (用于图片识别), BGE-M3 (文本嵌入模型)。
- **依赖任务**：无。可与任务 01/02 并行开发。

#### 任务 04：混合 RAG 问答与大模型调度引擎

- **任务说明**：实现前端对话的核心 API（如 `/api/v1/chat`）。接收用户提问（可带图片），使用路由逻辑判断是走 Text-to-SQL 还是 RAG。如果是 RAG，则进行向量+关键字混合检索，并将上下文和图片喂给大模型生成回答。
- **输入**：用户提问的文本及可能上传的 Base64 图片/文件、历史会话上下文、当前用户鉴权 Token。
- **输出**：流式 (Streaming) 的 Markdown 格式回答文本。
- **建议技术/工具**：FastAPI StreamingResponse, LlamaIndex/LangChain (用于 RAG 检索编排), BM25 算法库。
- **依赖任务**：依赖 任务 02（SQL 能力）和 任务 03（向量库数据）。

#### 任务 05：Web 端轻量级 AI 对话界面

- **任务说明**：开发一个纯前端的单页面应用（SPA），作为 AI 聊天窗口。包含消息流式打字机效果展示、支持 Markdown 渲染（特别是表格和代码块）、支持剪贴板图片上传、处理与后端的会话状态。
- **输入**：后端提供的 `/api/v1/chat` API 文档（输入输出格式）。
- **输出**：一套打包后的前端静态资源文件（HTML/JS/CSS）。
- **建议技术/工具**：Vue 3 + TailwindCSS（或 React + shadcn/ui），Marked.js（Markdown 渲染），Axios。
- **依赖任务**：无（只要定义好 Mock 数据格式即可提前开发）。

#### 任务 06：C++ Qt 客户端集成与 Token 注入

- **任务说明**：在现有的 C++ 老客户端中，添加一个悬浮按钮或菜单项触发 AI 助手。打开一个包含 QWebEngineView 的小窗，加载任务 05 的 Web 页面。核心是启动时生成一个包含当前登录 `LogNum` 的 JWT 或临时 Token，并通过 JS 注入或 HTTP Header 传给 Web 页面。
- **输入**：现有客户端登录成功后的 `AdminID` / `LogNum` 变量。
- **输出**：修改后的 C++ Qt 代码补丁。
- **建议技术/工具**：C++ 11/14, Qt 5/6, QWebEngineView, QWebChannel (用于 C++ 与 JS 通讯), JWT 生成库。
- **依赖任务**：依赖 任务 05（需要 Web 页面准备好加载）。

------

### 二、 代码组织与文件夹分配 (物理边界)

为了让 AI 不会产生上下文混乱，你需要建立严格的目录结构。**同一个目录下的任务应该由同一个 AI 会话（或同一个 Cursor/Cline 窗口）来完成**。

建议将工程拆分为以下三个独立的代码库（或根目录下的三个文件夹），并分别交给 AI：

Plaintext

```
/desk-agent-project
│
├── /agent_backend    <-- 【交给后端 AI 处理：包含任务 01, 02, 03, 04】
│   ├── /configs      # schema_metadata.yaml 放在这里
│   ├── /core         # 鉴权与中间件
│   ├── /sql_agent    # Text-to-SQL 逻辑
│   ├── /rag_engine   # Docling 与向量检索
│   └── main.py       # FastAPI 入口
│
├── /agent_frontend   <-- 【交给前端 AI 处理：包含任务 05】
│   ├── /src
│   │   ├── /components  # ChatBox, MessageBubble, ImageUploader
│   │   └── App.vue
│   └── package.json
│
└── /qt_client_patch  <-- 【交给 C++ AI 处理：包含任务 06】
    ├── ai_window.cpp
    └── ai_window.h
```

------

