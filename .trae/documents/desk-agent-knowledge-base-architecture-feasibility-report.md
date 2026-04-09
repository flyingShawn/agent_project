# Desk-Agent 知识库架构调整可行性调研分析报告

## 1. 项目现状分析

### 1.1 现有架构

通过对代码库的分析，当前项目具有以下特点：

- **RAG引擎已完整实现**：位于 `agent_backend/rag_engine/` 模块
- **Qdrant向量数据库已集成**：支持本地存储和远程服务
- **SQL生成模块已存在**：位于 `agent_backend/sql_agent/` 模块
- **配置管理已完善**：使用 Pydantic Settings + dotenv
- **已有的SQL样本库**：`data/desk-agent/sql/sql-example.md` 已存在

### 1.2 现有知识库结构

```
agent_project/
├── data/
│   └── desk-agent/
│       └── sql/
│           └── sql-example.md
├── .qdrant_local/
│   └── collection/
│       └── desk_agent_docs/
└── .env.example
```

### 1.3 现有配置文件

`.env.example` 中的相关配置：
- `RAG_DOCS_DIR=./data/docs`
- `RAG_QDRANT_COLLECTION=desk_agent_docs`
- 其他Qdrant和向量模型配置

---

## 2. 可行性评估

### 2.1 智能体命名方案（可行性：高）

**需求分析**：
- 从.env读取AGENT_NAME
- 影响：仅影响知识库文件路径
- 不影响核心业务逻辑

**实现方案**：
1. 在.env中添加 `AGENT_NAME=desk-agent`
2. 在配置中读取该变量
3. 动态构建文件路径：`data/{AGENT_NAME}/docs` 和 `data/{AGENT_NAME}/sql`

**风险评估**：
- 风险：低
- 影响范围：配置和路径构建
- 兼容措施：提供默认值 `desk-agent`

### 2.2 知识库架构调整（可行性：高）

**需求分析**：
- 标准问题知识库：`data/desk-agent/docs`
- SQL查询样本库：`data/desk-agent/sql`
- 物理隔离，独立检索

**实现方案**：
1. 使用Qdrant的独立collection实现物理隔离
   - docs知识库：`{AGENT_NAME}_docs`
   - SQL样本库：`{AGENT_NAME}_sql`
2. 分别配置独立的ingest和retrieval流程

**风险评估**：
- 风险：低
- 优势：现有RAG引擎支持灵活配置多个collection
- 兼容措施：保留原collection名称作为默认

### 2.3 SQL RAG检索集成（可行性：中高）

**需求分析**：
- SQL查询时优先检索SQL样本库
- 结合schema_metadata.yaml的表字段注释
- 提供给LLM提升准确性

**现有代码分析**：
- `prompt_builder.py` 中已有 `select_few_shots()` 函数，使用简单关键词匹配
- `schema_metadata.yaml` 中已有完整的表结构和注释
- SQL样本已存在于 `data/desk-agent/sql/sql-example.md`

**实现方案**：
1. 扩展RAG引擎支持SQL样本的检索
2. 修改 `prompt_builder.py` 集成RAG检索结果
3. 将检索到的SQL样本与schema信息结合

**风险评估**：
- 风险：中
- 挑战：需要调整提示词构建逻辑
- 优势：可大幅提升SQL生成准确性（参考研究报告中的预期提升）

### 2.4 向量数据库分区方案评估

**Qdrant Collection vs 其他方案对比**：

| 方案 | 优点 | 缺点 | 适用性 |
|-----|------|------|--------|
| **独立Collection** | 完全隔离、管理简单、查询高效 | 需要维护多个collection | ⭐⭐⭐⭐⭐ 推荐 |
| 单Collection + Payload过滤 | 只需一个collection | 查询性能下降，混合结果 | ⭐⭐ |
| 命名空间(Namespace) | Qdrant Cloud支持 | 本地模式不支持 | ⭐ |

**推荐方案**：使用独立的Qdrant Collection

---

## 3. 详细实施计划

### 3.1 第一阶段：配置和基础设施

#### 任务1：更新环境变量配置

**文件修改**：
- `.env.example`：添加AGENT_NAME和SQL相关配置

```env
# 智能体名称
AGENT_NAME=desk-agent

# RAG文档问答配置
RAG_DOCS_DIR=./data/${AGENT_NAME}/docs
RAG_QDRANT_COLLECTION=${AGENT_NAME}_docs

# SQL样本库配置
RAG_SQL_DIR=./data/${AGENT_NAME}/sql
RAG_QDRANT_SQL_COLLECTION=${AGENT_NAME}_sql
```

#### 任务2：扩展配置模块

**文件修改**：
- `agent_backend/rag_engine/settings.py`：添加SQL RAG相关配置

```python
class RagIngestSettings(BaseSettings):
    # 已有配置保持不变
    ...
    
    # 新增SQL相关配置
    sql_dir: str = "./data/desk-agent/sql"
    qdrant_sql_collection: str = "desk_agent_sql"
```

### 3.2 第二阶段：知识库架构调整

#### 任务3：创建目录结构

确保以下目录存在：
```
data/
└── desk-agent/
    ├── docs/      # 标准问题知识库
    └── sql/       # SQL查询样本库（已存在）
```

#### 任务4：扩展RAG引擎支持双知识库

**文件修改/新增**：

1. **修改 `agent_backend/rag_engine/ingest.py`**：
   - 添加 `ingest_sql_directory()` 函数
   - 支持独立的SQL样本导入流程

2. **修改 `agent_backend/rag_engine/retrieval.py`**：
   - 添加 `sql_hybrid_search()` 函数
   - 支持SQL样本库的独立检索

### 3.3 第三阶段：SQL RAG集成

#### 任务5：修改SQL提示词构建器

**文件修改**：
- `agent_backend/sql_agent/prompt_builder.py`

**修改内容**：
1. 导入RAG检索模块
2. 添加函数检索SQL样本
3. 集成检索结果到提示词中
4. 保留schema_metadata信息

#### 任务6：更新SQL Agent服务

**文件修改**：
- `agent_backend/sql_agent/service.py`
- 集成SQL RAG检索流程

### 3.4 第四阶段：代码清理（如需）

**评估**：当前SQL生成逻辑（`select_few_shots`等）可以保留作为后备方案，不建议完全删除。

**建议**：
- 保留现有代码作为fallback
- 添加开关控制使用哪种方式
- 逐步过渡到RAG方式

---

## 4. 潜在风险及规避措施

### 4.1 风险清单

| 风险 | 影响 | 概率 | 规避措施 |
|-----|------|------|---------|
| 向量检索增加响应时间 | 中 | 中 | 实现缓存、限制top_k |
| SQL样本不足导致效果不佳 | 高 | 中 | 渐进式扩展样本库、保留旧方法 |
| 路径变更导致兼容性问题 | 中 | 低 | 提供迁移脚本、向后兼容 |
| 多个Collection管理复杂 | 低 | 低 | 提供统一的管理CLI |

### 4.2 回滚方案

如遇到问题，可快速回滚：
1. 保留原有的collection和目录结构
2. 通过配置开关切换回旧方案
3. 数据库操作采用增量方式，不删除旧数据

---

## 5. 技术建议

### 5.1 向量数据库分区方案建议

**推荐使用独立Collection**，理由：
1. ✅ 完全物理隔离，避免误检索
2. ✅ 查询性能最优，无需过滤
3. ✅ 管理简单，可独立重建
4. ✅ 与现有架构兼容

### 5.2 SQL样本格式建议

建议SQL样本采用统一格式：

```markdown
## 查询场景：按IP查询设备信息

### 用户意图
查询指定IP的设备详细信息，包括所属部门和绑定用户

### SQL查询
```sql
SELECT
    m.ID,
    u.UserName AS UserName,
    g.GroupName AS GroupName,
    m.Name_C,
    m.Ip_C,
    m.Mac_c
FROM s_machine m
LEFT JOIN s_user u ON m.ClientId = u.ID
LEFT JOIN s_group g ON m.Groupid = g.id
WHERE m.Ip_C = :ip
```

### 说明
- 使用 LEFT JOIN 保证即使没有用户/部门也能返回设备
- 参数使用 :ip 格式
- 表别名遵循规范（m=machine, u=user, g=group）
```

### 5.3 提示词策略建议

建议的提示词组合：

```
【系统指令】
...

【数据库Schema】
(来自 schema_metadata.yaml)

【相关SQL示例】
(来自RAG检索的SQL样本库)

【同义词映射】
(来自 schema_metadata.yaml)

【用户问题】
{question}

【SQL】
```

---

## 6. 实施优先级和时间线

### 6.1 优先级排序

| 优先级 | 任务 | 预计工作量 |
|-------|------|-----------|
| P0 | 配置更新 + 目录结构 | 0.5天 |
| P0 | RAG引擎扩展支持双知识库 | 1天 |
| P1 | SQL提示词集成RAG检索 | 1天 |
| P1 | 测试和验证 | 0.5天 |
| P2 | 文档和示例完善 | 0.5天 |

**总计**：约3-4天完成核心功能

### 6.2 里程碑

- **Day 1**：完成配置和RAG引擎扩展
- **Day 2**：完成SQL RAG集成
- **Day 3**：测试验证和优化

---

## 7. 结论

### 7.1 可行性总结

| 方案项 | 可行性 | 推荐度 |
|-------|--------|--------|
| 智能体命名配置化 | 高 | ⭐⭐⭐⭐⭐ |
| 知识库架构调整（docs/sql分离） | 高 | ⭐⭐⭐⭐⭐ |
| SQL样本库独立向量存储 | 高 | ⭐⭐⭐⭐⭐ |
| SQL RAG检索集成 | 中高 | ⭐⭐⭐⭐ |
| 向量数据库分区（独立Collection） | 高 | ⭐⭐⭐⭐⭐ 推荐 |
| 移除现有SQL生成逻辑 | - | ❌ 不建议（保留作为后备） |

### 7.2 最终建议

✅ **建议实施方案**：
1. 采用智能体命名配置化
2. 实现docs和sql知识库物理隔离，使用独立Qdrant Collection
3. 集成SQL RAG检索，但**保留现有SQL生成逻辑作为fallback**
4. 渐进式扩展SQL样本库，持续优化效果

该方案技术风险低，与现有架构高度兼容，能够显著提升SQL生成准确性。
