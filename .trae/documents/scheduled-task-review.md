# 智能体定时任务调度系统 — 方案评审与优化建议

## 一、现有方案概述

现有方案基于 APScheduler AsyncIOScheduler 实现定时任务调度，包含：
- `agent_task` + `agent_task_result` 两张数据库表（存储在业务数据库 MySQL 中）
- `agent_backend/scheduler/` 模块（manager.py / executor.py / models.py / config_loader.py）
- `scheduled_tasks.yaml` 默认任务配置文件
- `schedule_task` Agent Tool（支持 create/list/pause/resume/delete）
- REST API 端点（`/api/v1/scheduler/tasks/*`）
- APScheduler SQLAlchemy jobstore 持久化

## 二、关键问题分析

### 🔴 问题1：数据库表存放位置错误（严重）

**现有方案**：将 `agent_task` 和 `agent_task_result` 表创建在业务数据库（MySQL/PostgreSQL）中。

**问题**：
- 业务数据库是外部系统管理的，本项目**仅有只读查询权限**（只执行 SELECT）
- 在业务库中建表违反了权限边界，可能导致运维冲突
- 项目已有独立的 SQLite 数据库（`data/chat_history.db`）用于存储应用自身数据（聊天历史）
- SQLite 数据库使用 `Base.metadata.create_all` 自动建表，无需迁移工具

**优化建议**：将 `agent_task` 和 `agent_task_result` 表创建在 **SQLite 数据库**中，与 `Conversation`、`Message` 表共存，遵循现有的 `Base` + `create_all` 模式。

### 🔴 问题2：APScheduler SQLAlchemy jobstore 过度设计（严重）

**现有方案**：使用 APScheduler 的 SQLAlchemy jobstore 将任务定义持久化到数据库。

**问题**：
- APScheduler 的 SQLAlchemy jobstore 需要同步引擎，但当前 SQLite 使用异步引擎（aiosqlite）
- 配置 jobstore 需要额外创建同步引擎，增加了不必要的复杂度
- 我们已经有 `agent_task` 表存储任务定义，jobstore 的持久化与我们的表是**重复存储**
- jobstore 存储的是 APScheduler 内部格式的 job 数据，与我们的业务模型不匹配

**优化建议**：
- 使用 APScheduler 的 **MemoryJobStore**（默认）
- 启动时从 `agent_task` 表读取活跃任务，手动注册到 Scheduler
- 任务变更时同步更新数据库和 Scheduler
- 这样任务定义的"权威来源"是我们的 `agent_task` 表，而非 APScheduler 的 jobstore

### 🟡 问题3：同步/异步执行模型未对齐（中等）

**现有方案**：TaskExecutor 中直接调用 `execute_sql` 和 `get_sql_llm`。

**问题**：
- `execute_sql` 是**同步函数**（使用 SQLAlchemy 同步引擎）
- `get_sql_llm().invoke()` 也是**同步调用**
- APScheduler 的 AsyncIOScheduler 在**异步事件循环**中触发回调
- 在异步上下文中直接调用同步阻塞函数会**阻塞整个事件循环**，影响所有 HTTP 请求处理

**优化建议**：
- 在 TaskExecutor 中使用 `asyncio.to_thread()` 将同步调用包装为异步
- 或者使用 `loop.run_in_executor(None, ...)` 在线程池中执行同步代码
- 确保定时任务执行不会阻塞 FastAPI 的请求处理

### 🟡 问题4：定时任务缺少 session_id 上下文（中等）

**现有方案**：未明确说明定时任务执行 SQL 时如何获取数据库连接。

**问题**：
- 当前 `execute_sql` 支持 `session_id` 参数用于连接复用
- 定时任务不在用户会话上下文中，没有 `session_id`
- 不传 `session_id` 时会创建临时引擎连接（每次执行都新建+销毁），效率低

**优化建议**：
- 为调度器分配固定的 `session_id`，如 `"__scheduler__"`
- 复用 `ConnectionManager` 的连接管理能力
- 或者创建一个专用的调度器数据库连接（长连接），避免频繁创建/销毁

### 🟡 问题5：建表方式不符合现有模式（中等）

**现有方案**：创建 `agent_backend/scheduler/migrations/001_create_agent_task_tables.sql` DDL 脚本。

**问题**：
- 项目不使用迁移工具，没有 `migrations/` 目录
- 现有表（Conversation、Message）通过 SQLAlchemy ORM 模型 + `Base.metadata.create_all` 自动创建
- 手写 DDL 脚本与现有模式不一致，且需要额外的执行逻辑

**优化建议**：
- 在 `agent_backend/db/models.py` 中新增 `AgentTask` 和 `AgentTaskResult` ORM 模型
- 利用现有的 `init_db()` → `Base.metadata.create_all` 自动建表
- 无需单独的迁移脚本和执行逻辑

### 🟢 问题6：模块结构可简化（轻微）

**现有方案**：`scheduler/` 模块包含 `__init__.py`、`manager.py`、`executor.py`、`models.py`、`config_loader.py` 五个文件。

**问题**：
- `models.py` 定义 Pydantic 模型，但如果使用 SQLAlchemy ORM，Pydantic 模型可以精简
- `config_loader.py` 仅解析 YAML 文件，逻辑简单，可合并到 `manager.py`
- 模块间依赖关系增加了理解和维护成本

**优化建议**：
- `models.py` 保留，但主要使用 SQLAlchemy ORM 模型（放在 `db/models.py`），Pydantic 仅用于 API 请求/响应
- `config_loader.py` 合并到 `manager.py` 中作为私有方法
- 最终结构：`__init__.py`、`manager.py`、`executor.py`

### 🟢 问题7：APScheduler 版本约束（轻微）

**现有方案**：`requirements.txt` 新增 `APScheduler>=3.10`。

**问题**：
- APScheduler 4.x 是完全重写的版本，API 不兼容 3.x
- 不加版本上限可能导致意外升级到 4.x

**优化建议**：约束为 `APScheduler>=3.10,<4.0`

### 🟢 问题8：结果数据增长未控制（轻微）

**现有方案**：`agent_task_result` 表持续写入，无清理机制。

**问题**：
- 高频任务（如每30分钟）每天产生 48 条结果记录
- 长期运行后表会膨胀，影响查询性能

**优化建议**：
- 添加结果保留策略，如默认保留最近 7 天的结果
- 在 SchedulerManager 中添加定期清理逻辑
- 或在 `agent_task` 表中添加 `result_retention_days` 字段，支持按任务配置

## 三、现有方案优点确认

以下设计合理，建议保留：

1. ✅ **APScheduler AsyncIOScheduler 选型**：轻量内嵌、原生异步、动态任务支持，与当前架构匹配
2. ✅ **任务定义与结果分离**：`agent_task` + `agent_task_result` 两表设计合理
3. ✅ **模板任务 vs 动态任务**：有 `sql_template` 直接执行，无则调 LLM 生成，灵活高效
4. ✅ **YAML 配置文件**：默认任务从配置加载，方便修改
5. ✅ **schedule_task Tool 五种 action**：create/list/pause/resume/delete 覆盖完整
6. ✅ **created_by 字段**：区分 system/chat 来源
7. ✅ **异常隔离**：单任务异常不影响其他任务和调度器

## 四、架构对比：原方案 vs 优化方案

| 维度 | 原方案 | 优化方案 |
|------|--------|----------|
| 任务表存储 | 业务数据库 MySQL | SQLite（与聊天历史共存） |
| APScheduler jobstore | SQLAlchemy jobstore | MemoryJobStore + DB 恢复 |
| 建表方式 | DDL 脚本 + 手动执行 | ORM 模型 + create_all 自动建表 |
| 同步/异步处理 | 未考虑 | asyncio.to_thread 包装 |
| 数据库连接 | 未明确 | 专用 scheduler session_id |
| 模块文件数 | 5个 | 3个（合并 config_loader） |
| APScheduler 版本 | >=3.10 | >=3.10,<4.0 |
| 结果清理 | 无 | 保留策略 + 定期清理 |
| ORM 模型位置 | scheduler/models.py | db/models.py（统一管理） |

## 五、优化后的数据流

```
应用启动
  ├── init_db() → Base.metadata.create_all（自动创建 agent_task / agent_task_result 表）
  ├── SchedulerManager.start()
  │   ├── 从 agent_task 表读取 status=active 的任务
  │   ├── 从 scheduled_tasks.yaml 读取默认任务，与 DB 对比，仅新增不存在的
  │   └── 将所有活跃任务注册到 APScheduler（MemoryJobStore）
  └── 调度器开始运行

定时触发
  ├── APScheduler 触发回调（async）
  ├── TaskExecutor.execute_task()
  │   ├── asyncio.to_thread(execute_sql) 或 asyncio.to_thread(get_sql_llm + execute_sql)
  │   ├── 结果写入 agent_task_result 表（async session）
  │   └── 更新 agent_task 的 last_run_at / next_run_at
  └── 异常捕获 → 写入 error 记录

聊天创建任务
  ├── 用户："每隔30分钟记录在线客户端数量"
  ├── LLM → schedule_task Tool（action=create）
  ├── SchedulerManager.add_task()
  │   ├── 写入 agent_task 表
  │   └── 注册到 APScheduler
  └── 返回确认信息

应用关闭
  ├── SchedulerManager.shutdown()
  │   ├── 关闭 APScheduler（等待执行中任务完成）
  │   └── 关闭调度器专用数据库连接
  └── ConnectionManager.shutdown()
```

## 六、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| SQLite 并发写入冲突 | 低 | 中 | APScheduler 保证单进程，WAL 模式支持并发读写 |
| LLM 不可用导致动态任务失败 | 中 | 低 | 记录错误，不影响其他任务，下次调度重试 |
| 任务执行超时 | 低 | 中 | 设置单任务执行超时（如60秒），超时自动取消 |
| 内存中任务状态与 DB 不一致 | 低 | 中 | 所有变更操作同时更新 DB 和 Scheduler，启动时从 DB 恢复 |
