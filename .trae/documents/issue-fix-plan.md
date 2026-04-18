# Desk Agent 问题修复计划

## 一、问题逐项验证与裁定

### 问题1：SQLite 路径配置加载时序

**他人说法**：`CHAT_DB_PATH` 在 `chat_history.py` 模块导入时就被读取（line 47），但 `.env` 在 `main.py` 更后面才加载（line 53-55），导致 `.env` 里的聊天库路径配置可能不生效。

**实际验证**：

导入链追踪结果：
```
main.py:45  → from agent_backend.api.routes import router
  → routes.py:31 → from agent_backend.api.v1.chat import router
    → chat.py:49 → from agent_backend.agent.graph import get_agent_graph
      → graph.py:41 → from agent_backend.agent.nodes import ...
        → nodes.py:45 → from agent_backend.llm.factory import get_llm
          → factory.py:44 → load_env_file()  ← .env 在此被加载！
    → chat.py:51 → from agent_backend.db.chat_history import init_db
      → chat_history.py:47 → SQLITE_DB_PATH = os.environ.get("CHAT_DB_PATH", ...)
```

**结论：当前实际运行中，`.env` 在 `chat_history.py` 被导入之前就已经通过 `factory.py` 的 `load_env_file()` 加载了。所以 `CHAT_DB_PATH` 配置是可以生效的。**

但这是一个**脆弱的隐式依赖**：
- 完全依赖 `routes.py` 中 `chat_router` 排在 `conversations_router` 之前
- 完全依赖 `chat.py` 中 `graph.py` 的导入排在 `chat_history.py` 之前
- 如果有人调整导入顺序，或单独导入 `chat_history.py`（如测试场景），`.env` 可能尚未加载
- `main.py` 第 53-55 行的 `load_dotenv` 实际是冗余的兜底（但风格不统一，直接用 `load_dotenv` 而非 `load_env_file`）

**裁定：需要修复。** 虽然当前碰巧能工作，但依赖隐式导入顺序是危险的，应改为显式保证。

**修复方案**：在 `chat_history.py` 模块级代码读取 `CHAT_DB_PATH` 之前，显式调用 `load_env_file()`，确保无论导入顺序如何都能正确读取环境变量。

---

### 问题2：CORS 配置不合理

**他人说法**：`allow_origins=["*"]` 配合 `allow_credentials=True`，既不安全也容易在浏览器侧出现和凭证相关的跨域行为不一致。

**实际验证**：

根据 CORS 规范（Fetch Standard）：
- `Access-Control-Allow-Origin: *` 与 `Access-Control-Allow-Credentials: true` **不能同时使用**
- 浏览器在收到带凭证的请求时，如果响应头是 `Access-Control-Allow-Origin: *`，会**拒绝**该响应
- FastAPI 的 CORSMiddleware 对此有特殊处理：当 `allow_credentials=True` 且 `allow_origins=["*"]` 时，它不会返回 `Access-Control-Allow-Origin: *`，而是**反射请求的 Origin 头**（即把请求来源原样返回）

所以 FastAPI 的行为是：**虽然配置写了 `["*"]`，但实际响应头并不是 `*`，而是动态反射 Origin**。这意味着：
- 功能上不会出错（浏览器不会拒绝）
- 但安全性更差——等于任何 Origin 都能带凭证访问，比显式写 `["*"]` 还隐蔽
- `allow_credentials=True` 当前项目实际不需要（前端没有用 cookies 做认证）

**裁定：需要修复。** 应该去掉 `allow_credentials=True`，并通过环境变量配置允许的 Origin 列表。

---

### 问题3：仓库历史残留

**他人说法**：工作区里混有本地 `frontend/`、根目录孤立 `package-lock.json`、缓存/构建产物和大量运行数据。

**实际验证**：

根目录确实存在以下残留文件：
- `log.txt` — 空文件，无用
- `tmp.txt` — 旧方案审查报告，属于临时文件
- `package-lock.json` — 根目录的空壳（name=agent_project, packages={}），真正的在前端目录
- `FOLDER_CONVENTIONS.md` — 与 `.trae/rules/folder-conventions.md` 重复
- `PROJECT.md` — 系统架构分析文档，与 `.trae/documents/` 下的计划文档重复
- `.qdrant_local/` — Qdrant 本地数据（运行时产物）
- `.rag_state/` — RAG 状态文件（运行时产物）
- `data/chat_history.db-shm`、`data/chat_history.db-wal` — SQLite WAL 文件（运行时产物）
- `agent_frontend/.vite/` — Vite 缓存

**裁定：需要清理。** 但需区分：
- 应删除的：`log.txt`、`tmp.txt`、根目录 `package-lock.json`
- 应加入 `.gitignore` 的：`.qdrant_local/`、`.rag_state/`、`agent_frontend/.vite/`、`data/chat_history.db*`
- 可保留但应考虑归档的：`FOLDER_CONVENTIONS.md`、`PROJECT.md`（与 `.trae/` 下重复）

---

### 问题4：requirements.txt 缺少依赖

**他人说法（我的原始报告）**：`openpyxl` 和 `numpy` 未列入 requirements.txt。

**用户疑问**：没有为什么我还能正常使用？

**实际验证**：

- **numpy**：`fastembed>=0.3` 依赖 `onnxruntime`，而 `onnxruntime` 依赖 `numpy`。所以 `pip install fastembed` 会自动安装 `numpy`。**能正常使用是因为传递依赖。** 但按照 Python 依赖管理最佳实践，代码中直接 `import numpy` 的包应该显式声明，因为传递依赖的版本不受你控制。

- **openpyxl**：**不是任何已列出包的传递依赖。** 代码中用 try/except 做了优雅降级（`export_tool.py:62-66`），未安装时 `_HAS_OPENPYXL = False`，自动降级为 CSV 格式。所以**能正常使用是因为代码做了降级处理，Excel 导出功能实际不可用，只是不会报错。**

- **requests**：`web_search_tool.py:97` 中 `import requests` 作为 tavily-python 未安装时的回退方案，同样不在 requirements.txt 中。但这也是可选依赖。

- **tavily-python**：`web_search_tool.py:65` 中 `from tavily import TavilyClient`，不在 requirements.txt 中。同样是可选依赖，未安装时用 requests 回退。

- **psycopg2**：`config.py` 中 PostgreSQL 连接串使用 `postgresql+psycopg2://`，但 psycopg2 不在 requirements.txt 中。不过代码中只是拼接 URL，实际连接时才需要，且默认 DB_TYPE 是 mysql。

**裁定：需要补充，但分优先级。**
- `openpyxl` — 应添加为核心依赖（Excel 导出是重要功能）
- `numpy` — 应添加（直接 import 了，虽然传递依赖能覆盖）
- `requests` — 可选，已有降级
- `tavily-python` — 可选，已有降级
- `psycopg2` — 可选，仅 PostgreSQL 场景需要

---

### 我原始报告中的其他问题复核

#### P1：LLM客户端双轨并存 — 确认存在，但暂不处理

`clients.py` 的 `OpenAICompatibleClient` 仍被 `sql_agent/service.py` 使用。但 `service.py` 本身也是旧架构遗留，`sql_tool.py` 已经用 `factory.py` 的 `get_sql_llm()` 了。这个问题存在但影响有限，暂不作为本次修复重点。

#### P2：SQL生成流程重复 — 确认存在，但暂不处理

三处重复（`sql_tool.py`、`service.py`、`scheduler_tool.py`），属于代码质量问题，不影响功能正确性，暂不作为本次修复重点。

#### P4：每次RAG检索重新创建EmbeddingModel — 确认存在，应修复

`rag_tool.py` 每次调用 `rag_search` 都创建新的 `EmbeddingModel()` 和 `QdrantVectorStore()`。FastEmbed 模型加载有显著开销（首次需下载），应全局缓存。

#### P5：tool_result_node 冗长 — 确认存在，但暂不处理

属于代码重构范畴，不影响功能。

#### P7：_sse_event 重复定义 — 确认存在，应修复

`stream.py` 和 `chat.py` 各自定义了完全相同的 `_sse_event()` 函数，应提取到公共模块。

#### P15：_clean_sql_markdown 重复定义 — 确认存在，应修复

三处重复定义，应提取到公共模块。

#### P18：docker-compose Qdrant 健康检查无效 — 确认存在，应修复

`test: ["CMD-SHELL", "exit 0"]` 永远返回成功。

---

## 二、最终修复清单

| 编号 | 问题 | 严重度 | 修复类型 |
|------|------|--------|----------|
| F1 | SQLite 路径加载时序依赖隐式导入顺序 | 🔴 高 | 代码修改 |
| F2 | CORS allow_credentials=True + allow_origins=["*"] 不合理 | 🔴 高 | 代码修改 |
| F3 | 根目录残留文件清理 + .gitignore 补充 | 🟡 中 | 文件清理 |
| F4 | requirements.txt 补充 openpyxl/numpy | 🟡 中 | 配置修改 |
| F5 | _sse_event 重复定义，提取到公共模块 | 🟢 低 | 代码重构 |
| F6 | _clean_sql_markdown 重复定义，提取到公共模块 | 🟢 低 | 代码重构 |
| F7 | EmbeddingModel/QdrantVectorStore 每次重建，应缓存 | 🟡 中 | 性能优化 |
| F8 | docker-compose Qdrant 健康检查无效 | 🟢 低 | 配置修改 |
| F9 | retrieval.py 的 load_dotenv 风格不统一 | 🟢 低 | 代码修改 |

---

## 三、具体修复步骤

### F1：SQLite 路径加载时序

**文件**：`agent_backend/db/chat_history.py`

**修改**：在模块级代码读取 `CHAT_DB_PATH` 之前，显式调用 `load_env_file()`

```python
# 修改前
import os
import logging
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, ...

SQLITE_DB_PATH = os.environ.get("CHAT_DB_PATH", "data/chat_history.db")

# 修改后
import os
import logging
from pathlib import Path
from agent_backend.core.config import load_env_file
from sqlalchemy.ext.asyncio import create_async_engine, ...

load_env_file()
SQLITE_DB_PATH = os.environ.get("CHAT_DB_PATH", "data/chat_history.db")
```

同时移除 `main.py` 中冗余的 `load_dotenv` 调用（第 41 行 import 和第 53-55 行调用），改为使用 `load_env_file()` 保持风格统一。

### F2：CORS 配置修复

**文件**：`agent_backend/main.py`

**修改**：
1. 去掉 `allow_credentials=True`
2. 通过环境变量 `CORS_ORIGINS` 配置允许的 Origin 列表（逗号分隔），默认开发环境为 `http://localhost:3000`

```python
# 修改后
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

3. 在 `.env.example` 和 `docker-compose.yml` 中添加 `CORS_ORIGINS` 配置项

### F3：根目录残留清理 + .gitignore 补充

**删除文件**：
- `log.txt`
- `tmp.txt`
- 根目录 `package-lock.json`

**更新 .gitignore**，添加：
```
.qdrant_local/
.rag_state/
agent_frontend/.vite/
data/chat_history.db-shm
data/chat_history.db-wal
```

### F4：requirements.txt 补充依赖

**文件**：`requirements.txt`

添加：
```
numpy>=1.24
openpyxl>=3.1
```

### F5：_sse_event 提取到公共模块

**新建**：`agent_backend/core/sse.py`

将 `_sse_event` 函数从 `stream.py` 和 `chat.py` 提取到此模块，两处改为 import。

### F6：_clean_sql_markdown 提取到公共模块

**新建**：`agent_backend/sql_agent/utils.py`

将 `_clean_sql_markdown` 函数从 `sql_tool.py`、`service.py`、`scheduler_tool.py` 提取到此模块，三处改为 import。

### F7：EmbeddingModel/QdrantVectorStore 缓存

**文件**：`agent_backend/rag_engine/retrieval.py`

使用模块级单例缓存 EmbeddingModel 和 QdrantVectorStore 实例，避免每次调用 rag_search/search_sql_samples 时重复创建。

```python
_embedding_model_cache: dict[str, EmbeddingModel] = {}
_store_cache: dict[str, QdrantVectorStore] = {}

def _get_or_create_embedding(model_name: str) -> EmbeddingModel:
    if model_name not in _embedding_model_cache:
        _embedding_model_cache[model_name] = EmbeddingModel(model_name=model_name)
    return _embedding_model_cache[model_name]

def _get_or_create_store(url, path, api_key, collection, dim) -> QdrantVectorStore:
    key = f"{collection}:{path or url}"
    if key not in _store_cache:
        store = QdrantVectorStore(url=url, path=path, api_key=api_key, collection=collection, dim=dim)
        store.ensure_collection()
        _store_cache[key] = store
    return _store_cache[key]
```

同步修改 `rag_tool.py`，使用缓存函数而非直接创建实例。

### F8：docker-compose Qdrant 健康检查

**文件**：`docker-compose.yml`

```yaml
# 修改前
healthcheck:
  test: ["CMD-SHELL", "exit 0"]

# 修改后
healthcheck:
  test: ["CMD-SHELL", "curl -sf http://localhost:6333/healthz || exit 1"]
```

注意：qdrant 镜像可能没有 curl，需确认。如果没有 curl，可使用 wget 或 Python 方式：
```yaml
test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:6333/healthz')\" || exit 1"]
```

或者更简单的方案——qdrant 镜像自带 curl：
```yaml
test: ["CMD", "curl", "-sf", "http://localhost:6333/healthz"]
```

### F9：retrieval.py 的 load_dotenv 风格统一

**文件**：`agent_backend/rag_engine/retrieval.py`

移除第 44 行 `from dotenv import load_dotenv` 和第 49-51 行的 `load_dotenv` 调用，改为：
```python
from agent_backend.core.config import load_env_file
load_env_file()
```

---

## 四、执行顺序

1. F1 — SQLite 路径加载时序修复（最关键，防止未来导入顺序变更导致配置失效）
2. F2 — CORS 配置修复（安全相关）
3. F5 — _sse_event 提取（为后续修改减少重复代码）
4. F6 — _clean_sql_markdown 提取（同上）
5. F7 — EmbeddingModel/QdrantVectorStore 缓存（性能优化）
6. F4 — requirements.txt 补充
7. F8 — docker-compose 健康检查
8. F9 — retrieval.py 风格统一
9. F3 — 根目录残留清理（放最后，避免影响其他修改）
