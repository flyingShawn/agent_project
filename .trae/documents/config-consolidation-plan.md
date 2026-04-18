# 配置文件合并计划

> 目标：**只改 `.env` 一个文件，前后端 + Docker 配置全部生效**

---

## 1. 当前问题诊断

### 问题一：前端配置有3个来源，互相覆盖，搞不清谁生效

| 来源 | 文件 | 什么时候生效 | 问题 |
|------|------|-------------|------|
| 硬编码默认值 | `src/config.js` 的 `defaultConfig` | 始终兜底 | ❌ 中文写死在代码里，改配置无效 |
| Vite 环境变量 | `import.meta.env.VITE_*` | 本地 dev | ❌ `.env` 里没有 `VITE_` 前缀变量，实际从未生效 |
| 运行时注入 | `public/config.js` → `window.__APP_CONFIG__` | 本地 dev | ❌ 硬编码中文，和 `.env` 的 `QUICK_OPTIONS` 无关 |
| Docker 注入 | `entrypoint.frontend.sh` 生成 `config.js` | Docker 部署 | ✅ 唯一正确读取 `.env` 的路径 |

**结果**：本地开发时，`.env` 中的 `APP_NAME`、`QUICK_OPTIONS` 等前端配置**根本不生效**，前端永远用的是 `public/config.js` 和 `src/config.js` 里的硬编码值。

### 问题二：后端 RAG 配置重复读取

`settings.py`（Pydantic BaseSettings）和 `retrieval.py`（os.getenv）独立读取相同的环境变量，两套机制并存。

### 问题三：`.env.example` 有未使用变量

`AGENT_NAME`、`ENABLE_CLOUD_FALLBACK`、`CHAT_API_TOKEN` 定义了但代码未读取。

### 问题四：默认值不一致

`CHAT_MODEL` 在 `.env.example` 是 `qwen2.5:7b`，docker-compose 是 `qwen2.5:7b-instruct`。

---

## 2. 合并方案

### 核心原则

- **`.env` 是唯一配置源**：所有可配置参数都定义在 `.env` 中
- **前端通过 Vite 读取 `.env`**：本地 dev 时 Vite 直接读根目录 `.env`
- **Docker 通过 docker-compose 传递**：已有机制不变
- **删除硬编码**：`public/config.js` 和 `src/config.js` 中的中文默认值全部删除

### 配置文件变更

| 文件 | 操作 | 说明 |
|------|------|------|
| `.env` / `.env.example` | ✏️ 更新 | 新增 `VITE_` 前缀前端变量，删除未使用变量，修复不一致 |
| `agent_frontend/public/config.js` | 🗑️ 删除 | 硬编码配置，不再需要 |
| `agent_frontend/src/config.js` | ✏️ 重写 | 简化为：运行时 > Vite env，无硬编码中文 |
| `agent_frontend/vite.config.js` | ✏️ 更新 | 添加 `envDir: '../'` 读取根目录 `.env` |
| `agent_frontend/index.html` | ✏️ 更新 | 删除 `<script src="/config.js">` 引用 |
| `docker/entrypoint.frontend.sh` | ✏️ 更新 | 变量名统一为 `VITE_` 前缀 |
| `docker-compose.yml` | ✏️ 更新 | 前端环境变量名统一为 `VITE_` 前缀 |
| `agent_backend/rag_engine/retrieval.py` | ✏️ 重写 | 复用 `RagIngestSettings`，不再独立 os.getenv |

---

## 3. 详细设计

### 3.1 `.env` 统一变量定义

```env
# ========================================
#   智能体配置
# ========================================
AGENT_NAME=desk-agent

# ========================================
#   大模型配置
# ========================================
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
CHAT_MODEL=qwen2.5:7b
VISION_MODEL=qwen2.5-vl:7b

# ========================================
#   数据库配置（只读）
# ========================================
DB_TYPE=mysql
DB_HOST=localhost
DB_PORT=3306
DB_NAME=desk_management
DB_USER=root
DB_PASSWORD=your_password
DATABASE_URL=

# ========================================
#   RAG 文档问答配置
# ========================================
RAG_DOCS_DIR=./data/desk-agent/docs
RAG_QDRANT_URL=http://localhost:6333
RAG_QDRANT_PATH=./.qdrant_local
RAG_QDRANT_COLLECTION=desk_agent_docs
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_HYBRID_ALPHA=0.7
RAG_TOP_K=5
RAG_CANDIDATE_K=30
RAG_VECTOR_MIN_SCORE=0.5

# ========================================
#   RAG SQL 样本库配置
# ========================================
RAG_SQL_DIR=./data/desk-agent/sql
RAG_SQL_QDRANT_COLLECTION=desk_agent_sql
RAG_SQL_TOP_K=3
RAG_SQL_CANDIDATE_K=15
RAG_SQL_HYBRID_ALPHA=0.8

# ========================================
#   SQL 查询限制
# ========================================
SQL_MAX_ROWS=500

# ========================================
#   网络搜索配置
# ========================================
TAVILY_API_KEY=
WEB_SEARCH_MAX_RESULTS=5

# ========================================
#   聊天历史数据库
# ========================================
CHAT_DB_PATH=data/chat_history.db

# ========================================
#   前端配置（VITE_ 前缀供 Vite 读取）
# ========================================
VITE_APP_NAME=阳途智能助手
VITE_APP_SUBTITLE=阳途智能助手为您服务
VITE_APP_WELCOME_TEXT=有什么我能帮您的呢？
VITE_APP_INPUT_PLACEHOLDER=给智能助手发消息
VITE_QUICK_OPTIONS=查看客户端在线状态,今日远程操作记录,近期开关机日志,老旧资产设备查询,部门设备数量统计,USB使用记录查询
```

**变更说明**：
- 删除 `ENABLE_CLOUD_FALLBACK`（未使用）
- 删除 `CHAT_API_TOKEN`（未使用）
- 前端变量统一用 `VITE_` 前缀（Vite 要求，只有 `VITE_` 前缀的变量才会暴露给前端代码）
- `CHAT_MODEL` 统一为 `qwen2.5:7b`（docker-compose 也改一致）

### 3.2 前端配置读取改造

**删除 `public/config.js`**：不再需要硬编码配置文件。

**重写 `src/config.js`**：

```js
const runtimeConfig = window.__APP_CONFIG__ || {}

const parseQuickOptions = (val) => {
  if (Array.isArray(val)) return val
  if (typeof val === 'string' && val.trim()) return val.split(',').map(s => s.trim()).filter(Boolean)
  return null
}

const envConfig = {
  appName: import.meta.env.VITE_APP_NAME || null,
  subtitle: import.meta.env.VITE_APP_SUBTITLE || null,
  welcomeText: import.meta.env.VITE_APP_WELCOME_TEXT || null,
  inputPlaceholder: import.meta.env.VITE_APP_INPUT_PLACEHOLDER || null,
  quickOptions: parseQuickOptions(import.meta.env.VITE_QUICK_OPTIONS || ''),
}

const config = {
  appName: runtimeConfig.appName || envConfig.appName,
  subtitle: runtimeConfig.subtitle || envConfig.subtitle,
  welcomeText: runtimeConfig.welcomeText || envConfig.welcomeText,
  inputPlaceholder: runtimeConfig.inputPlaceholder || envConfig.inputPlaceholder,
  quickOptions: runtimeConfig.quickOptions || envConfig.quickOptions,
}

export default config
```

**关键变化**：
- 删除 `defaultConfig`（不再有硬编码中文）
- 配置优先级：`window.__APP_CONFIG__`（Docker运行时）> `import.meta.env.VITE_*`（Vite读.env）
- 如果 `.env` 中没配置，值为 `null`，前端组件自行处理

**更新 `vite.config.js`**：

```js
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  return {
    plugins: [vue()],
    envDir: '../',  // 读取项目根目录的 .env
    server: {
      host: '0.0.0.0',
      port: 3000,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          configure: (proxy) => {
            proxy.on('proxyRes', (proxyRes) => {
              if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
                proxyRes.headers['cache-control'] = 'no-cache, no-transform'
                proxyRes.headers['x-accel-buffering'] = 'no'
              }
            })
          },
        },
      },
    },
    build: {
      outDir: 'dist',
      assetsDir: 'assets',
    },
  }
})
```

**关键变化**：添加 `envDir: '../'`，让 Vite 从项目根目录读取 `.env`。

**更新 `index.html`**：删除 `<script src="/config.js"></script>`。

### 3.3 Docker 前端配置统一

**更新 `entrypoint.frontend.sh`**：变量名改为 `VITE_` 前缀，与 `.env` 一致。

```sh
#!/bin/sh

CONFIG_FILE="/usr/share/nginx/html/config.js"

QUICK_OPTIONS_JSON="["
IFS=','
i=0
for item in $VITE_QUICK_OPTIONS; do
  if [ $i -gt 0 ]; then
    QUICK_OPTIONS_JSON="${QUICK_OPTIONS_JSON},"
  fi
  QUICK_OPTIONS_JSON="${QUICK_OPTIONS_JSON}\"${item}\""
  i=$((i + 1))
done
QUICK_OPTIONS_JSON="${QUICK_OPTIONS_JSON}]"

cat > "$CONFIG_FILE" << EOF
window.__APP_CONFIG__ = {
  appName: "${VITE_APP_NAME:-阳途智能助手}",
  subtitle: "${VITE_APP_SUBTITLE:-阳途智能助手为您服务}",
  welcomeText: "${VITE_APP_WELCOME_TEXT:-有什么我能帮您的呢？}",
  inputPlaceholder: "${VITE_APP_INPUT_PLACEHOLDER:-给智能助手发消息}",
  quickOptions: ${QUICK_OPTIONS_JSON}
};
EOF

echo "Generated config.js:"
cat "$CONFIG_FILE"

exec nginx -g 'daemon off;'
```

**更新 `docker-compose.yml`** 前端环境变量：

```yaml
frontend:
  environment:
    - VITE_APP_NAME=${VITE_APP_NAME:-阳途智能助手}
    - VITE_APP_SUBTITLE=${VITE_APP_SUBTITLE:-阳途智能助手为您服务}
    - VITE_APP_WELCOME_TEXT=${VITE_APP_WELCOME_TEXT:-有什么我能帮您的呢？}
    - VITE_APP_INPUT_PLACEHOLDER=${VITE_APP_INPUT_PLACEHOLDER:-给智能助手发消息}
    - VITE_QUICK_OPTIONS=${VITE_QUICK_OPTIONS:-查看客户端在线状态,今日远程操作记录,近期开关机日志,老旧资产设备查询,部门设备数量统计,USB使用记录查询}
```

同时修复后端 `CHAT_MODEL` 默认值不一致：

```yaml
backend:
  environment:
    - CHAT_MODEL=${CHAT_MODEL:-qwen2.5:7b}      # 统一，去掉 -instruct
    - VISION_MODEL=${VISION_MODEL:-qwen2.5-vl:7b}  # 统一，去掉 -instruct
```

### 3.4 后端 RAG 配置去重

**重写 `retrieval.py` 中的 `get_rag_settings()` 和 `get_sql_rag_settings()`**：

不再独立 `os.getenv()`，改为复用 `RagIngestSettings`：

```python
from agent_backend.rag_engine.settings import RagIngestSettings

def get_rag_settings():
    settings = RagIngestSettings()
    top_k = int(os.getenv("RAG_TOP_K", "5"))
    vector_min_score = float(os.getenv("RAG_VECTOR_MIN_SCORE", "0.5"))
    return (
        settings.qdrant_url, settings.qdrant_path, settings.qdrant_api_key,
        settings.qdrant_collection, settings.embedding_model,
        top_k, vector_min_score,
    )

def get_sql_rag_settings():
    settings = RagIngestSettings()
    top_k = int(os.getenv("RAG_SQL_TOP_K", "3"))
    candidate_k = int(os.getenv("RAG_SQL_CANDIDATE_K", "15"))
    alpha = float(os.getenv("RAG_SQL_HYBRID_ALPHA", "0.8"))
    return (
        settings.qdrant_url, settings.qdrant_path, settings.qdrant_api_key,
        settings.qdrant_sql_collection, settings.embedding_model,
        top_k, candidate_k, alpha,
    )
```

Qdrant 连接参数（url/path/api_key）统一从 `RagIngestSettings` 读取，检索参数（top_k/alpha 等）因为 `RagIngestSettings` 未定义，暂时保留 `os.getenv()`。

---

## 4. 合并后的配置读取全景

```
.env（唯一配置源）
│
├── 后端 Python ──────────────────────────────────
│   ├── core/config.py       → DB_*, SQL_MAX_ROWS, .env加载
│   ├── llm/factory.py       → LLM_BASE_URL, LLM_API_KEY, CHAT_MODEL
│   ├── llm/clients.py       → OLLAMA_BASE_URL, LLM_*, CHAT_MODEL, VISION_MODEL
│   ├── rag_engine/settings.py → RAG_*（Pydantic BaseSettings，统一入口）
│   ├── rag_engine/retrieval.py → 复用 RagIngestSettings + RAG_TOP_K 等
│   ├── db/chat_history.py   → CHAT_DB_PATH
│   └── agent/tools/web_search_tool.py → TAVILY_API_KEY, WEB_SEARCH_MAX_RESULTS
│
├── 前端 Vite（本地 dev）──────────────────────────
│   ├── vite.config.js       → envDir: '../' 读取根 .env
│   └── src/config.js        → import.meta.env.VITE_* 读取
│
└── Docker ───────────────────────────────────────
    ├── docker-compose.yml   → 读取 .env 传递给容器
    ├── backend 容器          → 直接读环境变量（同本地后端）
    └── frontend 容器
        └── entrypoint.frontend.sh → 生成 config.js → window.__APP_CONFIG__
```

**用户操作**：修改任何配置 → 编辑 `.env` → 本地 dev 重启即可生效，Docker `docker-compose up -d` 即可生效。

---

## 5. 执行步骤

### 阶段 1：更新 `.env.example` 和 `.env`
1. 前端变量改为 `VITE_` 前缀
2. 删除未使用变量（`ENABLE_CLOUD_FALLBACK`、`CHAT_API_TOKEN`）
3. 修复默认值不一致

### 阶段 2：前端配置改造
1. 删除 `agent_frontend/public/config.js`
2. 重写 `agent_frontend/src/config.js`（删除 defaultConfig 硬编码）
3. 更新 `agent_frontend/vite.config.js`（添加 `envDir: '../'`）
4. 更新 `agent_frontend/index.html`（删除 config.js 引用）

### 阶段 3：Docker 配置统一
1. 更新 `docker/entrypoint.frontend.sh`（变量名改 VITE_ 前缀）
2. 更新 `docker-compose.yml`（前端环境变量改 VITE_ 前缀，修复 CHAT_MODEL 不一致）

### 阶段 4：后端 RAG 配置去重
1. 重写 `retrieval.py` 的 `get_rag_settings()` 和 `get_sql_rag_settings()`，复用 `RagIngestSettings`

### 阶段 5：验证
1. 本地后端启动测试
2. 本地前端启动测试（确认 `.env` 中的 `VITE_*` 变量生效）
3. Docker 构建测试
