## 总结

实现任务04的 `/api/v1/chat` 核心对话接口：接收文本（可带 Base64 图片、历史上下文），通过路由规则判断走 **Text-to-SQL**（任务02）还是 **RAG 混合检索**（任务03），再调用大模型生成回答，并以 **SSE 流式**输出 Markdown。

你已确认：
- 暂不做 token 鉴权校验（先保留字段/接口形态，后续可补）。  
- 流式协议用 SSE（`text/event-stream`）。  
- 路由判断：查询/统计/在线数等走 SQL；方案解释/原因/怎么设置等走 RAG。  

---

## 现状分析（基于当前工程）

### 已具备能力
- 任务01：schema metadata 加载与索引（`agent_backend/core/config_loader.py`），统一错误与日志（`agent_backend/core/errors.py`、`agent_backend/core/logging.py`）。
- 任务02：安全 Text-to-SQL（`agent_backend/sql_agent/*`），`POST /api/v1/sql/generate`。
- 任务03：文档入库（`agent_backend/rag_engine/*`），`POST /api/v1/rag/sync` 触发入库；图片解析具备 Docling + Qwen2.5-VL(Ollama)兜底。

### 缺口（任务04需要补齐）
- 没有 `/api/v1/chat` 接口、没有 SSE 流式输出。
- RAG 仅有“入库”，缺少“检索/search”能力（`qdrant_store.py` 仅 upsert/delete）。
- 没有统一的大模型“流式生成客户端”（目前 Ollama 调用均为 `stream=false`）。
- 没有 chat 层面的路由与 prompt 组装。

---

## 目标与成功标准

### 目标
- 新增 `POST /api/v1/chat`：
  - 输入：用户问题文本、可选 Base64 图片数组、历史会话上下文、可选 lognum（供 SQL 权限用）、可选 mode（auto/sql/rag）。
  - 输出：SSE 流式 Markdown（逐段/逐 token 推送）。
  - auto 模式下按规则路由：统计/查询类 → SQL；解释/原因/设置/操作指导类 → RAG。

### 成功标准（验收）
- 调用 `/api/v1/chat` 能收到 SSE 数据流（至少包含若干 `delta` 事件 + 最终 `done`）。
- “统计/在线数/数量”类问法会走 SQL，并能把 SQL 结果组织成 Markdown 输出。
- “怎么设置/为什么/怎么回事/方案说明”类问法会走 RAG，并包含来自向量库的引用片段（payload 的 `source_path/heading`）。
- 单元测试可在无 Ollama、无 Qdrant 服务的情况下通过（对外部依赖全部 mock）。

---

## 设计决策（锁定方案）

### 1) 不引入 LlamaIndex/LangChain
当前工程未使用 LlamaIndex/LangChain；为了遵守“不要引入不相关技术”的约束，本任务采用“轻量自实现编排”：
- RAG 检索：Qdrant 向量检索 + 本地 BM25 轻量 rerank（在候选集上计算，不扫全库）
- 编排：普通函数/模块拆分（不额外引入新框架）

### 2) 混合检索方式（可扩展、先跑通）
- 第一步：向量检索 topN（例如 30）
- 第二步：对这批候选的 `payload.text` 做 BM25 打分
- 第三步：归一化后按 `score = alpha * vector_score + (1-alpha) * bm25_score` 重排（alpha 默认 0.7）

### 3) SSE 事件格式（简单稳定）
- `event: delta` / `data: <markdown片段>`
- `event: done` / `data: {"mode":"sql|rag","meta":{...}}`

---

## 拟议改动（具体文件与内容）

### A. 新增 Chat API
1) 新增 [agent_backend/api/v1/chat.py]
- `POST /chat` SSE 输出
- 请求模型包含：
  - `question: str`
  - `history: [{role, content}]`（可选）
  - `images_base64: [str]`（可选）
  - `mode: "auto"|"sql"|"rag"`（默认 auto）
  - `lognum: str|None`（SQL 权限需要时使用）
- 处理流程：
  - 先做参数校验（空问题、history 限长、图片数量/大小上限）
  - 路由判定（auto）
  - 调用对应处理器生成 prompt
  - 使用 Ollama 流式客户端输出 SSE

2) 修改 [agent_backend/api/routes.py]
- include chat router（prefix `/api/v1`）

### B. 路由与编排层
新增 `agent_backend/chat/`（新包）
- `router.py`：`decide_mode(question) -> "sql"|"rag"`，包含你要求的规则：
  - SQL 触发：统计/数量/多少/在线/离线/告警/查询某 IP/某 mtid 等
  - RAG 触发：怎么/如何/为什么/原因/怎么设置/怎么回事/方案/流程/配置/解释 等
  - 冲突时：RAG 关键词优先（例如“在线数怎么统计”仍走 SQL，但“在线异常怎么回事”走 RAG）
- `prompts.py`：组装 SQL 回答 prompt 与 RAG 回答 prompt（要求输出 Markdown）
- `handlers.py`：
  - `handle_sql_chat(...)`：调用 `generate_secure_sql` + 可选执行（若配置 DATABASE_URL 且请求允许执行）→ 把结果表转成 Markdown
  - `handle_rag_chat(...)`：调用 `hybrid_search(...)` 取得 topK 上下文块 → 组装 prompt

### C. RAG 检索能力补齐
1) 扩展 [agent_backend/rag_engine/qdrant_store.py]
- 增加 `search(vector, limit, with_payload=True)` 返回 `[(score, payload)]`

2) 新增 [agent_backend/rag_engine/retrieval.py]
- `hybrid_search(query, top_k, candidate_k, alpha) -> list[ContextChunk]`
- 内置轻量 BM25（不新增第三方库）

### D. 大模型流式客户端（Ollama）
新增 `agent_backend/core/ollama_stream.py`（或 `agent_backend/chat/ollama_stream.py`，以现有结构为准）
- `stream_generate(prompt, images_base64=None) -> Iterator[str]`
- 调用 `POST {OLLAMA_BASE_URL}/api/generate`，`stream=true`
- 逐行解析 JSON，取 `response` 字段作为 delta
- 支持图片：若 `images_base64` 非空，直接传给 Ollama（与任务03视觉调用形态保持一致）

### E. 配置项（为后续联调测试准备）
新增/更新 `.env.example`（放在项目根或 agent_backend/ 下，二选一，按当前仓库习惯决定）
建议包含：
- `OLLAMA_BASE_URL`（默认 `http://localhost:11434`）
- `CHAT_MODEL`（默认例如 `qwen2.5:7b-instruct`；若你本地已有更合适模型可改）
- `RAG_QDRANT_URL` / `RAG_QDRANT_PATH` / `RAG_QDRANT_COLLECTION`
- `RAG_EMBEDDING_MODEL`（注意 fastembed 支持列表）
- `DATABASE_URL`（若启用 SQL 执行）

---

## 测试计划（必须可复现）

新增 `tests/test_chat_api.py`
- mock：
  - Qdrant search 返回固定 payload
  - embedding 固定向量
  - Ollama 流式返回固定 token 序列
- 覆盖：
  - auto 路由：SQL 类问法走 SQL handler；RAG 类问法走 RAG handler
  - SSE 响应头/事件结构正确（至少包含 delta/done）

扩展 `tests/test_rag_retrieval.py`
- 对 BM25+融合排序做纯单测（无外部依赖）

---

## 假设与边界
- 暂不做 token 鉴权校验；但请求会保留 `token` 字段/Authorization 头读取位置，便于后续补齐。
- 混合检索先做“候选集 rerank”，不做全库关键词搜索（避免扫库性能问题）；后续如需真正的关键词索引，可再评估 Qdrant payload index 或外置全文检索。
- 默认不强制执行 SQL：除非客户端显式允许 + 配置了 `DATABASE_URL`。

---

## 验证步骤（实现后我会执行）
- `python -m unittest -v`：全测试通过
- 启动服务后手工验证 SSE：
  - `curl -N -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d "{\"question\":\"多少机器在线\",\"mode\":\"auto\",\"lognum\":\"admin\"}"`
  - `curl -N -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d "{\"question\":\"水印怎么设置\",\"mode\":\"auto\"}"`
