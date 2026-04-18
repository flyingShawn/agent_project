# 智能体定时任务调度系统 — 架构方案审查与优化

## 一、当前架构理解（验证后）

### 技术栈（已验证）
- **后端**: FastAPI + LangGraph (StateGraph) + SQLAlchemy (async aiosqlite + sync pymysql)
- **前端**: Vue 3 + Vite + TailwindCSS
- **向量库**: Qdrant + FastEmbed
- **LLM**: LangChain ChatOpenAI（兼容 OpenAI 协议）
- **部署**: Docker Compose (backend + frontend + qdrant)

### 关键代码路径（已验证）
```
main.py lifespan:
  启动 → init_db() (SQLite create_all)
  关闭 → get_connection_manager().shutdown()

db/chat_history.py:
  engine = create_async_engine("sqlite+aiosqlite:///...", connect_args={"check_same_thread": False})
  async_session = async_sessionmaker(engine, class_=AsyncSession)
  ❗ 未启用 WAL 模式

sql_agent/executor.py:
  execute_sql() → 同步函数，使用同步 SQLAlchemy 引擎连接 MySQL
  支持 session_id 复用 ConnectionManager 连接

sql_agent/connection_manager.py:
  单例模式，60分钟未使用自动清理连接
  后台守护线程每60秒扫描过期连接

llm/factory.py:
  get_sql_llm() → get_llm(streaming=False, temperature=0.0) → 同步阻塞

agent/tools/__init__.py:
  ALL_TOOLS = [sql_query, rag_search, metadata_query, get_current_time,
               calculator, generate_chart, export_data, web_search]
  每个工具使用 @tool(args_schema=XXXInput) 装饰器，返回 JSON 字符串

agent/state.py:
  AgentState(TypedDict, total=False) — 每种工具有独立的结果累积列表

agent/nodes.py:
  tool_result_node — 按工具名分类收集结果，每种工具有独立的处理分支

docker-compose.yml:
  CHAT_DB_PATH=/app/data/chat_history.db (chat_data named volume)
  configs/ 目录 :ro 只读挂载
  AGENT_NAME=desk-agent
```

---

## 二、原方案问题分析

### 🔴 严重问题1：async/sync 混合模式描述错误

**原方案描述**：
> TaskExecutor.execute_task(task_id) → asyncio.to_thread(同步执行)

**问题**：任务执行涉及两种数据库操作：
1. **MySQL 查询**：`execute_sql()` 是同步函数 → 需要 `asyncio.to_thread` 包装
2. **SQLite 结果写入**：`agent_task_result` 表使用 aiosqlite 异步引擎 → 必须在 async 上下文中 `await`

原方案将整个执行过程包装在 `asyncio.to_thread` 中是**错误的**——在线程中无法使用 aiosqlite 的 async session（asyncio 事件循环是线程局部的）。

**正确流程应为**：
```
APScheduler async 回调
  ├── rows = await asyncio.to_thread(execute_sql, sql=..., session_id="__scheduler__")  # MySQL 同步查询
  ├── async with async_session() as session:  # SQLite 异步写入
  │   ├── session.execute(insert AgentTaskResult)
  │   ├── session.execute(update AgentTask last_run_at/next_run_at)
  │   └── await session.commit()
  └── 异常捕获 → 同样异步写入 error 记录
```

### 🔴 严重问题2：`schedule_task` 工具设计过于复杂

**原方案设计**：6个 action（create/list/pause/resume/delete/update）合并在一个 Tool 中。

**问题**：
1. **LLM 选择困难**：现有8个工具都是单一职责，LLM 能准确判断何时调用。6个 action 的工具让 LLM 需要同时决定"用不用"和"用哪个 action"，增加出错概率
2. **入参模型混乱**：不同 action 需要不同参数（create 需要 task_name/interval/description，pause 只需要 task_id），全部放在一个 BaseModel 中导致大量 Optional 字段，LLM 容易混淆
3. **与现有模式不一致**：所有现有工具都是单一职责，一个 Tool 做一件事

**优化建议**：拆分为2个工具：
- `schedule_task`：创建定时任务（用户最常用的操作，从聊天创建）
- `manage_scheduled_task`：管理已有任务（pause/resume/delete/update/list）

### 🟡 问题3：SQLite 未启用 WAL 模式

**现状**：`chat_history.py` 的 `create_async_engine` 未配置 WAL 模式。

**风险**：调度器定时写入 `agent_task_result` 表时，SQLite 默认的 journal 模式会在写入时锁定整个数据库文件，阻塞 HTTP 请求对 `conversations`/`messages` 表的读取。

**解决方案**：在 `init_db()` 中启用 WAL 模式：
```python
async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)
```

WAL 模式允许并发读写，写操作不阻塞读操作，适合调度器场景。

### 🟡 问题4：`__scheduler__` session_id 与连接过期冲突

**原方案**：使用固定 `session_id = "__scheduler__"` 复用 ConnectionManager 连接。

**问题**：`ConnectionManager` 有60分钟自动过期清理机制。如果任务间隔超过60分钟（如"每隔2小时统计USB日志"），连接会被清理。下次执行时虽然 `get_or_create_connection` 会自动重建，但这意味着 `__scheduler__` 的"复用"优势在长间隔任务上不存在。

**优化建议**：不需要特殊处理，`ConnectionManager.get_or_create_connection()` 本身已支持自动重建失效连接。但应在 `SchedulerManager` 中维护对 `ConnectionManager` 的引用，而非依赖全局单例获取。

### 🟡 问题5：`agent_name` 来源不明确

**原方案**：`agent_task` 表有 `agent_name` 字段，`scheduled_tasks.yaml` 硬编码 `agent_name: desk-agent`。

**问题**：
1. `schedule_task` 工具的入参模型没有 `agent_name` 字段，LLM 无法指定
2. YAML 配置中硬编码了 `agent_name`，但 docker-compose 已有 `AGENT_NAME` 环境变量
3. 应统一从 `os.environ.get("AGENT_NAME", "desk-agent")` 获取

**优化建议**：`agent_name` 不应出现在工具入参或 YAML 配置中，应由代码自动从环境变量获取。

### 🟡 问题6：任务执行结果大小未控制

**原方案**：`result_data TEXT` 存储执行结果 JSON，无大小限制。

**风险**：SQL 查询可能返回大量数据（如全表扫描），`result_data` 可能达到数 MB，导致 SQLite 数据库膨胀。

**优化建议**：
1. 任务执行时强制 `LIMIT`（复用 `execute_sql` 的 `max_rows` 参数，默认500行）
2. `result_data` 只存储摘要信息（行数、关键指标），完整数据可选存文件
3. 或添加 `result_data_max_size` 配置项，超过阈值时截断

### 🟡 问题7：`result_summary` 字段生成方式未说明

**原方案**：`agent_task_result` 表有 `result_summary TEXT` 字段，但未说明如何生成。

**问题**：如果用 LLM 生成摘要，每次任务执行都要额外调用 LLM，增加开销和延迟。如果用简单规则（如"查询返回 N 行数据"），则价值有限。

**优化建议**：
- 第一版用简单规则生成摘要（如"查询返回 N 行，首行数据: ..."）
- 后续可扩展为 LLM 生成摘要（作为可选功能）

### 🟡 问题8：缺少 SQL 安全校验的完整流程

**原方案**：提到"安全校验 → 试执行验证"，但未详细说明。

**问题**：
1. 创建任务时生成的 SQL 必须经过 `validate_sql_basic()` 和 `enforce_deny_select_columns()` 校验
2. 试执行验证需要调用 `execute_sql()`，但此时没有 `session_id`（不在用户会话上下文中）
3. 配置文件中的 `sql_template` 是否也需要校验？（建议启动时校验，失败则跳过该任务并记录警告）

**优化建议**：
- 创建任务时：LLM 生成 SQL → `validate_sql_basic()` → `enforce_deny_select_columns()` → `execute_sql(max_rows=1)` 试执行验证 → 通过后存储
- 启动加载配置时：校验 YAML 中的 `sql_template`，失败则跳过并记录 warning

### 🟢 小问题9：REST API 设计可能过早

**原方案**：设计了8个 REST API 端点。

**分析**：用户原始需求没有提到 REST API，聊天管理已足够。但 REST API 对以下场景有价值：
- 外部系统读取任务结果（用户提到"由此表再推送出去消息"）
- 前端展示任务管理页面（未来需求）

**建议**：保留 REST API 设计，但优先级降低。第一版只实现核心端点：
- `GET /api/v1/scheduler/tasks` — 任务列表
- `GET /api/v1/scheduler/tasks/{task_id}/results` — 任务结果
- `POST /api/v1/scheduler/tasks/{task_id}/run` — 手动触发

其余端点（pause/resume/delete）后续按需添加。

### 🟢 小问题10：缺少调度器健康检查

**建议**：在现有 `health.py` 中添加调度器状态信息：
```python
{
    "scheduler": {
        "running": True,
        "active_tasks": 3,
        "total_executions_today": 15
    }
}
```

---

## 三、优化方案设计

### 3.1 模块拆分（调整后）

```
agent_backend/scheduler/           # 新增模块
├── __init__.py                    # 导出 SchedulerManager, get_scheduler_manager
├── manager.py                     # SchedulerManager 单例（调度器生命周期+任务CRUD+配置加载）
├── executor.py                    # TaskExecutor（任务执行+结果写入，正确处理async/sync）
└── models.py                      # AgentTask, AgentTaskResult ORM 模型（从 db/models.py 独立出来）

agent_backend/agent/tools/
├── scheduler_tool.py              # 新增：schedule_task（创建任务）
└── scheduler_manage_tool.py       # 新增：manage_scheduled_task（管理任务）

agent_backend/configs/scheduled_tasks.yaml   # 新增：默认任务配置（不含 agent_name）
agent_backend/api/v1/scheduler.py            # 新增：REST API（精简版）
```

**调整说明**：
1. ORM 模型独立为 `scheduler/models.py`，避免 `db/models.py` 膨胀。但需要确保 `scheduler/models.py` 中的模型继承自 `db/chat_history.py` 的 `Base`，这样 `init_db()` 的 `create_all` 才能自动建表
2. 工具拆分为2个，降低 LLM 选择复杂度
3. YAML 配置移除 `agent_name`，由代码从环境变量获取

### 3.2 数据流/调用链变化（修正后）

```
应用启动
  ├── init_db()
  │   ├── PRAGMA journal_mode=WAL  ← 新增：启用 WAL 模式
  │   └── Base.metadata.create_all（自动创建所有表，含 agent_task / agent_task_result）
  ├── SchedulerManager.start()
  │   ├── 从 agent_task 表读取 status=active 的任务 → 注册到 APScheduler
  │   ├── 从 scheduled_tasks.yaml 读取默认任务 → 校验 sql_template → 与 DB 对比 → 仅新增不存在的
  │   └── 启动 AsyncIOScheduler
  └── 调度器运行中

定时触发（核心修正）
  ├── APScheduler 触发 async 回调
  ├── TaskExecutor.execute_task(task_id)
  │   ├── 1. 从 SQLite 异步读取任务信息（agent_task 表）
  │   ├── 2. await asyncio.to_thread(execute_sql, sql=task.sql_template, session_id="__scheduler__")
  │   │   └── 在线程池中执行 MySQL 同步查询
  │   ├── 3. 异步写入结果到 agent_task_result 表
  │   │   ├── result_data: 截断到 max_result_size（默认 64KB）
  │   │   ├── result_summary: 简单规则生成（"查询返回 N 行"）
  │   │   └── duration_ms: 执行耗时
  │   ├── 4. 异步更新 agent_task 的 last_run_at / next_run_at
  │   └── 5. 异常 → 异步写入 error 记录到 agent_task_result
  └── 超时控制：单任务 60 秒，asyncio.wait_for 包装

聊天创建任务
  ├── 用户："每隔30分钟记录在线客户端数量"
  ├── LLM → schedule_task Tool
  │   ├── 若无 sql_template → 调 get_sql_llm 生成 SQL
  │   ├── validate_sql_basic() 安全校验
  │   ├── enforce_deny_select_columns() 敏感列校验
  │   ├── execute_sql(max_rows=1) 试执行验证
  │   ├── 验证通过 → SchedulerManager.add_task()
  │   │   ├── 写入 agent_task 表（agent_name 从环境变量获取）
  │   │   └── 注册到 APScheduler
  │   └── 返回确认信息（含 task_id 和生成的 SQL）
  └── LLM 向用户确认任务创建成功

应用关闭
  ├── SchedulerManager.shutdown()
  │   ├── 关闭 APScheduler（等待当前执行中的任务完成）
  │   └── 关闭 __scheduler__ 连接
  └── get_connection_manager().shutdown()
```

### 3.3 agent_task 表设计（微调后）

```sql
-- 存储在 SQLite（data/chat_history.db），与 Conversation/Message 共存

CREATE TABLE agent_task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id VARCHAR(64) NOT NULL UNIQUE,
    agent_name VARCHAR(128) NOT NULL,           -- 从 AGENT_NAME 环境变量自动填充
    task_name VARCHAR(256) NOT NULL,
    task_type VARCHAR(32) NOT NULL DEFAULT 'interval',  -- interval/cron
    task_config TEXT NOT NULL,                   -- JSON: {"interval_seconds":1800} 或 {"cron_expr":"0 */2 * * *"}
    sql_template TEXT NOT NULL,                  -- 统一存储最终执行的 SQL
    description TEXT,                            -- 自然语言描述（动态任务原始描述）
    status VARCHAR(16) NOT NULL DEFAULT 'active',  -- active/paused/completed/error
    last_run_at REAL,
    next_run_at REAL,
    created_by VARCHAR(64) DEFAULT 'system',     -- system/chat
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE agent_task_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id VARCHAR(64) NOT NULL,
    agent_name VARCHAR(128) NOT NULL,
    run_at REAL NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'success',  -- success/error
    result_data TEXT,                            -- 截断到 max_result_size
    result_summary TEXT,                         -- 简单规则生成
    row_count INTEGER,                           -- ← 新增：查询返回行数
    error_message TEXT,
    duration_ms INTEGER,
    created_at REAL NOT NULL
);

-- 索引同原方案
```

**微调点**：
1. `task_config` 改为 `NOT NULL`（必须有配置）
2. `sql_template` 改为 `NOT NULL`（创建时必须生成/提供）
3. 新增 `row_count` 字段，便于快速查看查询返回行数，无需解析 `result_data`
4. 移除 `task_type` 的 `date` 选项（一次性任务用 cron 表达式即可，无需单独类型）

### 3.4 默认任务配置文件（调整后）

```yaml
# agent_backend/configs/scheduled_tasks.yaml
# agent_name 从 AGENT_NAME 环境变量自动获取，不再在此配置

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

### 3.5 Agent Tool 设计（拆分后）

#### Tool 1: `schedule_task`（创建定时任务）

```
ScheduleTaskInput:
  task_name: str                  -- 任务名称（如"统计在线客户端数量"）
  description: str                -- 自然语言描述（如"每隔30分钟统计在线客户端数量"）
  interval_seconds: int | None    -- 间隔秒数（interval 类型）
  cron_expr: str | None           -- cron 表达式（cron 类型）
  sql_template: str | None        -- 可选：直接提供 SQL，无则 LLM 生成
```

**逻辑**：
1. 验证 interval_seconds 和 cron_expr 至少提供一个
2. 若无 sql_template → 调 get_sql_llm 根据 description 生成 SQL
3. 安全校验 → 试执行验证
4. 写入 DB → 注册调度 → 返回确认

#### Tool 2: `manage_scheduled_task`（管理已有任务）

```
ManageScheduledTaskInput:
  action: Literal["list", "pause", "resume", "delete", "update"]
  task_id: str | None             -- pause/resume/delete/update 时必填
  sql_template: str | None        -- update 时可选（无则重新 LLM 生成）
  description: str | None         -- update 时可选（重新生成 SQL 的描述）
```

**逻辑**：
- `list`: 返回所有活跃任务列表
- `pause`: 暂停任务（更新 DB status + 从 APScheduler 移除）
- `resume`: 恢复任务（更新 DB status + 重新注册 APScheduler）
- `delete`: 删除任务（更新 DB status=completed + 从 APScheduler 移除）
- `update`: 更新 SQL（可选重新 LLM 生成 → 安全校验 → 更新 DB + 重注册 APScheduler）

### 3.6 AgentState 扩展

```python
# agent/state.py 新增字段
scheduler_results: list[dict]     # 定时任务操作结果累积
```

### 3.7 stream.py 扩展

在 `_TOOL_STATUS_MESSAGES` 和 `_TOOL_COMPLETE_MESSAGES` 中添加：
```python
"schedule_task": "⏰ 正在创建定时任务...",
"manage_scheduled_task": "⏰ 正在管理定时任务...",
```

### 3.8 REST API（精简版）

```
GET    /api/v1/scheduler/tasks                    -- 获取任务列表（含最近执行状态）
GET    /api/v1/scheduler/tasks/{task_id}/results   -- 获取任务执行结果（支持 limit 参数）
POST   /api/v1/scheduler/tasks/{task_id}/run       -- 手动触发一次任务
```

后续按需添加：pause/resume/delete 端点。

### 3.9 结果清理策略（同原方案，补充细节）

- 默认保留最近 7 天的执行结果
- SchedulerManager 启动时执行一次清理
- 注册一个内部清理任务，每天凌晨 3:00 执行
- 清理逻辑：`DELETE FROM agent_task_result WHERE created_at < :cutoff_timestamp`

### 3.10 任务执行超时控制

```python
async def execute_task(self, task_id: str):
    try:
        result = await asyncio.wait_for(
            self._do_execute(task_id),
            timeout=60.0  # 单任务 60 秒超时
        )
    except asyncio.TimeoutError:
        # 写入超时错误记录
        await self._write_error_result(task_id, "任务执行超时（60秒）")
```

---

## 四、可选方案对比

### 方案对比：ORM 模型放置位置

| 维度 | 方案A: 放在 db/models.py（原方案） | 方案B: 放在 scheduler/models.py（推荐） |
|------|----------------------------------|---------------------------------------|
| 内聚性 | ❌ 调度器模型与聊天模型混在一起 | ✅ 调度器模块自包含 |
| 可维护性 | ⚠️ db/models.py 会持续膨胀 | ✅ 各模块独立维护 |
| 建表兼容 | ✅ 直接继承 Base，create_all 自动建 | ✅ 同样继承 Base，只需确保 import 链正确 |
| 一致性 | ✅ 所有模型在一处 | ⚠️ 需确保 scheduler/models.py 在 init_db 前被 import |

**关键点**：方案B 需要在 `db/models.py` 或 `db/chat_history.py` 中 import `scheduler/models.py`，确保 `Base.metadata.create_all` 能发现这些模型。最简单的方式是在 `db/models.py` 末尾添加：
```python
from agent_backend.scheduler.models import AgentTask, AgentTaskResult  # noqa: F401
```

### 方案对比：schedule_task 工具拆分

| 维度 | 方案A: 单工具6 action（原方案） | 方案B: 2个工具（推荐） | 方案C: 6个独立工具 |
|------|-------------------------------|----------------------|------------------|
| LLM 准确性 | ❌ action 选择增加出错率 | ✅ 职责清晰，LLM 易判断 | ✅ 最精确 |
| 工具数量 | ✅ 1个 | ✅ 2个 | ❌ 6个，工具列表膨胀 |
| 入参简洁性 | ❌ 大量 Optional 字段 | ✅ 每个工具参数明确 | ✅ 最简洁 |
| 与现有模式一致性 | ❌ 不一致 | ✅ 基本一致 | ⚠️ 工具太多 |

---

## 五、文件变更清单（优化后）

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| 修改 | `requirements.txt` | 新增 APScheduler>=3.10,<4.0 |
| 修改 | `agent_backend/db/chat_history.py` | init_db 启用 WAL 模式 |
| 修改 | `agent_backend/db/models.py` | 末尾 import scheduler models（确保 create_all 发现） |
| 新建 | `agent_backend/scheduler/__init__.py` | 模块入口 |
| 新建 | `agent_backend/scheduler/models.py` | AgentTask、AgentTaskResult ORM 模型 |
| 新建 | `agent_backend/scheduler/manager.py` | SchedulerManager 调度器管理 |
| 新建 | `agent_backend/scheduler/executor.py` | TaskExecutor 任务执行器（正确 async/sync） |
| 新建 | `agent_backend/configs/scheduled_tasks.yaml` | 默认任务配置（不含 agent_name） |
| 修改 | `agent_backend/main.py` | lifespan 集成调度器启动/关闭 |
| 新建 | `agent_backend/agent/tools/scheduler_tool.py` | schedule_task Tool（创建任务） |
| 新建 | `agent_backend/agent/tools/scheduler_manage_tool.py` | manage_scheduled_task Tool（管理任务） |
| 修改 | `agent_backend/agent/tools/__init__.py` | 注册2个新工具 |
| 修改 | `agent_backend/agent/prompts.py` | 添加2个工具说明 |
| 修改 | `agent_backend/agent/state.py` | 新增 scheduler_results |
| 修改 | `agent_backend/agent/nodes.py` | 添加 scheduler 工具结果处理 |
| 修改 | `agent_backend/agent/stream.py` | 添加 scheduler 工具状态消息 |
| 新建 | `agent_backend/api/v1/scheduler.py` | REST API（精简版3个端点） |
| 修改 | `agent_backend/api/routes.py` | 注册 scheduler_router |
| 修改 | `docker-compose.yml` | 无需新增环境变量（AGENT_NAME 已有） |

---

## 六、风险评估（补充后）

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| SQLite 并发写入冲突 | 低 | 中 | WAL 模式 + APScheduler 单进程保证串行执行 |
| LLM 生成 SQL 不可靠 | 中 | 中 | 创建时验证+缓存，支持 update 重新生成 |
| 任务执行超时 | 低 | 中 | asyncio.wait_for 60秒超时 |
| 内存任务状态与DB不一致 | 低 | 中 | 所有变更同时更新DB和Scheduler，启动时从DB恢复 |
| 业务库 schema 变化导致 SQL 失效 | 中 | 中 | 执行失败自动记录 error，支持手动 update |
| result_data 过大导致 SQLite 膨胀 | 中 | 中 | 截断到 64KB + 7天自动清理 + row_count 快速查看 |
| scheduler models 未被 create_all 发现 | 低 | 高 | db/models.py 末尾显式 import |
| APScheduler 3.x 与 Python 3.12+ 兼容性 | 低 | 中 | 当前 Docker 用 Python 3.11，无问题；后续升级需关注 |

---

## 七、总结：原方案评分与优化要点

### 原方案优点 ✅
1. 任务表存 SQLite 的决策正确（不打破 MySQL 只读边界）
2. 创建时生成并缓存 SQL 的策略正确（避免每次执行调 LLM）
3. APScheduler 3.x AsyncIOScheduler 选型合理
4. MemoryJobStore + DB 恢复策略正确
5. 表设计基本合理，字段完整
6. 结果清理策略实用

### 原方案需修正的问题 ❌→✅
1. ❌ async/sync 混合模式描述错误 → ✅ 分步处理：to_thread 做 MySQL，async await 做 SQLite
2. ❌ 单工具6 action 设计复杂 → ✅ 拆分为2个工具
3. ❌ 未启用 SQLite WAL 模式 → ✅ init_db 中启用
4. ❌ agent_name 硬编码 → ✅ 从环境变量获取
5. ❌ result_data 无大小控制 → ✅ 截断 + row_count 字段
6. ❌ result_summary 生成方式未说明 → ✅ 简单规则生成
7. ❌ SQL 安全校验流程不完整 → ✅ 完整校验链
8. ❌ ORM 模型放置位置不够内聚 → ✅ 独立 scheduler/models.py
9. ❌ REST API 过多 → ✅ 精简为核心3个端点
10. ❌ 缺少超时控制实现细节 → ✅ asyncio.wait_for
