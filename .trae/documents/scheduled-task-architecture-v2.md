# 智能体定时任务调度系统 — 架构方案（第二轮）

## 一、当前架构理解

### 技术栈
- **后端**: FastAPI + LangGraph (StateGraph) + SQLAlchemy (async aiosqlite + sync pymysql)
- **前端**: Vue 3 + Vite + TailwindCSS
- **向量库**: Qdrant + FastEmbed
- **LLM**: LangChain ChatOpenAI (兼容 OpenAI 协议，支持 Ollama/DeepSeek/Qwen)
- **部署**: Docker Compose (backend + frontend + qdrant)

### 模块划分
```
agent_backend/
├── agent/          # Agent 编排层（graph/nodes/state/prompts/stream/tools）
├── sql_agent/      # SQL 生成/执行/安全校验/连接管理
├── rag_engine/     # RAG 检索/向量化/分块/导入
├── llm/            # LLM 调用（factory.py: get_llm / get_sql_llm）
├── api/v1/         # API 路由（chat/conversations/health/metadata/rag/sql_agent/export）
├── db/             # 聊天历史 SQLite（chat_history.py + models.py）
├── core/           # 基础设施（config/errors/logging/request_id/schema_models）
└── configs/        # 业务配置 YAML（schema_metadata.yaml）
```

### 调用关系
```
前端 → POST /api/v1/chat → chat.py
  → 构建 AgentState → get_agent_graph()
  → LangGraph StateGraph 流程:
      init_node → agent_node(LLM+ToolCalling) → [tools/respond 条件路由]
      tools → tool_result_node(执行Tool) → agent_node(循环)
      respond → END
  → stream.py → SSE 流式输出
```

### 关键约束
1. **业务数据库(MySQL)只读**: `sql_safety.py` 强制只允许 SELECT，禁止 INSERT/UPDATE/DELETE
2. **应用数据库(SQLite)读写**: 聊天历史存储在 `data/chat_history.db`，使用异步引擎(aiosqlite)
3. **SQL执行是同步的**: `execute_sql()` 使用同步 SQLAlchemy 引擎，通过 `ConnectionManager` 管理连接
4. **LLM调用是同步的**: `get_sql_llm().invoke()` 是同步阻塞调用
5. **单进程部署**: Docker 单容器，无分布式需求

---

## 二、问题分析

### 🔴 核心问题1：任务结果表存储位置冲突

**用户需求**："就当前连接的数据库中加个agent_task表"

**技术约束**：当前连接的 MySQL 业务数据库是**只读**的（sql_safety.py 强制 SELECT-ONLY），在业务库中建表需要写权限，违反现有安全设计。

**风险**：
- 在业务库建表可能引发运维冲突（DBA 不允许应用自行建表）
- 业务库是外部系统管理，schema 变更不受控
- 打破"只读"安全边界后，后续可能误写业务数据

### 🔴 核心问题2：动态任务的 SQL 生成可靠性

**场景**：用户说"每隔2小时统计USB日志情况"，没有提供 SQL 模板。

**问题**：
- 每次 LLM 生成的 SQL 可能不同（温度=0 也非完全确定性）
- LLM 可能生成语法错误的 SQL，导致任务持续失败
- 没有人工审核环节，错误 SQL 会反复执行

### 🟡 问题3：定时任务与异步事件循环的兼容性

**现状**：`execute_sql()` 和 `get_sql_llm().invoke()` 都是同步阻塞函数。

**问题**：APScheduler AsyncIOScheduler 在异步事件循环中触发回调，直接调用同步函数会阻塞整个事件循环，影响所有 HTTP 请求处理。

### 🟡 问题4：定时任务缺少数据库连接上下文

**现状**：`execute_sql()` 通过 `session_id` 复用 `ConnectionManager` 的连接。

**问题**：定时任务不在用户会话上下文中，没有 `session_id`。不传 `session_id` 时每次创建临时连接，效率低。

### 🟡 问题5：已有方案的部分设计需重新审视

之前 `.trae/specs/add-scheduled-task-agent/` 中的方案存在以下需调整的点：
- 建表方式已优化为 ORM + create_all（✅ 正确）
- APScheduler jobstore 已优化为 MemoryJobStore + DB 恢复（✅ 正确）
- 但动态任务每次执行都调 LLM 生成 SQL（❌ 应缓存）
- 缺少任务执行超时控制
- 缺少任务结果的通知/回调机制（预留接口）

---

## 三、方案设计（本轮提案）

### 3.1 架构调整思路

新增 `agent_backend/scheduler/` 模块，作为与 `agent/`、`sql_agent/`、`rag_engine/` 平级的独立模块。调度器与 FastAPI 应用生命周期绑定，通过 `schedule_task` Agent Tool 支持聊天创建任务。

### 3.2 模块拆分

```
agent_backend/scheduler/           # 新增模块
├── __init__.py                    # 导出 SchedulerManager, get_scheduler_manager
├── manager.py                     # SchedulerManager 单例（调度器生命周期+任务CRUD）
└── executor.py                    # TaskExecutor（任务执行+结果写入）

agent_backend/db/models.py         # 修改：新增 AgentTask, AgentTaskResult ORM 模型
agent_backend/agent/tools/scheduler_tool.py  # 新增：schedule_task Agent Tool
agent_backend/configs/scheduled_tasks.yaml   # 新增：默认任务配置文件
```

### 3.3 数据流/调用链变化

```
应用启动
  ├── init_db() → Base.metadata.create_all（自动创建 agent_task / agent_task_result 表）
  ├── SchedulerManager.start()
  │   ├── 从 agent_task 表读取 status=active 的任务 → 注册到 APScheduler
  │   ├── 从 scheduled_tasks.yaml 读取默认任务 → 与 DB 对比 → 仅新增不存在的
  │   └── 启动 AsyncIOScheduler
  └── 调度器运行中

定时触发
  ├── APScheduler 触发回调（async）
  ├── TaskExecutor.execute_task(task_id)
  │   ├── asyncio.to_thread(同步执行)
  │   │   ├── 模板任务：直接执行 sql_template
  │   │   └── 动态任务：执行已缓存的 SQL（创建时已生成并存储）
  │   ├── 结果写入 agent_task_result 表
  │   └── 更新 agent_task 的 last_run_at / next_run_at
  └── 异常捕获 → 写入 error 记录

聊天创建任务
  ├── 用户："每隔30分钟记录在线客户端数量"
  ├── LLM → schedule_task Tool（action=create）
  │   ├── 动态任务：先调用 get_sql_llm 生成 SQL → 安全校验 → 存储为 sql_template
  │   └── 模板任务：直接使用用户/配置提供的 sql_template
  ├── SchedulerManager.add_task()
  │   ├── 写入 agent_task 表
  │   └── 注册到 APScheduler
  └── 返回确认信息（含 task_id 和生成的 SQL）

应用关闭
  ├── SchedulerManager.shutdown()
  └── ConnectionManager.shutdown()
```

### 3.4 关键设计决策

#### 决策1：任务表存储位置 → SQLite（与聊天历史共存）

**理由**：
1. 业务 MySQL 是只读的，不应打破安全边界
2. 任务结果是应用自身数据，不是业务数据
3. SQLite 使用 ORM + create_all 自动建表，与现有模式一致
4. 后续如需从外部访问任务结果，可通过 REST API 提供

**对外访问方案**：通过 `GET /api/v1/scheduler/tasks/{task_id}/results` API 暴露任务结果，外部系统可调用 API 获取数据，无需直接访问 SQLite。

#### 决策2：动态任务 SQL 生成策略 → 创建时生成并缓存

**理由**：
1. 避免 LLM 每次生成不同 SQL 导致结果不一致
2. 减少 LLM 调用开销（每次执行省去一次 LLM 调用）
3. 创建时生成 SQL 可立即校验，发现问题及时反馈用户
4. 用户可通过聊天让 LLM 重新生成 SQL（action=update）

**流程**：
- 用户说"每隔2小时统计USB日志" → LLM 调用 schedule_tool(create)
- Tool 内部先调用 get_sql_llm 生成 SQL → 安全校验 → 试执行验证
- 验证通过后，将 SQL 存入 agent_task.sql_template 字段
- 后续定时执行直接使用缓存的 sql_template

#### 决策3：调度框架 → APScheduler 3.x AsyncIOScheduler + MemoryJobStore

**理由**：
1. 轻量内嵌，无需外部消息代理，与单容器部署一致
2. 原生异步，与 FastAPI 事件循环兼容
3. 运行时动态增删改任务
4. MemoryJobStore + DB 恢复策略：任务定义的"权威来源"是 agent_task 表，启动时从 DB 恢复

#### 决策4：同步代码处理 → asyncio.to_thread 包装

**理由**：
1. `execute_sql()` 和 `get_sql_llm().invoke()` 都是同步函数
2. 直接在 async 回调中调用会阻塞事件循环
3. `asyncio.to_thread()` 在线程池中执行同步代码，不阻塞事件循环

#### 决策5：调度器数据库连接 → 专用 session_id = "__scheduler__"

**理由**：
1. 复用 ConnectionManager 的连接管理能力
2. 避免每次执行创建临时连接
3. 固定 session_id 便于连接健康检查和清理

### 3.5 agent_task 表设计

```sql
-- 存储在 SQLite（data/chat_history.db），与 Conversation/Message 共存

CREATE TABLE agent_task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id VARCHAR(64) NOT NULL UNIQUE,       -- 任务唯一标识
    agent_name VARCHAR(128) NOT NULL,           -- 智能体名称（如 desk-agent）
    task_name VARCHAR(256) NOT NULL,            -- 任务名称（如 统计在线客户端数量）
    task_type VARCHAR(32) NOT NULL DEFAULT 'interval',  -- interval/cron/date
    task_config TEXT,                           -- JSON: {"interval_seconds":1800} 或 {"cron_expr":"0 */2 * * *"}
    sql_template TEXT,                          -- 预定义SQL（模板任务）或LLM生成后缓存的SQL（动态任务）
    description TEXT,                           -- 自然语言描述（动态任务原始描述）
    status VARCHAR(16) NOT NULL DEFAULT 'active',  -- active/paused/completed/error
    last_run_at REAL,                           -- 上次执行时间（Unix时间戳，与Message.created_at一致）
    next_run_at REAL,                           -- 下次执行时间（Unix时间戳）
    created_by VARCHAR(64) DEFAULT 'system',    -- system/chat/user
    created_at REAL NOT NULL,                   -- 创建时间（Unix时间戳）
    updated_at REAL NOT NULL                    -- 更新时间（Unix时间戳）
);

CREATE TABLE agent_task_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id VARCHAR(64) NOT NULL,               -- 关联任务ID
    agent_name VARCHAR(128) NOT NULL,           -- 智能体名称
    run_at REAL NOT NULL,                       -- 执行时间（Unix时间戳）
    status VARCHAR(16) NOT NULL DEFAULT 'success',  -- success/error
    result_data TEXT,                           -- 执行结果JSON
    result_summary TEXT,                        -- 结果摘要文本
    error_message TEXT,                         -- 错误信息
    duration_ms INTEGER,                        -- 执行耗时毫秒
    created_at REAL NOT NULL                    -- 记录创建时间
);

CREATE INDEX idx_agent_task_task_id ON agent_task(task_id);
CREATE INDEX idx_agent_task_agent_name ON agent_task(agent_name);
CREATE INDEX idx_agent_task_status ON agent_task(status);
CREATE INDEX idx_agent_task_result_task_id ON agent_task_result(task_id);
CREATE INDEX idx_agent_task_result_agent_name ON agent_task_result(agent_name);
CREATE INDEX idx_agent_task_result_run_at ON agent_task_result(run_at);
```

**设计要点**：
- 时间字段使用 REAL（Unix时间戳），与现有 Message/Conversation 模型一致
- task_id 全局唯一，关联两张表
- sql_template 统一存储最终执行的 SQL（无论来源是配置文件还是 LLM 生成）
- description 保留原始自然语言描述，便于后续重新生成 SQL
- created_by 区分任务来源

### 3.6 默认任务配置文件

```yaml
# agent_backend/configs/scheduled_tasks.yaml
agent_name: desk-agent

tasks:
  - task_id: online_client_count
    task_name: 统计在线客户端数量
    task_type: interval
    interval_seconds: 1800
    sql_template: |
      SELECT COUNT(*) AS online_count
      FROM s_machine
      WHERE IsOnline = 1
    description: 每隔30分钟统计在线客户端数量

  - task_id: asset_change_detection
    task_name: 统计新增资产变更的设备
    task_type: interval
    interval_seconds: 1800
    sql_template: |
      SELECT m.MachineName, m.IP, m.GroupID, m.LastUpdateTime
      FROM s_machine m
      WHERE m.LastUpdateTime >= DATE_SUB(NOW(), INTERVAL 30 MINUTE)
    description: 每隔30分钟统计新增资产变更的设备

  - task_id: usb_log_stats
    task_name: 统计USB日志情况
    task_type: interval
    interval_seconds: 7200
    sql_template: |
      SELECT COUNT(*) AS usb_event_count
      FROM a_usblog
      WHERE LogTime >= DATE_SUB(NOW(), INTERVAL 2 HOUR)
    description: 每隔2小时统计USB日志情况
```

**设计要点**：
- 所有默认任务都提供 sql_template，确保首次执行即可成功
- 无 sql_template 的任务在聊天创建时由 LLM 生成并缓存
- 配置文件中的任务 created_by 标记为 system

### 3.7 schedule_task Agent Tool 设计

```
ScheduleTaskInput:
  action: Literal["create", "list", "pause", "resume", "delete", "update"]
  task_name: Optional[str]       -- create 时必填
  interval_seconds: Optional[int] -- create + interval 类型
  cron_expr: Optional[str]       -- create + cron 类型
  description: Optional[str]     -- create 时必填（自然语言描述）
  sql_template: Optional[str]    -- create 时可选（有则直接用，无则LLM生成）
  task_id: Optional[str]         -- pause/resume/delete/update 时必填
```

**action 说明**：
- `create`: 创建新任务 → 若无 sql_template 则调 LLM 生成 → 安全校验 → 写入 DB → 注册调度
- `list`: 返回所有活跃任务列表
- `pause`: 暂停任务
- `resume`: 恢复任务
- `delete`: 删除任务
- `update`: 更新任务的 SQL（重新调 LLM 生成）

### 3.8 REST API 设计

```
GET    /api/v1/scheduler/tasks                    -- 获取任务列表
GET    /api/v1/scheduler/tasks/{task_id}          -- 获取单个任务详情
GET    /api/v1/scheduler/tasks/{task_id}/results   -- 获取任务执行结果（支持 limit 参数）
POST   /api/v1/scheduler/tasks/{task_id}/run       -- 手动触发一次任务
PUT    /api/v1/scheduler/tasks/{task_id}/pause     -- 暂停任务
PUT    /api/v1/scheduler/tasks/{task_id}/resume    -- 恢复任务
DELETE /api/v1/scheduler/tasks/{task_id}           -- 删除任务
```

### 3.9 结果清理策略

- 默认保留最近 7 天的执行结果
- SchedulerManager 启动时执行一次清理
- 每天凌晨自动清理一次（注册一个内部清理任务）
- agent_task 表可选添加 `result_retention_days` 字段，支持按任务配置保留天数

---

## 四、可选方案

### 方案对比：任务结果表存储位置

| 维度 | 方案A: SQLite（推荐） | 方案B: MySQL 业务库 | 方案C: 双写 |
|------|----------------------|-------------------|-----------|
| 安全性 | ✅ 不打破只读边界 | ❌ 需要写权限 | ⚠️ 部分打破 |
| 运维冲突 | ✅ 无冲突 | ❌ 可能与DBA冲突 | ⚠️ 部分冲突 |
| 外部访问 | ⚠️ 需通过API | ✅ 直接SQL查询 | ✅ 直接SQL查询 |
| 建表方式 | ✅ ORM自动建表 | ⚠️ 需手动建表或额外逻辑 | ⚠️ 复杂 |
| 一致性 | ✅ 与聊天历史一致 | ❌ 不一致 | ❌ 双写一致性风险 |
| 复杂度 | ✅ 低 | ⚠️ 中 | ❌ 高 |

### 方案对比：动态任务 SQL 生成策略

| 维度 | 方案A: 创建时生成并缓存（推荐） | 方案B: 每次执行时生成 |
|------|------------------------------|---------------------|
| 一致性 | ✅ 结果一致 | ❌ SQL可能变化 |
| 性能 | ✅ 无LLM开销 | ❌ 每次LLM调用 |
| 可靠性 | ✅ 创建时即可验证 | ❌ 可能持续失败 |
| 灵活性 | ⚠️ 需手动更新SQL | ✅ 自动适应schema变化 |

### 最佳方案判断

**我推荐的最佳方案组合**：
1. **任务表存储**: 方案A（SQLite）— 安全性最高，与现有架构一致，外部访问通过 API 满足
2. **SQL生成策略**: 方案A（创建时生成并缓存）— 可靠性最好，性能最优
3. **调度框架**: APScheduler 3.x AsyncIOScheduler — 轻量、异步、动态任务

---

## 五、文件变更清单

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| 修改 | `requirements.txt` | 新增 APScheduler>=3.10,<4.0 |
| 修改 | `agent_backend/db/models.py` | 新增 AgentTask、AgentTaskResult ORM 模型 |
| 新建 | `agent_backend/scheduler/__init__.py` | 模块入口 |
| 新建 | `agent_backend/scheduler/manager.py` | SchedulerManager 调度器管理 |
| 新建 | `agent_backend/scheduler/executor.py` | TaskExecutor 任务执行器 |
| 新建 | `agent_backend/configs/scheduled_tasks.yaml` | 默认任务配置 |
| 修改 | `agent_backend/main.py` | 集成调度器生命周期 |
| 修改 | `docker-compose.yml` | 新增调度器环境变量 |
| 新建 | `agent_backend/agent/tools/scheduler_tool.py` | schedule_task Tool |
| 修改 | `agent_backend/agent/tools/__init__.py` | 注册 schedule_task |
| 修改 | `agent_backend/agent/prompts.py` | 添加工具说明 |
| 修改 | `agent_backend/agent/state.py` | 新增 scheduler_results |
| 修改 | `agent_backend/agent/nodes.py` | 添加结果处理逻辑 |
| 修改 | `agent_backend/agent/stream.py` | 添加 schedule_task 状态消息 |
| 新建 | `agent_backend/api/v1/scheduler.py` | REST API 端点 |
| 修改 | `agent_backend/api/routes.py` | 注册 scheduler_router |

---

## 六、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| SQLite 并发写入冲突 | 低 | 中 | APScheduler 保证单进程，WAL 模式支持并发读写 |
| LLM 生成 SQL 不可靠 | 中 | 中 | 创建时验证+缓存，支持 update 重新生成 |
| 任务执行超时 | 低 | 中 | 单任务超时60秒，超时自动取消 |
| 内存任务状态与DB不一致 | 低 | 中 | 所有变更同时更新DB和Scheduler，启动时从DB恢复 |
| 业务库schema变化导致SQL失效 | 中 | 中 | 执行失败自动记录error，支持手动update重新生成SQL |
