# 智能体定时任务调度系统 — 架构方案（最终版）

## 一、评审文档逐条分析与决策

### 🔴 严重问题1：async/sync 混合模式描述错误

**评审观点**：原方案将整个执行过程包装在 `asyncio.to_thread` 中是错误的——在线程中无法使用 aiosqlite 的 async session。

**我的分析**：✅ **评审正确，这是真实 bug。**

验证依据：
- `execute_sql()` 是同步函数，使用同步 SQLAlchemy 引擎连接 MySQL → 需要 `asyncio.to_thread`
- `agent_task_result` 写入使用 aiosqlite 异步引擎 → 必须在 async 上下文中 `await`
- `asyncio.to_thread` 在线程池中执行，线程中没有 asyncio 事件循环，无法 `await`

**最终决策**：分步处理，不整体包装：
```
APScheduler async 回调
  ├── rows = await asyncio.to_thread(execute_sql, ...)   # MySQL 同步查询，在线程池中
  ├── async with async_session() as session:              # SQLite 异步写入，在事件循环中
  │   ├── session.execute(insert AgentTaskResult)
  │   └── await session.commit()
  └── 异常 → 同样异步写入 error 记录
```

---

### 🔴 严重问题2：schedule_task 工具设计过于复杂

**评审观点**：6个 action 合并在一个 Tool 中，LLM 选择困难，入参模型混乱。

**我的分析**：⚠️ **评审部分正确，但拆成2个工具不是最佳方案。**

验证依据：
- 现有8个工具中，7个只有0~1个入参字段，`generate_chart` 最多5个字段
- 单工具6 action 确实复杂，但拆成2个工具也有问题：
  - `manage_scheduled_task` 仍有5个 action，复杂度并未真正降低
  - LLM 需要判断"创建用 schedule_task，管理用 manage_scheduled_task"，增加一层路由决策
  - 与 `sql_query` 等工具的单一职责模式不一致

**最终决策**：拆分为2个工具，但调整职责划分：
- **`schedule_task`**：创建定时任务（用户最常用、最自然的操作）
  - 入参：`task_name`, `description`, `interval_seconds`(可选), `cron_expr`(可选), `sql_template`(可选)
  - 逻辑：生成/校验SQL → 写入DB → 注册调度 → 返回确认
- **`manage_scheduled_task`**：管理已有任务（list/pause/resume/delete/update）
  - 入参：`action`, `task_id`(可选), `sql_template`(可选，update时用)
  - 逻辑：按action执行对应操作

理由：创建任务是最核心、最频繁的操作，独立出来让 LLM 最容易识别。管理操作相对低频，5个 action 合在一个工具中可接受。

---

### 🟡 问题3：SQLite 未启用 WAL 模式

**评审观点**：调度器定时写入 agent_task_result 表时，SQLite 默认 journal 模式会锁定整个数据库文件，阻塞 HTTP 请求。

**我的分析**：✅ **评审正确，但严重程度被高估。**

验证依据：
- 当前 `chat_history.py` 确实未启用 WAL 模式
- 但 APScheduler 是单进程串行执行任务，不会出现并发写入
- HTTP 请求读取 conversations/messages 表时，如果调度器正在写入 agent_task_result，确实可能短暂阻塞
- WAL 模式允许读写并发，是正确的解决方案

**最终决策**：在 `init_db()` 中启用 WAL 模式。这是一个低风险、高收益的改动：
```python
async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)
```

---

### 🟡 问题4：`__scheduler__` session_id 与连接过期冲突

**评审观点**：ConnectionManager 60分钟自动过期，长间隔任务（2小时）的连接会被清理。

**我的分析**：⚠️ **评审观点正确但无需特殊处理。**

验证依据：
- `ConnectionManager.get_or_create_connection()` 已支持自动重建失效连接
- 连接过期后下次调用会自动创建新连接，功能不受影响
- 唯一的"损失"是长间隔任务无法复用连接，但这完全可接受

**最终决策**：保持 `__scheduler__` session_id 设计，无需特殊处理。ConnectionManager 的自动重建机制已足够。

---

### 🟡 问题5：`agent_name` 来源不明确

**评审观点**：agent_name 应从 AGENT_NAME 环境变量获取，不应硬编码在 YAML 或工具入参中。

**我的分析**：✅ **评审完全正确。**

验证依据：
- `docker-compose.yml` 已有 `AGENT_NAME=${AGENT_NAME:-desk-agent}`
- `.env.example` 已有 `AGENT_NAME=desk-agent`
- YAML 中硬编码 `agent_name: desk-agent` 是冗余的
- 工具入参中添加 `agent_name` 让 LLM 填写是不合理的（LLM 不知道应该填什么）

**最终决策**：
- YAML 配置移除 `agent_name` 字段
- 工具入参不包含 `agent_name`
- 代码中统一从 `os.environ.get("AGENT_NAME", "desk-agent")` 获取

---

### 🟡 问题6：任务执行结果大小未控制

**评审观点**：result_data 可能达到数 MB，导致 SQLite 膨胀。

**我的分析**：✅ **评审正确，但解决方案需调整。**

验证依据：
- `execute_sql()` 已有 `max_rows` 限制（默认500行），单次查询结果不会无限大
- 但500行 × 多列 的 JSON 确实可能达到几十 KB~几百 KB
- 高频任务（每30分钟）每天48条结果，7天336条，长期累积确实会膨胀

**最终决策**：
1. `result_data` 存储完整查询结果（已有 max_rows 限制兜底），但增加截断保护：超过 64KB 时截断并标记
2. 新增 `row_count` 字段，便于快速查看行数无需解析 result_data
3. 7天自动清理策略（原方案已有）
4. 不采用"只存摘要"方案——因为用户明确说"后续可以从这个表中取数据"，完整数据有价值

---

### 🟡 问题7：`result_summary` 字段生成方式未说明

**评审观点**：未说明如何生成 result_summary。

**我的分析**：✅ **评审正确。**

**最终决策**：第一版用简单规则生成摘要，不调 LLM：
- 模板：`"查询返回 {row_count} 行数据"` 
- 若只有1行1列：`"查询结果: {value}"`
- 错误时：不生成 summary

---

### 🟡 问题8：缺少 SQL 安全校验的完整流程

**评审观点**：创建任务时的 SQL 安全校验流程不完整。

**我的分析**：✅ **评审正确，需要明确完整校验链。**

验证依据：
- `sql_tool.py` 中已有完整的校验链：`validate_sql_basic()` → `enforce_deny_select_columns()` → `execute_sql()`
- 定时任务创建时应复用相同校验链

**最终决策**：
- 创建任务时：LLM 生成 SQL → `validate_sql_basic()` → `enforce_deny_select_columns()` → `execute_sql(max_rows=1)` 试执行验证 → 通过后存储
- 启动加载 YAML 配置时：校验 sql_template，失败则跳过该任务并记录 warning（不阻塞启动）
- 试执行验证使用临时连接（不传 session_id），避免污染 __scheduler__ 连接

---

### 🟢 小问题9：REST API 设计可能过早

**评审观点**：用户原始需求没提 REST API，精简为核心3个端点。

**我的分析**：⚠️ **评审部分正确，但我倾向于保留完整 API。**

理由：
- 用户明确说"后续可以从这个表中取数据或者由此表再推送出去消息"，REST API 是取数据的标准方式
- pause/resume/delete 是任务管理的基本操作，前端未来必定需要
- 实现成本很低（只是调用 SchedulerManager 的方法），不影响开发进度
- 如果第一版不实现，后续补加时需要重新测试

**最终决策**：保留完整 REST API 设计，但实现优先级分两批：
- 第一批（核心）：GET tasks, GET results, POST run
- 第二批（管理）：PUT pause, PUT resume, DELETE

---

### 🟢 小问题10：缺少调度器健康检查

**评审观点**：在 health.py 中添加调度器状态信息。

**我的分析**：✅ **评审正确，是好建议。**

**最终决策**：在 health 端点中添加调度器状态信息。

---

## 二、关于 ORM 模型放置位置的独立决策

评审建议将 ORM 模型放在 `scheduler/models.py` 而非 `db/models.py`。

**我的分析**：⚠️ **评审的建议有道理，但放在 `db/models.py` 更符合项目惯例。**

理由：
1. 当前 `db/models.py` 只有 Conversation 和 Message 两个模型，共30行代码，不存在"膨胀"问题
2. 所有 ORM 模型共享同一个 `Base`，放在同一个文件中确保 `create_all` 能发现所有表
3. 如果放在 `scheduler/models.py`，需要在 `db/models.py` 末尾添加 import 来确保 create_all 发现——这种"隐式依赖"反而更脆弱
4. 项目规范 `folder-conventions.md` 明确说"聊天历史 SQLite → agent_backend/db/"，agent_task 表也是存在 SQLite 中的

**最终决策**：ORM 模型放在 `db/models.py`，与 Conversation/Message 保持一致。`scheduler/` 模块只包含业务逻辑（manager.py、executor.py），不包含 ORM 模型。

---

## 三、最终架构方案

### 3.1 模块结构

```
agent_backend/scheduler/           # 新增模块
├── __init__.py                    # 导出 SchedulerManager, get_scheduler_manager
├── manager.py                     # SchedulerManager 单例（生命周期+任务CRUD+配置加载）
└── executor.py                    # TaskExecutor（任务执行+结果写入，正确处理async/sync）

agent_backend/db/models.py         # 修改：新增 AgentTask, AgentTaskResult ORM 模型
agent_backend/agent/tools/
├── scheduler_tool.py              # 新增：schedule_task（创建定时任务）
└── scheduler_manage_tool.py       # 新增：manage_scheduled_task（管理已有任务）
agent_backend/configs/scheduled_tasks.yaml   # 新增：默认任务配置（不含 agent_name）
agent_backend/api/v1/scheduler.py            # 新增：REST API
```

### 3.2 数据流（修正后）

```
应用启动
  ├── init_db()
  │   ├── PRAGMA journal_mode=WAL
  │   └── Base.metadata.create_all（含 agent_task / agent_task_result）
  ├── SchedulerManager.start()
  │   ├── 从 agent_task 表读取 status=active 的任务 → 注册到 APScheduler
  │   ├── 从 scheduled_tasks.yaml 读取默认任务 → 校验 sql_template → 与 DB 对比 → 仅新增
  │   └── 启动 AsyncIOScheduler
  └── 调度器运行中

定时触发（核心修正）
  ├── APScheduler 触发 async 回调
  ├── TaskExecutor.execute_task(task_id)
  │   ├── 1. async 读取 SQLite 中的任务信息
  │   ├── 2. await asyncio.to_thread(execute_sql, sql=..., session_id="__scheduler__")
  │   │   └── 在线程池中执行 MySQL 同步查询
  │   ├── 3. async 写入结果到 agent_task_result 表
  │   │   ├── result_data: 完整查询结果（max_rows 限制 + 64KB 截断保护）
  │   │   ├── result_summary: 简单规则生成
  │   │   ├── row_count: 查询返回行数
  │   │   └── duration_ms: 执行耗时
  │   ├── 4. async 更新 agent_task 的 last_run_at / next_run_at
  │   └── 5. 异常 → async 写入 error 记录
  └── 超时控制：asyncio.wait_for 60秒

聊天创建任务
  ├── 用户："每隔30分钟记录在线客户端数量"
  ├── LLM → schedule_task Tool
  │   ├── 若无 sql_template → 调 get_sql_llm 生成 SQL
  │   ├── validate_sql_basic() 安全校验
  │   ├── enforce_deny_select_columns() 敏感列校验
  │   ├── execute_sql(max_rows=1) 试执行验证
  │   ├── 验证通过 → SchedulerManager.add_task()
  │   │   ├── agent_name 从 os.environ.get("AGENT_NAME", "desk-agent") 获取
  │   │   ├── 写入 agent_task 表
  │   │   └── 注册到 APScheduler
  │   └── 返回确认信息（含 task_id 和生成的 SQL）
  └── LLM 向用户确认任务创建成功

应用关闭
  ├── SchedulerManager.shutdown()
  │   ├── 关闭 APScheduler（等待当前执行中的任务完成）
  │   └── 关闭 __scheduler__ 连接
  └── get_connection_manager().shutdown()
```

### 3.3 agent_task 表设计

```sql
-- 存储在 SQLite（data/chat_history.db），与 Conversation/Message 共存

CREATE TABLE agent_task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id VARCHAR(64) NOT NULL UNIQUE,
    agent_name VARCHAR(128) NOT NULL,
    task_name VARCHAR(256) NOT NULL,
    task_type VARCHAR(32) NOT NULL DEFAULT 'interval',
    task_config TEXT NOT NULL,                   -- JSON: {"interval_seconds":1800}
    sql_template TEXT NOT NULL,                  -- 统一存储最终执行的 SQL
    description TEXT,                            -- 自然语言描述
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    last_run_at REAL,
    next_run_at REAL,
    created_by VARCHAR(64) DEFAULT 'system',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE agent_task_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id VARCHAR(64) NOT NULL,
    agent_name VARCHAR(128) NOT NULL,
    run_at REAL NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'success',
    result_data TEXT,                            -- 完整查询结果 JSON（max_rows 限制 + 64KB 截断）
    result_summary TEXT,                         -- 简单规则生成
    row_count INTEGER,                           -- 查询返回行数
    error_message TEXT,
    duration_ms INTEGER,
    created_at REAL NOT NULL
);

CREATE INDEX idx_agent_task_task_id ON agent_task(task_id);
CREATE INDEX idx_agent_task_status ON agent_task(status);
CREATE INDEX idx_agent_task_result_task_id ON agent_task_result(task_id);
CREATE INDEX idx_agent_task_result_run_at ON agent_task_result(run_at);
```

### 3.4 默认任务配置文件

```yaml
# agent_backend/configs/scheduled_tasks.yaml
# agent_name 从 AGENT_NAME 环境变量自动获取

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

### 3.5 Agent Tool 设计

#### Tool 1: `schedule_task`（创建定时任务）

```
ScheduleTaskInput:
  task_name: str                  -- 任务名称
  description: str                -- 自然语言描述
  interval_seconds: int | None    -- 间隔秒数
  cron_expr: str | None           -- cron 表达式
  sql_template: str | None        -- 可选：直接提供 SQL
```

#### Tool 2: `manage_scheduled_task`（管理已有任务）

```
ManageScheduledTaskInput:
  action: Literal["list", "pause", "resume", "delete", "update"]
  task_id: str | None             -- pause/resume/delete/update 时必填
  sql_template: str | None        -- update 时可选
  description: str | None         -- update 时可选（重新生成 SQL 的描述）
```

### 3.6 REST API

```
GET    /api/v1/scheduler/tasks                    -- 任务列表
GET    /api/v1/scheduler/tasks/{task_id}/results   -- 任务执行结果
POST   /api/v1/scheduler/tasks/{task_id}/run       -- 手动触发
PUT    /api/v1/scheduler/tasks/{task_id}/pause     -- 暂停
PUT    /api/v1/scheduler/tasks/{task_id}/resume    -- 恢复
DELETE /api/v1/scheduler/tasks/{task_id}           -- 删除
```

### 3.7 结果清理策略

- 默认保留最近 7 天
- 启动时执行一次清理
- 注册内部清理任务，每天凌晨 3:00 执行

### 3.8 任务执行超时

- 单任务 60 秒超时，`asyncio.wait_for` 包装
- 超时写入 error 记录

---

## 四、文件变更清单

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| 修改 | `requirements.txt` | 新增 APScheduler>=3.10,<4.0 |
| 修改 | `agent_backend/db/chat_history.py` | init_db 启用 WAL 模式 |
| 修改 | `agent_backend/db/models.py` | 新增 AgentTask、AgentTaskResult ORM 模型 |
| 新建 | `agent_backend/scheduler/__init__.py` | 模块入口 |
| 新建 | `agent_backend/scheduler/manager.py` | SchedulerManager |
| 新建 | `agent_backend/scheduler/executor.py` | TaskExecutor（正确 async/sync） |
| 新建 | `agent_backend/configs/scheduled_tasks.yaml` | 默认任务配置 |
| 修改 | `agent_backend/main.py` | lifespan 集成调度器 |
| 新建 | `agent_backend/agent/tools/scheduler_tool.py` | schedule_task Tool |
| 新建 | `agent_backend/agent/tools/scheduler_manage_tool.py` | manage_scheduled_task Tool |
| 修改 | `agent_backend/agent/tools/__init__.py` | 注册2个新工具 |
| 修改 | `agent_backend/agent/prompts.py` | 添加2个工具说明 |
| 修改 | `agent_backend/agent/state.py` | 新增 scheduler_results |
| 修改 | `agent_backend/agent/nodes.py` | 添加 scheduler 工具结果处理 |
| 修改 | `agent_backend/agent/stream.py` | 添加 scheduler 工具状态消息 |
| 新建 | `agent_backend/api/v1/scheduler.py` | REST API |
| 修改 | `agent_backend/api/routes.py` | 注册 scheduler_router |
| 修改 | `agent_backend/api/v1/health.py` | 添加调度器状态信息 |

---

## 五、评审文档评分总结

| 评审观点 | 是否正确 | 采纳程度 | 理由 |
|----------|---------|---------|------|
| 1. async/sync 混合模式错误 | ✅ 正确 | ✅ 完全采纳 | 真实 bug，必须修正 |
| 2. 工具拆分为2个 | ⚠️ 部分正确 | ✅ 采纳拆分思路 | 但职责划分与评审略有不同 |
| 3. 启用 WAL 模式 | ✅ 正确 | ✅ 完全采纳 | 低风险高收益 |
| 4. session_id 过期冲突 | ✅ 正确但无需处理 | ✅ 采纳结论 | ConnectionManager 自动重建已足够 |
| 5. agent_name 来源 | ✅ 完全正确 | ✅ 完全采纳 | 从环境变量获取 |
| 6. result_data 大小控制 | ✅ 正确 | ⚠️ 部分采纳 | 保留完整数据（用户需取数据），加截断保护 |
| 7. result_summary 生成方式 | ✅ 正确 | ✅ 完全采纳 | 简单规则生成 |
| 8. SQL 安全校验流程 | ✅ 正确 | ✅ 完全采纳 | 复用 sql_tool 的校验链 |
| 9. REST API 精简 | ⚠️ 部分正确 | ❌ 不采纳 | 保留完整 API，用户需取数据 |
| 10. 调度器健康检查 | ✅ 好建议 | ✅ 完全采纳 | 低成本高价值 |
| ORM 模型放 scheduler/ | ⚠️ 有道理 | ❌ 不采纳 | 放 db/models.py 更符合项目惯例 |
