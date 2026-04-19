# 项目配置文件与提示词全景分析及改良计划（v2）

> 综合两方视角，经代码验证后重新整理

***

## 一、配置文件读取全景

### 1.1 真正生效的 4 类配置

| 配置文件                   | 路径                       | 格式     | 读取位置                                                                                                                                                   | 用途                                     |
| ---------------------- | ------------------------ | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------- |
| `.env`                 | 项目根目录                    | dotenv | [config.py:73](agent_backend/core/config.py#L73), [main.py:53](agent_backend/main.py#L53), [chat\_history.py:48](agent_backend/db/chat_history.py#L48) | 环境变量统一入口，LLM/DB/RAG/搜索/CORS 全从此取       |
| `schema_metadata.yaml` | `agent_backend/configs/` | YAML   | [config.py:214](agent_backend/core/config.py#L214)                                                                                                     | 数据库 Schema 元数据（表结构、同义词、安全规则、查询模板、展示字段） |
| `scheduled_tasks.yaml` | `agent_backend/configs/` | YAML   | [manager.py:603](agent_backend/scheduler/manager.py#L603)                                                                                              | 默认定时任务定义，支持 SQL 模板热更新                  |
| 前端运行时配置链               | `public/config.js`       | JS     | [index.html:11](agent_frontend/index.html#L11) → [src/config.js:16](agent_frontend/src/config.js#L16)                                                  | 前端应用名称/欢迎语/快捷选项                        |

> **注意**：`.rag_state/*.json`、`data/chat_history.db`、Qdrant 本地文件这些不是配置，是状态/数据。

### 1.2 环境变量分类汇总（真正被代码消费的）

#### 数据库相关（8个 ✅ 全部生效）

| 环境变量           | 默认值       | 读取位置          |
| -------------- | --------- | ------------- |
| `DATABASE_URL` | 无         | config.py:103 |
| `DB_TYPE`      | `"mysql"` | config.py:106 |
| `DB_HOST`      | 无         | config.py:107 |
| `DB_PORT`      | 无         | config.py:108 |
| `DB_NAME`      | 无         | config.py:109 |
| `DB_USER`      | 无         | config.py:110 |
| `DB_PASSWORD`  | 无         | config.py:111 |
| `SQL_MAX_ROWS` | `"500"`   | config.py:135 |

#### LLM 相关（5个 ✅ 全部生效）

| 环境变量              | 默认值                           | 读取位置                          |
| ----------------- | ----------------------------- | ----------------------------- |
| `LLM_BASE_URL`    | `"http://localhost:11434/v1"` | factory.py:69, clients.py:293 |
| `LLM_API_KEY`     | `"ollama"`                    | factory.py:70, clients.py:296 |
| `CHAT_MODEL`      | `"qwen2.5:7b"`                | factory.py:71, clients.py:89  |
| `VISION_MODEL`    | `"qwen2.5-vl:7b"`             | clients.py:90                 |
| `OLLAMA_BASE_URL` | `"http://localhost:11434"`    | clients.py:86                 |

#### RAG 相关（7个 ✅ 生效 + 4个 ❌ 死变量）

| 环境变量                        | 默认值                        | 读取位置                                  | 状态    |
| --------------------------- | -------------------------- | ------------------------------------- | ----- |
| `RAG_QDRANT_URL`            | `"http://localhost:6333"`  | retrieval.py:346, qdrant\_store.py:97 | ✅ 生效  |
| `RAG_QDRANT_PATH`           | `None`                     | retrieval.py:347, qdrant\_store.py:98 | ✅ 生效  |
| `RAG_QDRANT_API_KEY`        | `None`                     | retrieval.py:348, qdrant\_store.py:99 | ✅ 生效  |
| `RAG_QDRANT_COLLECTION`     | `"desk_agent_docs"`        | retrieval.py:349                      | ✅ 生效  |
| `RAG_SQL_QDRANT_COLLECTION` | `"desk_agent_sql"`         | retrieval.py:374                      | ✅ 生效  |
| `RAG_EMBEDDING_MODEL`       | `"BAAI/bge-small-zh-v1.5"` | retrieval.py:350, embedding.py:75     | ✅ 生效  |
| `RAG_TOP_K`                 | `"5"`                      | retrieval.py:351                      | ✅ 生效  |
| `RAG_VECTOR_MIN_SCORE`      | `"0.5"`                    | retrieval.py:352                      | ✅ 生效  |
| `RAG_SQL_TOP_K`             | `"3"`                      | retrieval.py:376                      | ✅ 生效  |
| `RAG_SQL_CANDIDATE_K`       | `"15"`                     | retrieval.py:377                      | ✅ 生效  |
| `RAG_SQL_HYBRID_ALPHA`      | `"0.8"`                    | retrieval.py:378                      | ✅ 生效  |
| `RAG_HYBRID_ALPHA`          | `"0.7"`                    | **无代码读取**                             | ❌ 死变量 |
| `RAG_CANDIDATE_K`           | `"30"`                     | **无代码读取**                             | ❌ 死变量 |

#### 其他（5个 ✅ 全部生效）

| 环境变量                     | 默认值                       | 读取位置                     |
| ------------------------ | ------------------------- | ------------------------ |
| `CHAT_DB_PATH`           | `"data/chat_history.db"`  | chat\_history.py:49      |
| `CORS_ORIGINS`           | `"http://localhost:3000"` | main.py:92               |
| `AGENT_NAME`             | `"desk-agent"`            | manager.py:185           |
| `TAVILY_API_KEY`         | `""`                      | web\_search\_tool.py:142 |
| `WEB_SEARCH_MAX_RESULTS` | `"5"`                     | web\_search\_tool.py:149 |

#### ❌ 死环境变量（.env 中声明但代码从未消费）

| 环境变量                    | 声明位置             | 问题                                                                 |
| ----------------------- | ---------------- | ------------------------------------------------------------------ |
| `ENABLE_CLOUD_FALLBACK` | .env.example:43  | 无任何代码读取                                                            |
| `CHAT_API_TOKEN`        | .env.example:119 | 文档声称"接口鉴权"，但代码未实现鉴权逻辑                                              |
| `RAG_HYBRID_ALPHA`      | .env.example:88  | 文档检索的 `get_doc_rag_settings()` 不返回此值，`hybrid_search()` 用硬编码默认值 0.7 |
| `RAG_CANDIDATE_K`       | .env.example:92  | 文档检索的 `get_doc_rag_settings()` 不返回此值，`hybrid_search()` 用硬编码默认值 30  |

### 1.3 配置读取方式不一致问题

当前项目存在 **3 种不同的配置读取方式**：

| 方式                               | 使用位置                                                                             | 特点                  |
| -------------------------------- | -------------------------------------------------------------------------------- | ------------------- |
| `core/config.py` 集中函数            | DB配置、Schema加载                                                                    | 有缓存、有日志、统一入口        |
| `pydantic_settings.BaseSettings` | `rag_engine/settings.py` 的 `RagIngestSettings`                                   | 类型安全、自动验证、`RAG_` 前缀 |
| `os.getenv()` 散落调用               | retrieval.py、factory.py、clients.py、web\_search\_tool.py、chat\_history.py、main.py | 无验证、无缓存、分散各处        |

**RAG 配置双轨制**尤其突出：`RagIngestSettings`（pydantic\_settings）和 `retrieval.py` 中 `os.getenv()` 读取相同环境变量，默认值分散在两处，容易不一致。

### 1.4 前端配置链断层

当前前端存在 **三套配置机制并存**，且本地开发时有断层：

```
Docker 环境变量 APP_*
    ↓ (entrypoint.frontend.sh 生成)
window.__APP_CONFIG__ (runtimeConfig)     ← 最高优先级，Docker 下生效
    ↓ fallback
import.meta.env.VITE_* (envConfig)        ← 中等优先级，但本地开发时永远为 undefined
    ↓ fallback
defaultConfig (硬编码)                     ← 最低优先级，本地开发实际兜底
```

**问题**：`envConfig` 层是死代码——根目录 `.env.example` 中变量名是 `APP_`生效。

***

## 二、提示词全景

### 2.1 真正生效的 4 处提示词

| 编号 | 名称                   | 文件                                                                                      | 行号      | 生效时机                 | 效果                                              |
| -- | -------------------- | --------------------------------------------------------------------------------------- | ------- | -------------------- | ----------------------------------------------- |
| 1  | `SYSTEM_PROMPT`      | [prompts.py](agent_backend/agent/prompts.py#L25)                                        | 25-101  | 每次 chat 请求初始化时注入     | 决定优先用哪个工具、何时取时间、何时建定时任务、回答不暴露 SQL 等             |
| 2  | `build_sql_prompt()` | [prompt\_builder.py](agent_backend/sql_agent/prompt_builder.py#L74)                     | 74-214  | 每次生成 SQL 时动态构建       | Schema + 同义词 + SQL 样本 + 指令规则，影响字段选择、别名风格、是否参考样本 |
| 3  | SQL 系统提示词            | sql\_tool.py:174, scheduler\_tool.py:163, scheduler\_manage\_tool.py:149, service.py:64 | 各处      | 每次调用 LLM 生成 SQL 时    | "只返回 SQL 语句，不要包含解释"，把输出格式压窄                     |
| 4  | `summary_prompt`     | [nodes.py](agent_backend/agent/nodes.py#L329)                                           | 329-332 | max\_tool\_calls 用尽时 | 强制 LLM 基于已有结果给最终答复                              |

### 2.2 写了但没生效/半生效的提示词

| 编号 | 名称                      | 文件                                                                       | 行号      | 状态         | 说明                                                                                                                                                                                      |
| -- | ----------------------- | ------------------------------------------------------------------------ | ------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 5  | `query_patterns`        | [schema\_metadata.yaml](agent_backend/configs/schema_metadata.yaml#L724) | 724-841 | ❌ **死代码**  | 模板匹配逻辑完整实现（[patterns.py:83](agent_backend/sql_agent/patterns.py#L83)），但 `use_template` 默认 `False` 且**无任何调用方传** **`True`**；主 SQL 生成路径（sql\_tool.py）完全不走 `generate_secure_sql`，有独立 LLM 流程 |
| 6  | `display_fields` prompt | [schema\_metadata.yaml](agent_backend/configs/schema_metadata.yaml#L842) | 842-919 | ❌ **死配置**  | 模型定义接住了（[schema\_models.py:128](agent_backend/core/schema_models.py#L128)），YAML 也配了 3 组，但 `build_sql_prompt()` 未注入，不参与 SQL 选择或回答格式控制                                                    |
| 7  | sql\_query 追加 Prompt    | [sql\_tool.py](agent_backend/agent/tools/sql_tool.py#L163)               | 163-170 | ⚠️ **半生效** | 仅 sql\_query 工具追加，与 `build_sql_prompt()` 中已有指令重叠（样本模仿、禁止重复字段），导致三条 SQL 生成链路（聊天/建任务/改任务）的约束不完全一致                                                                                         |
| 8  | `required_fields`       | [schema\_metadata.yaml](agent_backend/configs/schema_metadata.yaml#L920) | 920-926 | ❌ **死配置**  | 定义了必选字段列表，但无代码消费                                                                                                                                                                        |

### 2.3 提示词层级关系（修正版）

```
用户提问
  │
  ├─ SYSTEM_PROMPT (始终生效，定义全局行为)
  │    ├─ 工具 docstring (隐式，LLM 据此选工具)
  │    └─ 决策/回答规则
  │
  ├─ 工具调用阶段
  │    ├─ sql_query 路径:
  │    │    ├─ query_patterns 模板匹配 ← ❌ 死代码，从未触发
  │    │    └─ LLM 生成路径:
  │    │         ├─ SQL系统提示词 "只返回SQL"
  │    │         ├─ build_sql_prompt() (Schema+同义词+样本+规则)
  │    │         ├─ sql_query 追加 Prompt ← ⚠️ 仅此路径有，其他路径没有
  │    │         └─ 失败时 hint 文本
  │    │
  │    ├─ schedule_task 路径:
  │    │    ├─ SQL系统提示词 (重复定义)
  │    │    └─ build_sql_prompt() (无追加 Prompt)
  │    │
  │    ├─ manage_scheduled_task 路径:
  │    │    ├─ SQL系统提示词 (重复定义)
  │    │    └─ build_sql_prompt() (无追加 Prompt)
  │    │
  │    ├─ rag_search 路径:
  │    │    └─ 无结果回退文本
  │    │
  │    └─ 其他工具: 无额外提示词
  │
  └─ 达到工具调用上限时
       └─ summary_prompt (强制总结)
```

***

## 三、问题诊断（综合两方视角）

### 3.1 核心判断

> **当前最大的问题不是"配置少"或"提示词少"，而是"生效链路不够统一，死配置和半生效配置偏多"。**
> 看起来能配，实际上没用的东西，比没有还危险——它给维护者错误的预期。

### 3.2 问题清单

| #  | 问题                                         | 严重程度 | 来源 | 说明                                                                                             |
| -- | ------------------------------------------ | ---- | -- | ---------------------------------------------------------------------------------------------- |
| 1  | **CHAT\_API\_TOKEN 假鉴权**                   | 🔴 高 | 对方 | 文档声称"接口鉴权"，代码未实现。给人"好像有保护"的错觉，比没有还危险                                                           |
| 2  | **query\_patterns 完全死代码**                  | 🔴 高 | 对方 | 完整实现+配置齐全，但 `use_template` 永远为 False，主路径完全绕过。误导维护者以为模板匹配在工作                                    |
| 3  | **SQL 系统提示词 4 处重复**                        | 🔴 高 | 双方 | 硬编码在 4 个文件中，修改需同步 4 处                                                                          |
| 4  | **三条 SQL 生成链路约束不一致**                       | 🔴 高 | 对方 | sql\_query 有追加 Prompt，schedule\_task/manage\_scheduled\_task 没有。聊天查数、建任务、改任务生成的 SQL 风格和约束不完全一样 |
| 5  | **RAG 配置双轨制**                              | 🟡 中 | 双方 | `RagIngestSettings` 和 `os.getenv()` 读取相同变量，默认值分散                                               |
| 6  | **4 个死环境变量**                               | 🟡 中 | 对方 | `ENABLE_CLOUD_FALLBACK`、`CHAT_API_TOKEN`、`RAG_HYBRID_ALPHA`、`RAG_CANDIDATE_K` 声明了但没接入          |
| 7  | **前端配置链断层**                                | 🟡 中 | 对方 | `APP_*` vs `VITE_APP_*` vs `window.__APP_CONFIG__` 三套并存，本地开发改 `.env` 不生效                       |
| 8  | **display\_fields / required\_fields 死配置** | 🟡 中 | 双方 | YAML 中定义了 3 组展示提示词和必选字段，但无代码消费                                                                 |
| 9  | **环境变量散落无校验**                              | 🟡 中 | 双方 | `os.getenv()` 散落在 6+ 个文件，无类型校验                                                                 |
| 10 | **SYSTEM\_PROMPT 硬编码**                     | 🟢 低 | 我方 | 77 行提示词硬编码在 Python 中，不便于非开发人员调整                                                                |
| 11 | **Schema YAML 缓存不可刷新**                     | 🟢 低 | 我方 | `lru_cache` 导致 YAML 修改需重启                                                                      |

***

## 四、改良计划

### 阶段一：配置瘦身 — 清理死配置，消除假安全感（P0）

#### 1.1 CHAT\_API\_TOKEN 定性

**问题**：文档声称可做鉴权，代码未实现。给人"好像有保护"的错觉。

**方案**（二选一）：

- **A. 实现鉴权**：在 `main.py` 中增加中间件，校验 `Authorization: Bearer {CHAT_API_TOKEN}`，未配置 token 时跳过鉴权
- **B. 删除声明**：从 `.env.example`、`.env`、Docker 文档中移除 `CHAT_API_TOKEN`，避免误导

**建议**：如果短期不打算实现鉴权，选 B；如果需要鉴权，选 A 但需同步修改 Docker 配置。

#### 1.2 清理死环境变量

**操作**：

- 从 `.env.example` 和 `.env` 中移除 `ENABLE_CLOUD_FALLBACK`（无代码消费）
- 将 `RAG_HYBRID_ALPHA` 和 `RAG_CANDIDATE_K` 接入 `get_doc_rag_settings()`，让文档检索也能从环境变量配置（当前 `hybrid_search()` 用硬编码默认值 0.7/30）
- 或从 `.env.example` 中移除这两个变量，承认当前硬编码值

#### 1.3 query\_patterns 定性

**问题**：完整实现但从未触发，是最大的死代码块。

**方案**（二选一）：

- **A. 接入主流程**：在 `sql_tool.py` 的 SQL 生成流程中，先尝试 `select_query_pattern()` 匹配，命中则直接返回模板 SQL（降低延迟、提升稳定性），未命中再走 LLM 生成
- **B. 删除**：移除 `patterns.py`、`QueryPattern` 模型、YAML 中的 `query_patterns` 段落，减少维护负担

**建议**：query\_patterns 本身是很好的"高频查询直达模板"机制，接上能降低延迟、提升稳定性。推荐 A。

#### 1.4 display\_fields / required\_fields 定性

**方案**（二选一）：

- **A. 接入 SQL 生成**：在 `build_sql_prompt()` 中根据用户问题匹配 display\_fields，自动追加展示字段指导
- **B. 删除**：从 YAML 和模型中移除

**建议**：这块思路是对的（面向业务展示的字段规范），但短期如果没精力接入，先移除避免误导，后续需要时再加回来。

***

### 阶段二：提示词收口 — 消除重复，统一唯一真源（P0-P1）

#### 2.1 提取 SQL 系统提示词为常量

**操作**：

- 在 `sql_agent/prompt_builder.py` 中定义 `SQL_SYSTEM_PROMPT = "你是一个专业的数据库查询助手，只返回 SQL 语句，不要包含任何解释或其他内容。"`
- 4 个调用方（sql\_tool.py、scheduler\_tool.py、scheduler\_manage\_tool.py、service.py）统一 import

#### 2.2 合并 sql\_query 追加 Prompt 到 build\_sql\_prompt()

**问题**：sql\_query 有追加 Prompt，其他两条 SQL 生成链路没有，导致约束不一致。

**操作**：

- 将 `sql_tool.py` 第 163-170 行的追加内容合并到 `build_sql_prompt()` 的 instructions 列表中
- 这样三条链路（聊天/建任务/改任务）都走同一个 prompt 构建逻辑，约束完全一致
- 删除 `sql_tool.py` 中的追加逻辑

***

### 阶段三：配置体系统一 — 消除双轨制和散落（P1）

#### 3.1 后端 env 收口为统一 AppSettings

**操作**：

- 在 `core/config.py` 中创建 `AppSettings(BaseSettings)` 类，按领域划分子配置：
  - `DatabaseSettings`：DB\_TYPE/DB\_HOST/DB\_PORT/DB\_NAME/DB\_USER/DB\_PASSWORD/DATABASE\_URL/SQL\_MAX\_ROWS
  - `LlmSettings`：LLM\_BASE\_URL/LLM\_API\_KEY/CHAT\_MODEL/VISION\_MODEL/OLLAMA\_BASE\_URL
  - `RagRetrievalSettings`：当前散落在 retrieval.py 的所有 RAG 检索配置（含 RAG\_HYBRID\_ALPHA/RAG\_CANDIDATE\_K）
  - `RagIngestSettings`：保留现有，继承/复用 RagRetrievalSettings 的 Qdrant 连接部分
  - `AppMiscSettings`：CORS\_ORIGINS/CHAT\_DB\_PATH/AGENT\_NAME/TAVILY\_API\_KEY/WEB\_SEARCH\_MAX\_RESULTS
- 提供 `get_settings()` 单例，启动时打印"已生效配置摘要（脱敏）"
- 逐步替换各模块中的 `os.getenv()` 调用

**预期收益**：

- 一眼就知道：读了哪个文件、最终值来自哪里、哪些变量没被消费
- 类型安全，自动校验
- 默认值集中管理

#### 3.2 前端配置链统一

**问题**：`APP_*`、`VITE_APP_*`、`window.__APP_CONFIG__` 三套并存。

**方案**（二选一）：

- **A. 全走运行时 config.js**：删除 `src/config.js` 中的 `envConfig` 层（VITE\_\* 读取），只保留 `runtimeConfig > defaultConfig`。本地开发时直接改 `public/config.js`
- **B. 全走 Vite VITE\_**\*：在 `vite.config.js` 中配置 `envDir` 指向项目根目录，将 `.env.example` 中的 `APP_*` 改名为 `VITE_APP_*`

**建议**：选 A 更简单。运行时 config.js 已经是 Docker 部署的唯一生效路径，本地开发也直接改 `public/config.js` 即可，认知成本最低。

***

### 阶段四：提示词外置与热更新（P2）

#### 4.1 SYSTEM\_PROMPT 外置为 YAML

**操作**：

- 创建 `configs/system_prompt.yaml`
- 在 `core/config.py` 中增加 `get_system_prompt()` 函数
- `prompts.py` 改为从配置读取，保留硬编码作为 fallback
- 支持 Docker 挂载覆盖

#### 4.2 Schema YAML 热更新

**操作**：

- 将 `get_schema_runtime()` 的 `lru_cache` 替换为可手动清除的缓存
- 增加 `/api/v1/admin/reload_schema` 管理接口

***

## 五、实施优先级与步骤

| 阶段 | 步骤                                      | 优先级 | 影响范围   | 复杂度 |
| -- | --------------------------------------- | --- | ------ | --- |
| 一  | 1.1 CHAT\_API\_TOKEN 定性（实现或删除）          | P0  | 2-3 文件 | 低   |
| 一  | 1.2 清理死环境变量（接入或删除）                      | P0  | 2-3 文件 | 低   |
| 一  | 1.3 query\_patterns 定性（接入或删除）           | P0  | 3-4 文件 | 中   |
| 一  | 1.4 display\_fields/required\_fields 定性 | P0  | 2 文件   | 低   |
| 二  | 2.1 提取 SQL 系统提示词常量                      | P0  | 4 文件   | 低   |
| 二  | 2.2 合并追加 Prompt 到 build\_sql\_prompt    | P1  | 2 文件   | 中   |
| 三  | 3.1 后端 env 收口为 AppSettings              | P1  | 多文件    | 高   |
| 三  | 3.2 前端配置链统一                             | P1  | 3-4 文件 | 中   |
| 四  | 4.1 SYSTEM\_PROMPT 外置 YAML              | P2  | 2 文件   | 中   |
| 四  | 4.2 Schema YAML 热更新                     | P2  | 2 文件   | 中   |

***

## 六、对对方建议的反馈

| 对方观点                                       | 我的评价              | 补充                                           |
| ------------------------------------------ | ----------------- | -------------------------------------------- |
| "先做配置瘦身，分三类：生效/预留/历史"                      | ✅ 完全同意，这是最优先的事    | 我补充了具体的死变量清单和验证结果                            |
| "后端 env 收口成统一 Settings"                    | ✅ 同意              | 我细化了子 Settings 划分方案和启动时打印脱敏摘要的建议             |
| "前端配置链统一一种口径"                              | ✅ 同意，对方诊断准确       | 我补充了具体方案：推荐全走运行时 config.js，删除 envConfig 死代码层 |
| "SQL 提示词集中成唯一真源"                           | ✅ 同意              | 我进一步指出不仅是重复问题，更是三条链路约束不一致的隐患                 |
| "query\_patterns 要么启用要么删"                  | ✅ 同意              | 我验证了确实是完全死代码，推荐接入主流程                         |
| "display\_fields 要么接上要么去掉"                 | ✅ 同意              | 我补充了 required\_fields 也是死配置                  |
| "CHAT\_API\_TOKEN 要尽快定性"                   | ✅ 完全同意，这是安全层面最紧急的 | 我补充了"假鉴权比没有更危险"的判断                           |
| "RAG\_HYBRID\_ALPHA/RAG\_CANDIDATE\_K 没接入" | ✅ 验证属实            | 我补充了具体原因：`get_doc_rag_settings()` 不返回这两个值    |

**对方没提到但我觉得重要的**：

- Schema YAML 的 `lru_cache` 不可刷新问题（运维场景需要）
- SYSTEM\_PROMPT 外置 YAML 的价值（Docker 挂载、非开发人员可调）
- `RagIngestSettings` 与 `retrieval.py` 的双轨制问题（不仅是散落，而是同一变量两套默认值）

