# 智能体定时任务调度系统 — 最终实施计划

## 一、总体架构

基于 APScheduler 3.x AsyncIOScheduler，任务定义存储在 SQLite 数据库（与聊天历史共存），使用 MemoryJobStore + DB 恢复策略，通过 `schedule_task` Agent Tool 支持聊天创建任务。

## 二、实施任务清单

### Task 1: 依赖与数据模型

#### 1.1 更新 requirements.txt
- 新增 `APScheduler>=3.10,<4.0`

#### 1.2 在 db/models.py 中新增 ORM 模型
- `AgentTask` 模型（对应 agent_task 表）
- `AgentTaskResult` 模型（对应 agent_task_result 表）
- 字段设计保持 spec 中的定义，但使用 SQLAlchemy Column 声明
- 利用现有 `init_db()` → `Base.metadata.create_all` 自动建表，无需迁移脚本

**AgentTask 字段**：
```
id: BigInteger, PK, autoincrement
task_id: String(64), NOT NULL, UNIQUE, INDEX
agent_name: String(128), NOT NULL, INDEX
task_name: String(256), NOT NULL
task_type: String(32), NOT NULL, default='interval'
task_config: Text (JSON: interval_seconds / cron_expr / run_date)
sql_template: Text (预定义SQL模板)
description: Text (自然语言描述)
status: String(16), NOT NULL, default='active', INDEX
last_run_at: DateTime (nullable)
next_run_at: DateTime (nullable)
created_by: String(64), default='system'
created_at: DateTime, NOT NULL, default=now
updated_at: DateTime, NOT NULL, default=now, onupdate=now
```

**AgentTaskResult 字段**：
```
id: BigInteger, PK, autoincrement
task_id: String(64), NOT NULL, INDEX
agent_name: String(128), NOT NULL, INDEX
run_at: DateTime, NOT NULL, INDEX
status: String(16), NOT NULL, default='success'
result_data: Text (JSON)
result_summary: Text
error_message: Text
duration_ms: Integer
created_at: DateTime, NOT NULL, default=now
```

### Task 2: 调度器核心模块

#### 2.1 创建 agent_backend/scheduler/__init__.py
- 导出 `SchedulerManager`、`get_scheduler_manager`

#### 2.2 创建 agent_backend/scheduler/manager.py
- `SchedulerManager` 类（单例模式，类似 ConnectionManager）
- 核心方法：
  - `start()`: 初始化 AsyncIOScheduler → 从 DB 恢复活跃任务 → 加载 YAML 默认任务 → 启动调度器
  - `shutdown()`: 关闭调度器（wait=True, timeout=5s）
  - `add_task(task_def)`: 写入 DB → 注册到 Scheduler → 返回 task_id
  - `remove_task(task_id)`: 从 Scheduler 移除 → 更新 DB status=completed
  - `pause_task(task_id)`: 暂停 Scheduler 中的 job → 更新 DB status=paused
  - `resume_task(task_id)`: 恢复 Scheduler 中的 job → 更新 DB status=active
  - `get_tasks()`: 查询 DB 返回所有任务列表
  - `get_task(task_id)`: 查询单个任务
  - `get_task_results(task_id, limit)`: 查询任务执行结果
  - `run_task_now(task_id)`: 手动触发一次任务执行
  - `_load_default_tasks()`: 解析 scheduled_tasks.yaml，与 DB 对比，仅新增不存在的
  - `_recover_tasks_from_db()`: 从 DB 读取 status=active 的任务，注册到 Scheduler
  - `_register_task_to_scheduler(task)`: 根据 task_type 创建对应 trigger 并添加 job
  - `_cleanup_old_results()`: 清理超过保留期限的旧结果（默认7天）

- 使用 MemoryJobStore（默认），不使用 SQLAlchemy jobstore
- Scheduler 实例存储在 `app.state.scheduler` 上
- 定时任务回调函数为 `TaskExecutor.execute_task(task_id)`

#### 2.3 创建 agent_backend/scheduler/executor.py
- `TaskExecutor` 类
- `async execute_task(task_id)` 方法：
  1. 从 DB 读取任务定义
  2. 记录开始时间
  3. 判断任务类型：
     - 有 `sql_template` → `await asyncio.to_thread(self._execute_template_task, task)`
     - 无 `sql_template` → `await asyncio.to_thread(self._execute_dynamic_task, task)`
  4. 生成结果摘要（result_summary）
  5. 写入 `agent_task_result` 表
  6. 更新 `agent_task` 的 last_run_at / next_run_at
  7. 异常捕获 → 写入 error 记录

- `_execute_template_task(task)`: 同步方法
  - 直接执行 `task.sql_template`
  - 使用 `execute_sql(sql=task.sql_template, params={}, database_url=db_url)`

- `_execute_dynamic_task(task)`: 同步方法
  - 调用 `get_sql_llm()` 根据 description 生成 SQL
  - 安全校验（validate_sql_basic + enforce_deny_select_columns）
  - 执行 SQL

- `_generate_summary(rows)`: 从查询结果生成简要摘要文本
- 使用 `asyncio.to_thread()` 将同步执行包装为异步，避免阻塞事件循环
- 数据库连接使用专用 session_id = `"__scheduler__"` 复用 ConnectionManager

### Task 3: 默认任务配置文件

#### 3.1 创建 agent_backend/configs/scheduled_tasks.yaml
- 与 spec 中定义一致，包含3个默认任务：
  - online_client_count: 每隔30分钟统计在线客户端数量（有 sql_template）
  - asset_change_detection: 每隔30分钟统计新增资产变更设备（有 sql_template）
  - usb_log_stats: 每隔2小时统计USB日志情况（无 sql_template，动态任务）

### Task 4: 集成到 FastAPI 生命周期

#### 4.1 修改 agent_backend/main.py
- 在 lifespan 启动阶段：
  ```python
  from agent_backend.scheduler import get_scheduler_manager
  scheduler = get_scheduler_manager()
  await scheduler.start()
  ```
- 在 lifespan 关闭阶段（在 ConnectionManager.shutdown() 之前）：
  ```python
  scheduler = get_scheduler_manager()
  await scheduler.shutdown()
  ```

#### 4.2 修改 docker-compose.yml
- 新增环境变量 `SCHEDULER_ENABLED`（默认 true）
- 新增环境变量 `SCHEDULED_TASKS_CONFIG_PATH`（默认 /app/configs/scheduled_tasks.yaml）
- configs 目录已挂载，无需额外配置

### Task 5: schedule_task Agent Tool

#### 5.1 创建 agent_backend/agent/tools/scheduler_tool.py
- `ScheduleTaskInput(BaseModel)` 入参模型：
  - `action`: Literal["create", "list", "pause", "resume", "delete"]
  - `task_name`: Optional[str] — 任务名称（create 时必填）
  - `interval_seconds`: Optional[int] — 间隔秒数（create + interval 类型）
  - `cron_expr`: Optional[str] — cron 表达式（create + cron 类型）
  - `description`: Optional[str] — 任务描述（create 时必填）
  - `sql_template`: Optional[str] — SQL模板（create 时可选）
  - `task_id`: Optional[str] — 任务ID（pause/resume/delete 时必填）

- `schedule_task` 函数（@tool 装饰器）：
  - create: 调用 `scheduler.add_task()` → 返回确认信息（含 task_id）
  - list: 调用 `scheduler.get_tasks()` → 返回任务列表
  - pause: 调用 `scheduler.pause_task()` → 返回确认
  - resume: 调用 `scheduler.resume_task()` → 返回确认
  - delete: 调用 `scheduler.remove_task()` → 返回确认
  - 返回 JSON 字符串，遵循现有工具模式

#### 5.2 修改 agent_backend/agent/tools/__init__.py
- 导入 `schedule_task`
- 添加到 `ALL_TOOLS` 列表

#### 5.3 修改 agent_backend/agent/prompts.py
- 在 SYSTEM_PROMPT 中添加第9个工具说明：
  ```
  9. **schedule_task** - 创建和管理定时任务
     - 适用场景：用户要求"每隔N分钟/小时"、"定时"、"定期"执行某个查询或统计任务
     - 支持操作：create(创建)、list(查看)、pause(暂停)、resume(恢复)、delete(删除)
     - 示例问题："每隔30分钟记录一下在线客户端数量"、"查看当前有哪些定时任务"、"暂停统计在线客户端的任务"
     - 重要：仅当用户明确要求"定时"或"定期"执行时才使用此工具，普通查询仍用sql_query
  ```
- 在决策规则中添加：
  ```
  - 如果用户要求"每隔"、"定时"、"定期"、"每天"、"每小时"等周期性执行任务，使用 schedule_task 创建定时任务
  - 如果用户只是单次查询，不要创建定时任务，使用 sql_query 即可
  ```

#### 5.4 修改 agent_backend/agent/state.py
- AgentState 新增 `scheduler_results: list[dict]` 字段

#### 5.5 修改 agent_backend/agent/nodes.py
- `init_node`: 初始化 `scheduler_results: []`
- `tool_result_node`: 新增 `elif tool_name == "schedule_task"` 分支
  - 解析 JSON 结果，追加到 `scheduler_results`
  - 与其他工具结果处理模式一致

### Task 6: 任务管理 REST API

#### 6.1 创建 agent_backend/api/v1/scheduler.py
- `GET /scheduler/tasks` — 获取任务列表
- `GET /scheduler/tasks/{task_id}/results` — 获取任务执行结果（支持 limit 参数）
- `POST /scheduler/tasks/{task_id}/run` — 手动触发任务
- `PUT /scheduler/tasks/{task_id}/pause` — 暂停任务
- `PUT /scheduler/tasks/{task_id}/resume` — 恢复任务
- `DELETE /scheduler/tasks/{task_id}` — 删除任务

#### 6.2 修改 agent_backend/api/routes.py
- 导入并注册 `scheduler_router`

### Task 7: 验证测试

#### 7.1 启动验证
- 应用启动时调度器正常初始化
- 默认任务从配置文件加载到数据库
- agent_task 和 agent_task_result 表自动创建

#### 7.2 定时执行验证
- 模板任务按配置间隔执行，结果写入 agent_task_result 表
- 动态任务（usb_log_stats）通过 LLM 生成 SQL 并执行

#### 7.3 聊天创建验证
- 通过对话"每隔30分钟记录在线客户端数量"创建定时任务
- LLM 正确调用 schedule_task Tool

#### 7.4 API 验证
- 任务管理 API 端点功能正常

#### 7.5 恢复验证
- 应用重启后任务从数据库自动恢复并继续调度

#### 7.6 异常隔离验证
- 任务执行异常不影响其他任务和调度器

## 三、文件变更清单

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| 修改 | `requirements.txt` | 新增 APScheduler>=3.10,<4.0 |
| 修改 | `agent_backend/db/models.py` | 新增 AgentTask、AgentTaskResult ORM 模型 |
| 新建 | `agent_backend/scheduler/__init__.py` | 模块入口，导出核心接口 |
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
| 新建 | `agent_backend/api/v1/scheduler.py` | REST API 端点 |
| 修改 | `agent_backend/api/routes.py` | 注册 scheduler_router |

## 四、任务依赖关系

```
Task 1 (依赖+模型)
  ├── Task 2 (调度器核心) ← 依赖 Task 1
  ├── Task 3 (配置文件) ← 独立
  ├── Task 5 (Agent Tool) ← 依赖 Task 2
  └── Task 6 (REST API) ← 依赖 Task 2

Task 4 (生命周期集成) ← 依赖 Task 2, Task 3

Task 7 (验证) ← 依赖 Task 4, Task 5, Task 6

Task 5 和 Task 6 可并行执行
```

## 五、关键设计决策总结

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 任务表存储位置 | SQLite | 与聊天历史共存，遵循现有模式，不侵入业务库 |
| APScheduler jobstore | MemoryJobStore | 避免与异步引擎冲突，DB 恢复策略更可控 |
| 建表方式 | ORM + create_all | 与现有 Conversation/Message 一致，无需迁移工具 |
| 同步代码处理 | asyncio.to_thread | 避免阻塞事件循环，保持 FastAPI 响应性 |
| 调度器数据库连接 | 专用 session_id | 复用 ConnectionManager，避免频繁创建连接 |
| 结果清理 | 默认7天保留 | 防止表膨胀，可按任务配置 |
