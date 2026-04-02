## 总结（先回答“是否采用 LangChain”）

建议 **采用 LangChain，但做“最小化引入”**：把 LangChain 作为任务04“对话编排层/可插拔接口层”，而不是把整个后端重构成 LangChain 项目。

理由基于你在 [task.md](file:///d:/work_space/agent_project/task.md) 最开始的核心诉求（最重要）：
- 核心业务目标是“文档问答 + 数据库只读查询 + 多模态上传”，并且要 **本地优先、可审计、只读、安全**。
- task.md 在架构建议里明确写到“文档知识库可采用 LlamaIndex/Flowise/自研”，任务04也把 “LlamaIndex/LangChain（用于 RAG 检索编排）”列为建议技术；并且你现在明确表示“最初就打算 LangChain 为核心向外扩展”。
- 因此 LangChain 属于“相关技术”，引入不违背“不要引入不相关技术”的约束；但考虑现有工程已完成任务01/02/03，全面迁移成本高，所以采用“最小化引入”最符合当前阶段。

“最小化引入”的定义（落地原则）：
- 只引入 **langchain-core**（必要时再加 1 个最小补充包），用于：消息抽象、Runnable/Tool 统一接口、流式回调契约。
- 不引入/不依赖大型全家桶（避免牵扯太多连接器与版本波动），Qdrant/SQL/Ollama 仍走我们已有模块。
- 任务04的路由与 RAG/SQL handler 继续以我们现有实现为主，LangChain 用来“规范接口与编排形态”，方便后续扩展成更完整的 Agent。

---

## 现状分析（基于仓库实际状态）

### 已实现（任务01/02/03）
- FastAPI 骨架、统一错误/日志/RequestId：`agent_backend/main.py`、`agent_backend/core/*`
- 元数据引擎：`agent_backend/core/config_loader.py`（加载 `agent_backend/configs/schema_metadata.yaml`）
- 安全 Text-to-SQL：`agent_backend/sql_agent/*` + `POST /api/v1/sql/generate`
- RAG 入库：`agent_backend/rag_engine/*` + `POST /api/v1/rag/sync`
  - 文档解析 Docling + 图片 Qwen2.5-VL(Ollama)兜底
  - 向量库：Qdrant（远程 url 或本地 path）

### 任务04缺口
- 没有 `/api/v1/chat`
- 没有 SSE 流式输出
- RAG 只有“入库”，缺少“检索/query + 混合检索（向量+关键词）”
- 没有统一的大模型调度层（本地 Ollama + 可选云端兜底），也没有统一流式 LLM client
- Token 鉴权：task.md 写到要 Token 校验，但你前面确认“先不做鉴权校验”（可留接口与实现位置）

---

## 需求回扣（来自 task.md 的“最开始需求最重要”）

必须满足/不偏离：
- **只读**：数据库相关能力只能读，不允许任何写入（task.md 第 17、71、217 行等）
- **多模态输入**：支持上传文档/图片参与问答（task.md 第 15、35、53 行等）
- **本地优先 + 云端兜底**：模型接口抽象，默认本地 Ollama/Qwen，多云端接口可选（task.md 第 21、59-62 行）
- **可审计与安全**：日志追溯、敏感字段控制（task.md 第 71、219 行）
- **前端对话核心 API**：`/api/v1/chat`，流式 Markdown（task.md 第 262-266 行）

---

## 方案选择：为什么“最小化引入 LangChain”是最优折中

引入 LangChain 的收益（与你的长期目标一致）：
- 统一 Tool/Runnable 抽象：把 SQL、RAG、图片理解都变成可组合的“能力块”，后续扩展 Agent 更省力
- 统一流式回调语义：对 SSE 输出和 LLM streaming 更友好
- 更接近你“LangChain 为核心向外扩展”的架构方向

控制引入范围的原因（与你的 MVP 目标一致）：
- 当前工程已经跑通 01/02/03，不需要为了任务04推倒重来
- LangChain 生态包很多，过度引入会带来版本/依赖/部署复杂度上升，反而不利于你后续“开展测试”

结论：**引入 langchain-core 做“接口与编排规范”，底层能力复用现有代码**。

---

## 拟议实现（任务04）

### 1) 新增 Chat API（SSE）
新增文件：
- `agent_backend/api/v1/chat.py`
  - `POST /chat`：SSE（`text/event-stream`）流式输出 Markdown
  - 输入：`question`、`history`、`images_base64`、`lognum`、`mode(auto/sql/rag)`、`token(占位)` 等
  - 输出事件：
    - `event: delta` + `data: <markdown片段>`
    - `event: done` + `data: {"route":"sql|rag","meta":{...}}`
修改：
- `agent_backend/api/routes.py`：挂载 chat router

鉴权策略（按你已确认的“暂不鉴权”）：
- 读取 `Authorization`/`X-Access-Token` 但不做校验；保留可插拔验证函数位置，后续补 JWT/缓存校验不改接口。

### 2) 路由规则（SQL vs RAG）
新增文件（独立于框架，便于测试）：
- `agent_backend/chat/router.py`
  - 规则：**查询/统计/在线数/多少台/告警/某 IP/某 mtid** → SQL
  - **怎么设置/为什么/原因/怎么回事/流程/方案/解释** → RAG
  - 冲突处理：优先级与白名单词表明确化（写成可配置常量）

### 3) RAG 检索（混合：向量 + 关键词）
扩展：
- `agent_backend/rag_engine/qdrant_store.py`：增加 `search(query_vector, limit, filter?, with_payload=True)`（读取 payload.text/source_path/heading 等）
新增：
- `agent_backend/rag_engine/retrieval.py`
  - `hybrid_search(query_text, top_k=5, candidate_k=30, alpha=0.7)`：
    - 向量检索拿候选
    - 对候选做 BM25（实现轻量 BM25，不新增第三方库）
    - 融合分数重排，返回 context chunks（含引用信息）

### 4) 大模型调度与流式输出
新增：
- `agent_backend/llm/clients.py`
  - `OllamaChatClient`（支持 stream=true）
  - 预留 `CloudFallbackClient` 接口（不实现/或只写占位），以满足“本地优先 + 云端兜底”的架构方向
  - 输入支持：纯文本 + images_base64（兼容 qwen2.5-vl）
新增：
- `agent_backend/chat/handlers.py`
  - `handle_sql_chat(...)`：
    - 调用任务02生成 SQL（必要时执行：仅当 `DATABASE_URL` 存在且请求允许；否则返回 SQL + 解释性 markdown）
  - `handle_rag_chat(...)`：
    - 调用 `hybrid_search` 拿上下文（含引用）
    - 将 context + history + images 交给 LLM 生成回答（Markdown）

### 5) LangChain 最小化引入点（核心决策落实）
依赖策略：
- 增加 `langchain-core`（仅此为默认；如未来需要工具调用生态再加 `langchain`/`langchain-community`）
使用范围：
- 用 `langchain_core.messages` 表达 history（Human/AI/System）
- 用 `langchain_core.runnables` 把 `router -> handler -> llm streaming` 形成可测试的 Runnable 链
- Tool 的抽象：SQL/RAG 处理器以 Tool 形式暴露（但实现仍复用现有模块）

---

## 配置清单（为后续联调/测试一次性准备）

建议新增或更新 `.env.example`（位置按现有习惯：项目根或 `agent_backend/`）：
- **模型**
  - `OLLAMA_BASE_URL=http://localhost:11434`
  - `CHAT_MODEL=qwen2.5:7b-instruct`
  - `VISION_MODEL=qwen2.5-vl:7b-instruct`
  - `ENABLE_CLOUD_FALLBACK=0`（占位）
- **RAG**
  - `RAG_DOCS_DIR=/data/docs`
  - `RAG_QDRANT_URL=http://localhost:6333`
  - `RAG_QDRANT_PATH=./.qdrant_local`（本地模式二选一）
  - `RAG_QDRANT_COLLECTION=desk_agent_docs`
  - `RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5`（建议默认填 fastembed 支持的模型）
  - `RAG_HYBRID_ALPHA=0.7`
  - `RAG_TOP_K=5`
  - `RAG_CANDIDATE_K=30`
- **数据库（只读）**
  - `DATABASE_URL=`（只读账号；为空则 chat 的 SQL 分支返回 SQL 而不执行）
- **鉴权占位**
  - `CHAT_API_TOKEN=`（占位；当前不校验）

---

## 测试计划（小白也能跑）

新增单测：
- `tests/test_chat_router.py`：验证路由规则
- `tests/test_rag_retrieval.py`：验证 BM25 + 融合排序（纯单测，无外部依赖）
- `tests/test_chat_sse.py`：mock 掉 Qdrant 搜索与 LLM stream，验证 SSE 输出格式与 `delta/done` 事件序列

验收脚本（手工）：
- `curl -N` 调用 `/api/v1/chat` 验证 SSE 能持续输出
- 典型问法：
  - SQL：`多少机器在线` / `查询 192.168.1.10 的告警`
  - RAG：`水印怎么设置` / `远程连接不通怎么排查`

---

## 验证步骤（实现后我会执行）
- `python -m unittest -v` 全绿
- 启动服务后：
  - `curl -N -X POST http://localhost:8000/api/v1/chat ...` 能看到持续输出的 SSE 数据
  - RAG 分支能输出引用来源（source_path/heading）
  - SQL 分支在 `DATABASE_URL` 为空时返回“SQL + 解释”；配置后返回结果表格 markdown
