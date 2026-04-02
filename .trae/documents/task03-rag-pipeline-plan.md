## 总结

将 `task3/` 目录中他人已实现的“多模态文档解析与向量入库流水线”代码审阅后，整体思路符合任务03要求：支持离线 CLI、支持 API 触发全量/增量同步、支持 Docling 转 Markdown、切片、BGE-M3 向量化并写入 Qdrant（含本地/远程两种形态）。接下来需要做的主要是把代码按当前工程的既定结构合并到 `agent_backend/rag_engine/` 和 `agent_backend/api/v1/`，并按你的要求补齐“图片识别必须接入 Qwen2.5-VL”的兜底路径，同时清理/避免迁入 `task3/` 目录里的缓存与本地库数据目录。

本计划只描述将要做的文件移动与代码调整；你确认后我才会开始实际编辑或移动文件。

---

## 现状分析（基于仓库实际内容）

### 现有工程（任务01/02）
- 真实后端工程根：`agent_backend/`
- 现有 API 入口：`agent_backend/main.py` + `agent_backend/api/routes.py`（统一挂载 `/api/v1/*`）
- 统一错误处理：`agent_backend/core/errors.py`（AppError + handler）
- 当前 `agent_backend/rag_engine/` 仅是空包（占位），尚未实现任务03逻辑

### task3 目录（他人交付）
- 交付代码位于：`task3/agent_backend/rag_engine/`，包含：
  - `docling_parser.py`：Docling -> Markdown
  - `chunking.py`：Markdown 切片
  - `embedding.py`：FastEmbed + BGE-M3
  - `qdrant_store.py`：Qdrant upsert/delete
  - `ingest.py`：全量/增量目录入库（文件指纹 state）
  - `state.py`：指纹 state 存取
  - `cli.py`：离线入口
  - `api.py`：`/api/v1/rag/sync` 后台任务 + job 状态查询（内存 job store）
- 同时 `task3/agent_backend/` 目录下存在不应迁入主工程的“运行产物/缓存”：
  - `.fastembed_cache/`（模型缓存）
  - `.qdrant_local*`（本地向量库数据）
  - `.smoke_docs/`（演示文档）
  - `task3/.state/`（指纹状态示例）

### 差距/需要调整点
- 你要求“必须接入 Qwen2.5-VL 做图片识别/OCR 兜底”：当前 `docling_parser.py` 仅用 Docling 解析图片，没有 Qwen2.5-VL 兜底。
- task3 的 `api.py` 自带 `prefix="/api/v1/rag"`，与主工程的 `/api/v1` 前缀挂载方式不兼容，需要改成主工程风格（在 `agent_backend/api/v1/` 下提供路由）。
- task3 的 API 使用 `HTTPException` + 内存 job store；主工程推荐统一用 `AppError` 返回结构，并尽量避免进程重启导致 job 丢失（可接受，但要明确行为）。

---

## 目标与成功标准

### 目标
- 在主工程 `agent_backend/` 中提供任务03能力：
  - 读取本地 `/data/docs`（可通过环境变量覆盖）下的 PDF/Word/图片等文档
  - 解析为 Markdown（Docling）
  - 对图片类文档增加 Qwen2.5-VL 兜底识别（生成可入库的 Markdown）
  - 切片并向量化（BGE-M3）
  - 写入 Qdrant（支持远程 URL + 本地 path 两种形态）
  - 提供 API：触发 full/incremental 同步，并可查询 job 状态

### 成功标准（可验收）
- `POST /api/v1/rag/sync` 可触发 `mode=full|incremental` 同步，返回 202 + job_id
- `GET /api/v1/rag/sync/{job_id}` 返回 running/succeeded/failed + 统计字段
- 离线命令 `python -m agent_backend.rag_engine.cli --mode full` 可运行（不要求必须连真实 Qdrant，允许本地 path 模式）
- 图片类文件在 Docling 失败/不可用时，能走 Qwen2.5-VL 兜底生成 markdown（至少输出标题+识别文本/描述）

---

## 拟议改动（文件与目录级别）

### 1) 代码迁移到正确目录（只迁移“源码”，不迁移运行产物）
将以下文件从 `task3/agent_backend/rag_engine/` 迁移/合并到主工程 `agent_backend/rag_engine/`：
- `chunking.py`
- `docling_parser.py`（后续改造：增加 Qwen2.5-VL 兜底）
- `embedding.py`
- `ingest.py`
- `qdrant_store.py`
- `settings.py`
- `state.py`
- `cli.py`

明确不迁移：
- `task3/agent_backend/.fastembed_cache/`
- `task3/agent_backend/.qdrant_local*`
- `task3/agent_backend/.smoke_docs/`
- `task3/.state/`
- `task3/data/docs/`（除非你希望作为示例保留在主工程）

### 2) API 以主工程风格接入
在主工程新增（或迁移重写）：
- `agent_backend/api/v1/rag.py`
  - 路由挂在 `/rag/sync` 与 `/rag/sync/{job_id}`
  - 使用 `BackgroundTasks` 运行入库任务
  - 返回结构尽量与现有 `AppError` 兼容（失败时抛 `AppError` 或返回统一错误结构）
- 修改 `agent_backend/api/routes.py`：include 新 rag router（prefix 仍为 `/api/v1`）

备注：保留你选定的固定路径：`/api/v1/rag/sync`（主工程层面为 `/api/v1` + rag 路由 `/rag/sync`）。

### 3) 增加 Qwen2.5-VL 图片识别兜底
新增/调整：
- `agent_backend/rag_engine/vision.py`（新增）
  - 定义 VisionClient 抽象
  - 提供 Ollama 兼容的 vision 调用实现（优先，便于本地部署）
  - 通过环境变量配置模型与服务地址（例如 `RAG_VISION_BASE_URL`, `RAG_VISION_MODEL`）
- 改造 `agent_backend/rag_engine/docling_parser.py`
  - 对图片后缀（png/jpg/jpeg/webp）：
    - 优先 Docling（若可用且输出非空）
    - 失败/空输出 -> 调用 VisionClient，将识别结果组织为 Markdown（例如：图片描述 + 识别文本块）

### 4) 依赖合并到主工程 requirements
将 task3 需要的依赖合并到主工程根 `requirements.txt`（不删除你已有依赖）：
- `pydantic-settings`
- `python-multipart`（若后续要支持上传，也可先不加；若保留则用于扩展）
- `qdrant-client`
- `fastembed`
- `docling`

### 5) 测试与演示
- 新增 `tests/test_rag_sync.py`
  - 使用 FastAPI TestClient 调用 `/api/v1/rag/sync` 与 job 查询
  - 对 ingest 过程做最小化 mock（避免真实下载模型/连接 Qdrant）
- 更新 `scripts/smoke_demo.py`（可选）：增加对 rag 接口的调用示例（不执行真实入库，只验证接口返回）

---

## 关键设计决策（已按你的选择锁定）
- 图片识别：必须接入 Qwen2.5-VL（作为图片解析兜底）
- Qdrant：同时支持远程 URL 与本地 path 两种模式
- API 路径：固定为 `/api/v1/rag/sync`

---

## 风险与约束
- Docling/fastembed 依赖较重，首次运行可能触发模型下载；测试需要 mock 以保证 CI/本地可复现。
- job 状态目前计划先使用“进程内内存字典”保存（与 task3 一致）；进程重启会丢失历史 job。若你需要“持久化 job 状态”，需要额外存储（例如写入本地 JSON/SQLite），这会增加实现范围。

---

## 验证步骤（实现后我会执行）
- `python -m unittest -v`：确保现有任务01/02/03测试全通过
- `python -m agent_backend.rag_engine.cli --mode incremental`：在设置 `RAG_DOCS_DIR` 指向包含少量文档的目录后，验证能扫描/切片/写入（可用 `RAG_QDRANT_PATH` 走本地模式）
- 启动 API 后：
  - `POST /api/v1/rag/sync {"mode":"incremental"}` 返回 202 + job_id
  - `GET /api/v1/rag/sync/{job_id}` 状态从 running -> succeeded/failed
