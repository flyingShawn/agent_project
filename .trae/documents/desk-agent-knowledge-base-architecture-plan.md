# 智能体命名及知识库架构调整方案 — 可行性分析与实施计划

## 一、项目现状总结

### 1.1 当前架构概览

| 模块    | 当前状态                                | 关键文件                                        |
| ----- | ----------------------------------- | ------------------------------------------- |
| RAG引擎 | 完整实现，单collection `desk_agent_docs`  | `rag_engine/` 全模块                           |
| SQL生成 | 模板匹配+LLM，prompt\_builder硬编码few-shot | `sql_agent/service.py`, `prompt_builder.py` |
| 意图路由  | 关键词+正则评分，SQL/RAG二选一                 | `chat/router.py`                            |
| 向量存储  | Qdrant，支持payload过滤                  | `rag_engine/qdrant_store.py`                |
| 配置管理  | `.env` + Pydantic Settings          | `rag_engine/settings.py`, `.env.example`    |

### 1.2 当前数据目录

```
data/
├── docs/                    # RAG文档库（所有文档混在一起）
│   ├── EMM版本更新内容.xlsx
│   ├── sample.md
│   └── ...（8个文档）
└── desk-agent/
    └── sql/
        └── sql-example.md   # SQL示例（已存在但未接入RAG）
```

### 1.3 当前SQL生成流程

```
用户问题 → 意图识别 → SQL分支 → generate_secure_sql()
  → select_query_pattern()  # 模板匹配（可选）
  → build_sql_prompt()      # 构建prompt（schema + synonyms + few-shot from YAML）
  → LLM生成SQL
  → 安全校验
  → 执行SQL
  → LLM总结结果
```

**关键问题**：`build_sql_prompt()` 中的 few-shot 样例来自 `schema_metadata.yaml` 的 `sql_shots` 字段（仅4个），且选择策略是简单关键词匹配，无法捕捉语义相似性。

***

## 二、可行性分析

### 2.1 智能体命名方案 — 可行性：✅ 高

| 评估维度  | 分析                               |
| ----- | -------------------------------- |
| 技术可行性 | 高。仅需新增环境变量 `AGENT_NAME`，修改路径拼接逻辑 |
| 影响范围  | 仅影响知识库路径构建，不涉及核心业务逻辑             |
| 风险等级  | 低。向后兼容，可设置默认值 `desk-agent`       |
| 实施复杂度 | 低。约3-4个文件需修改                     |

**具体影响点**：

* `.env.example`：新增 `AGENT_NAME=desk-agent`

* `rag_engine/settings.py`：`docs_dir` 默认值改为 `./data/{AGENT_NAME}/docs`

* `rag_engine/retrieval.py`：`get_rag_settings()` 读取 `AGENT_NAME` 构建路径

* `docker-compose.yml`：环境变量和卷挂载路径

**命名规范注意**：

* 环境变量中用连字符：`desk-agent`（符合URL/CLI惯例）

* Python代码/路径中用下划线：`desk_agent`（符合Python惯例）

* Qdrant collection名用下划线：`desk_agent_docs`、`desk_agent_sql`

* 需要一个转换函数：`agent_name.replace("-", "_")`

### 2.2 知识库架构调整 — 可行性：✅ 高

| 评估维度  | 分析                       |
| ----- | ------------------------ |
| 技术可行性 | 高。目录结构已部分存在，仅需迁移和规范化     |
| 影响范围  | 文档存储路径、RAG入库配置、Docker卷挂载 |
| 风险等级  | 低。数据迁移简单，可保留旧路径兼容        |
| 实施复杂度 | 低。主要是目录移动和配置修改           |

**目标目录结构**：

```
data/
└── desk-agent/              # data/{AGENT_NAME}/
    ├── docs/                # 标准问题知识库
    │   ├── EMM版本更新内容.xlsx
    │   ├── sample.md
    │   └── ...
    └── sql/                 # SQL查询样本库
        └── sql-example.md
```

**迁移步骤**：

1. 将 `data/docs/*` 移动到 `data/desk-agent/docs/`
2. `data/desk-agent/sql/` 已存在，无需移动
3. 更新 `RAG_DOCS_DIR` 默认值为 `./data/desk-agent/docs`
4. 更新 Docker 卷挂载路径

### 2.3 SQL样本库RAG检索 — 可行性：✅ 高

| 评估维度  | 分析                        |
| ----- | ------------------------- |
| 技术可行性 | 高。现有RAG引擎已具备完整的入库和检索能力    |
| 影响范围  | SQL生成流程的prompt构建环节        |
| 风险等级  | 中。需确保检索质量，避免引入无关SQL样本     |
| 实施复杂度 | 中。需新增SQL专用collection和检索逻辑 |

**核心改造思路**：

当前 `build_sql_prompt()` 使用硬编码的 `sql_shots`（4个样例），改造为：

1. 通过RAG检索 `data/desk-agent/sql/` 中的SQL样本
2. 将检索到的SQL样本与 `schema_metadata.yaml` 的表字段注释结合
3. 共同作为prompt提供给LLM

**改造后的SQL生成流程**：

```
用户问题 → 意图识别 → SQL分支
  → RAG检索SQL样本（从 desk_agent_sql collection）
  → 加载schema_metadata.yaml表字段注释
  → 构建增强prompt（schema + synonyms + RAG检索的SQL样本 + 约束）
  → LLM生成SQL
  → 安全校验
  → 执行SQL
  → LLM总结结果
```

### 2.4 向量数据库分区方案 — 可行性分析

#### 方案A：独立Collection（推荐 ✅）

| 评估维度 | 分析                           |
| ---- | ---------------------------- |
| 物理隔离 | ✅ 完全隔离，数据存储独立                |
| 检索性能 | ✅ 每个collection更小，检索更快        |
| 管理便利 | ✅ 独立管理、独立备份、独立清理             |
| 资源开销 | ⚠️ 每个collection有独立的向量索引，略增内存 |
| 扩展性  | ✅ 新增知识库类型只需新增collection      |

**具体设计**：

```
Qdrant Collections:
├── desk_agent_docs    # 标准问题知识库（文档问答）
└── desk_agent_sql     # SQL查询样本库（SQL生成辅助）
```

**命名规则**：`{agent_name}_{type}`，其中 `agent_name` 为 `AGENT_NAME` 环境变量（连字符转下划线），`type` 为 `docs` 或 `sql`。

#### 方案B：单Collection + Payload过滤

| 评估维度 | 分析                  |
| ---- | ------------------- |
| 物理隔离 | ❌ 逻辑隔离，数据混存         |
| 检索性能 | ⚠️ 需要过滤，略慢；BM25需后处理 |
| 管理便利 | ⚠️ 管理复杂，删除/更新需过滤    |
| 资源开销 | ✅ 共享索引，内存更省         |
| 扩展性  | ⚠️ 数据量增大后性能下降       |

**具体设计**：在payload中添加 `kb_type` 字段（`docs`/`sql`），检索时通过filter限定。

#### 方案对比与推荐

| 对比项      | 方案A（独立Collection） | 方案B（Payload过滤） |
| -------- | ----------------- | -------------- |
| 物理隔离     | ✅ 完全              | ❌ 逻辑           |
| 检索定向性    | ✅ 天然隔离            | ⚠️ 需filter     |
| BM25兼容性  | ✅ 完美              | ⚠️ 需后处理过滤      |
| 代码改动量    | 中                 | 小              |
| 当前数据规模适配 | ✅ 适合              | ✅ 适合           |
| 未来扩展性    | ✅ 好               | ⚠️ 一般          |

**最终推荐：方案A（独立Collection）**

理由：

1. 当前项目数据规模小（文档<100，SQL样本<50），两个collection的内存开销可忽略
2. 独立collection天然实现物理隔离，检索时无需额外过滤逻辑
3. BM25混合检索在独立collection上更准确（文档频率计算不受跨类型数据干扰）
4. 未来新增知识库类型（如API文档库）只需新增collection，扩展性好
5. 与用户需求"SQL样本库与普通知识库的物理隔离"完全一致

### 2.5 SQL样本与Schema注释整合策略 — 可行性：✅ 高

**Prompt整合方案**：

```
┌─────────────────────────────────────────┐
│           SQL生成增强Prompt              │
├─────────────────────────────────────────┤
│ 1. 角色定义与约束指令                     │
│    （保留现有：只允许SELECT、别名规则等）  │
├─────────────────────────────────────────┤
│ 2. 受限表和敏感列                         │
│    （保留现有，来自schema_metadata.yaml） │
├─────────────────────────────────────────┤
│ 3. 数据库表与列（含semantic_key）         │
│    （保留现有，来自schema_metadata.yaml） │
├─────────────────────────────────────────┤
│ 4. 同义词映射                             │
│    （保留现有，来自schema_metadata.yaml） │
├─────────────────────────────────────────┤
│ 5. RAG检索的SQL样本 ← 【新增】           │
│    （从desk_agent_sql collection检索，   │
│     替代原硬编码的sql_shots）             │
├─────────────────────────────────────────┤
│ 6. 用户问题                              │
└─────────────────────────────────────────┘
```

**关键设计**：

* RAG检索的SQL样本**替代**原 `sql_shots`，而非叠加，避免prompt过长

* 检索top\_k建议设为3-5（与原few-shot数量一致）

* SQL样本文件格式需结构化，包含：查询意图描述、SQL语句、适用场景说明

### 2.6 代码清理范围 — 可行性：✅ 高

**需移除/重构的组件**：

| 文件                                   | 处理方式   | 原因                      |
| ------------------------------------ | ------ | ----------------------- |
| `sql_agent/prompt_builder.py`        | **重构** | 核心改造对象，需集成RAG检索         |
| `sql_agent/langgraph_flow.py`        | **删除** | 未被使用，service.py直接调用llm  |
| `sql_agent/llm_clients.py`           | **删除** | 与 `llm/clients.py` 功能重复 |
| `sql_agent/patterns.py`              | **保留** | 模板匹配仍有价值，作为快速路径         |
| `sql_agent/service.py`               | **重构** | 集成RAG检索SQL样本            |
| `schema_metadata.yaml` 的 `sql_shots` | **移除** | 被RAG检索替代                |
| `schema_models.py` 的 `SqlShotDef`    | **移除** | 对应yaml字段移除              |

***

## 三、详细实施步骤

### 阶段一：智能体命名与目录结构调整（低风险）

#### 步骤1.1：新增AGENT\_NAME环境变量

**修改文件**：`.env.example`

* 新增 `AGENT_NAME=desk-agent`

* 修改 `RAG_DOCS_DIR=./data/desk-agent/docs`

* 修改 `RAG_QDRANT_COLLECTION=desk_agent_docs`

* 新增 `RAG_SQL_DIR=./data/desk-agent/sql`

* 新增 `RAG_SQL_QDRANT_COLLECTION=desk_agent_sql`

#### 步骤1.2：修改RAG配置模块

**修改文件**：`rag_engine/settings.py`

* `RagIngestSettings` 新增 `agent_name` 字段，从 `AGENT_NAME` 环境变量读取

* `docs_dir` 默认值改为动态：`./data/{agent_name}/docs`

* 新增 `sql_dir` 字段：`./data/{agent_name}/sql`

* 新增 `qdrant_sql_collection` 字段：默认 `{agent_name_underscore}_sql`

#### 步骤1.3：迁移文档目录

* 将 `data/docs/` 下所有文件移动到 `data/desk-agent/docs/`

* `data/desk-agent/sql/` 已存在，确认 `sql-example.md` 内容

#### 步骤1.4：更新Docker配置

**修改文件**：`docker-compose.yml`

* 更新卷挂载路径：`${RAG_DOCS_DIR:-./data/desk-agent/docs}`

* 新增SQL目录挂载：`${RAG_SQL_DIR:-./data/desk-agent/sql}`

* 新增环境变量 `AGENT_NAME`

### 阶段二：SQL样本库RAG接入（核心改造）

#### 步骤2.1：规范化SQL样本文件格式

**修改文件**：`data/desk-agent/sql/sql-example.md`

将SQL样本文件改为结构化格式，每个样本包含：

````markdown
#### 查询场景：查询指定IP的机器详细信息

**适用场景**：当用户询问某IP地址对应的设备详细信息时使用

**关键表**：s_machine, s_group, s_user, onlineinfo

```sql
SELECT ... FROM s_machine ... WHERE IP_C = :ip
````

```

这种格式有利于：
- RAG检索时匹配"查询场景"和"适用场景"的语义
- 分块时按 `####` 标题自然分割
- 保留SQL完整性

#### 步骤2.2：扩展RAG入库模块支持SQL目录

**修改文件**：`rag_engine/ingest.py`
- 新增 `ingest_sql_directory()` 函数，或为 `ingest_directory()` 增加 `kb_type` 参数
- SQL入库时在payload中添加 `kb_type: "sql"` 标记
- 使用独立的 `qdrant_sql_collection`

**修改文件**：`rag_engine/state.py`
- SQL样本库使用独立的状态文件：`rag_sql_ingest_state.json`

#### 步骤2.3：新增SQL样本检索函数

**修改文件**：`rag_engine/retrieval.py`
- 新增 `get_sql_rag_settings()` 函数，读取SQL专用RAG配置
- 新增 `search_sql_samples()` 函数，封装SQL样本检索逻辑
- 检索参数调优：`top_k=3`，`candidate_k=15`，`alpha=0.8`（SQL样本更依赖语义匹配）

#### 步骤2.4：重构SQL Prompt构建器

**修改文件**：`sql_agent/prompt_builder.py`
- `build_sql_prompt()` 新增 `sql_samples` 参数
- 用RAG检索的SQL样本替代原 `select_few_shots()` 的硬编码样例
- 保留schema信息、同义词、安全约束等现有逻辑
- 移除 `select_few_shots()` 和 `_shot_score()` 函数

#### 步骤2.5：重构SQL生成服务

**修改文件**：`sql_agent/service.py`
- `generate_secure_sql()` 中集成RAG检索SQL样本的步骤
- 流程调整：
  1. 模板匹配（保留，作为快速路径）
  2. **新增**：RAG检索SQL样本
  3. 构建增强prompt（含RAG检索结果）
  4. LLM生成SQL
  5. 安全校验（保留）

#### 步骤2.6：新增SQL样本同步API

**修改文件**：`api/v1/rag.py`
- 新增 `POST /api/v1/rag/sync-sql` 端点，触发SQL样本库同步
- 复用现有同步机制，指向SQL专用collection

### 阶段三：代码清理与优化

#### 步骤3.1：移除冗余SQL生成组件

**删除文件**：
- `sql_agent/langgraph_flow.py` — 未被使用
- `sql_agent/llm_clients.py` — 与 `llm/clients.py` 重复

**修改文件**：
- `sql_agent/service.py` — 移除对 `langgraph_flow` 的引用（如有）
- `schema_metadata.yaml` — 移除 `sql_shots` 字段
- `core/schema_models.py` — 移除 `SqlShotDef` 类及相关引用
- `core/config_loader.py` — 移除 `sql_shots` 相关索引构建逻辑

#### 步骤3.2：清理import和依赖

- 检查所有文件中是否还有对已删除模块的import
- 清理 `requirements.txt` 中不再需要的依赖（如 `langgraph`，需确认无其他使用）

#### 步骤3.3：更新RAG同步API

**修改文件**：`api/v1/rag.py`
- 现有 `/rag/sync` 端点同时同步docs和sql两个目录
- 或保持分离，让前端可以独立触发同步

### 阶段四：测试与验证

#### 步骤4.1：功能测试
- 验证 `AGENT_NAME` 环境变量正确读取
- 验证文档目录迁移后RAG检索正常
- 验证SQL样本库独立入库和检索
- 验证SQL生成流程中RAG检索的SQL样本正确注入prompt

#### 步骤4.2：回归测试
- 验证RAG文档问答功能不受影响
- 验证SQL查询功能正常（模板匹配+LLM生成）
- 验证意图识别路由正常

#### 步骤4.3：性能测试
- 测量SQL样本检索的延迟
- 测量整体SQL生成流程的端到端延迟
- 对比改造前后的SQL生成准确率

---

## 四、潜在风险与规避措施

### 4.1 数据迁移风险

| 风险 | 影响 | 规避措施 |
|------|------|---------|
| 文档目录迁移后旧路径失效 | RAG检索失败 | 保留旧路径兼容，支持环境变量覆盖 |
| Qdrant已有向量数据与新路径不匹配 | 检索返回旧路径 | 执行全量同步（full mode）重建索引 |
| Docker卷挂载路径变更 | 容器启动失败 | 更新docker-compose.yml，添加注释说明 |

### 4.2 RAG检索质量风险

| 风险 | 影响 | 规避措施 |
|------|------|---------|
| SQL样本检索不相关 | Prompt质量下降，SQL生成错误 | 调优检索参数（alpha、top_k），设置最低相似度阈值 |
| SQL样本数量不足 | RAG检索无结果 | 保留回退机制：无检索结果时使用schema信息直接生成 |
| SQL样本文件格式不规范 | 分块质量差，检索不准 | 制定SQL样本文件编写规范，统一格式 |
| BM25对SQL语法的分词效果差 | 关键词检索不准 | SQL样本文件中增加自然语言描述，提升BM25匹配率 |

### 4.3 系统稳定性风险

| 风险 | 影响 | 规避措施 |
|------|------|---------|
| 新增RAG检索步骤增加延迟 | SQL生成响应变慢 | SQL样本库小，检索延迟<100ms，可接受 |
| 两个Collection增加内存开销 | 资源占用增加 | SQL样本库极小（<50条），额外内存<10MB |
| 代码重构引入bug | 功能异常 | 分阶段实施，每阶段充分测试 |

### 4.4 向后兼容风险

| 风险 | 影响 | 规避措施 |
|------|------|---------|
| 移除sql_shots后旧配置文件报错 | 启动失败 | schema_models.py中sql_shots设为可选字段 |
| 移除langgraph_flow后其他模块引用报错 | 运行时错误 | 全局搜索确认无其他引用后再删除 |
| AGENT_NAME未设置时路径异常 | 功能异常 | 设置默认值 `desk-agent`，确保向后兼容 |

---

## 五、向量数据库分区方案专业建议

### 5.1 Qdrant分区能力评估

Qdrant **不支持**传统关系数据库意义上的"分区"（如MySQL的PARTITION BY）。Qdrant提供的隔离机制有：

| 机制 | 说明 | 适用场景 |
|------|------|---------|
| **多Collection** | 完全独立的向量集合，各有索引 | 不同类型数据的物理隔离 |
| **Payload过滤** | 同一collection内按metadata过滤 | 同类型数据的子集筛选 |
| **分片(Sharding)** | 单collection跨节点分布 | 大规模数据的水平扩展 |
| **命名空间** | Qdrant无此概念 | — |

### 5.2 推荐方案：双Collection架构

```

Qdrant实例
├── desk\_agent\_docs          # 文档知识库
│   ├── 向量索引（COSINE）
│   ├── Payload: source\_path, doc\_hash, text, heading, kb\_type="docs"
│   └── 状态文件: rag\_ingest\_state.json
│
└── desk\_agent\_sql           # SQL样本库
├── 向量索引（COSINE）
├── Payload: source\_path, doc\_hash, text, heading, kb\_type="sql"
└── 状态文件: rag\_sql\_ingest\_state.json

```

### 5.3 为什么不用单Collection+过滤

1. **BM25混合检索的兼容性**：当前 `hybrid_search()` 先向量检索取candidate_k个候选，再对候选做BM25打分。如果单collection混存，向量检索可能返回跨类型的候选，BM25的文档频率计算会被跨类型数据干扰，降低检索精度。

2. **物理隔离需求明确**：用户明确要求"SQL样本库与普通知识库的物理隔离"，单collection+过滤只是逻辑隔离。

3. **独立管理需求**：SQL样本库和文档库的更新频率、同步策略、备份策略可能不同，独立collection更灵活。

4. **性能考量**：SQL样本库极小（预计<50条chunk），独立collection的索引构建和检索开销可忽略。反而因为collection更小，检索速度更快。

### 5.4 未来扩展建议

如果未来需要更多类型的知识库（如API文档库、运维手册库等），只需按相同模式新增collection：

```

desk\_agent\_docs    # 标准问题知识库
desk\_agent\_sql     # SQL查询样本库
desk\_agent\_api     # API文档库（未来）
desk\_agent\_ops     # 运维手册库（未来）

```

Collection命名规则：`{agent_name}_{kb_type}`，确保清晰和一致。

---

## 六、实施优先级与时间规划建议

| 优先级 | 阶段 | 内容 | 依赖 |
|-------|------|------|------|
| P0 | 阶段一 | 智能体命名与目录调整 | 无 |
| P0 | 阶段二 | SQL样本库RAG接入 | 阶段一 |
| P1 | 阶段三 | 代码清理与优化 | 阶段二 |
| P1 | 阶段四 | 测试与验证 | 阶段三 |

**建议**：严格按照阶段顺序执行，每个阶段完成后进行充分测试再进入下一阶段。

---

## 七、涉及修改的文件清单

### 新增文件
无（优先编辑现有文件）

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `.env.example` | 新增AGENT_NAME、RAG_SQL_DIR、RAG_SQL_QDRANT_COLLECTION |
| `rag_engine/settings.py` | 新增agent_name、sql_dir、qdrant_sql_collection字段 |
| `rag_engine/ingest.py` | 支持SQL目录入库，独立collection |
| `rag_engine/retrieval.py` | 新增get_sql_rag_settings()、search_sql_samples() |
| `rag_engine/state.py` | 支持SQL独立状态文件 |
| `sql_agent/service.py` | 集成RAG检索SQL样本 |
| `sql_agent/prompt_builder.py` | 重构，用RAG样本替代硬编码few-shot |
| `api/v1/rag.py` | 新增SQL样本同步端点 |
| `chat/handlers.py` | SQL处理流程中调用RAG检索 |
| `configs/schema_metadata.yaml` | 移除sql_shots字段 |
| `core/schema_models.py` | 移除SqlShotDef |
| `core/config_loader.py` | 移除sql_shots索引逻辑 |
| `docker-compose.yml` | 更新环境变量和卷挂载 |
| `data/desk-agent/sql/sql-example.md` | 规范化SQL样本格式 |

### 删除文件

| 文件 | 删除原因 |
|------|---------|
| `sql_agent/langgraph_flow.py` | 未被使用 |
| `sql_agent/llm_clients.py` | 与llm/clients.py重复 |

### 迁移操作

| 操作 | 说明 |
|------|------|
| `data/docs/*` → `data/desk-agent/docs/` | 文档目录迁移 |
```

