# Tasks

- [ ] Task 1: 新增依赖和数据库表
  - [ ] SubTask 1.1: 在 requirements.txt 中新增 `APScheduler>=3.10` 依赖
  - [ ] SubTask 1.2: 创建数据库建表脚本 `agent_backend/scheduler/migrations/001_create_agent_task_tables.sql`，包含 agent_task 和 agent_task_result 两张表的 DDL
  - [ ] SubTask 1.3: 在 scheduler 模块中实现自动建表逻辑（应用启动时检测表是否存在，不存在则创建）

- [ ] Task 2: 创建调度器核心模块 `agent_backend/scheduler/`
  - [ ] SubTask 2.1: 创建 `agent_backend/scheduler/__init__.py`，导出核心接口
  - [ ] SubTask 2.2: 创建 `agent_backend/scheduler/manager.py`，实现 SchedulerManager 类
    - 初始化 AsyncIOScheduler（使用 SQLAlchemy jobstore 持久化到当前数据库）
    - start() / shutdown() 生命周期方法
    - add_task() / remove_task() / pause_task() / resume_task() 任务管理方法
    - get_tasks() / get_task() 查询方法
    - 与 FastAPI app.state 绑定
  - [ ] SubTask 2.3: 创建 `agent_backend/scheduler/executor.py`，实现 TaskExecutor 类
    - execute_task() 方法：根据任务定义执行 SQL 查询
    - 模板任务：直接执行 sql_template
    - 动态任务：调用 get_sql_llm 生成 SQL → 安全校验 → 执行
    - 结果写入 agent_task_result 表
    - 异常捕获和错误记录
  - [ ] SubTask 2.4: 创建 `agent_backend/scheduler/models.py`，定义 Pydantic 模型
    - TaskDefinition: 任务定义模型
    - TaskResult: 任务执行结果模型
    - TaskCreateRequest / TaskUpdateRequest: API 请求模型

- [ ] Task 3: 创建默认任务配置文件
  - [ ] SubTask 3.1: 创建 `agent_backend/configs/scheduled_tasks.yaml`，定义默认定时任务
    - online_client_count: 每隔30分钟统计在线客户端数量
    - asset_change_detection: 每隔30分钟统计新增资产变更的设备
    - usb_log_stats: 每隔2小时统计USB日志情况
  - [ ] SubTask 3.2: 创建 `agent_backend/scheduler/config_loader.py`，实现配置文件加载逻辑
    - 解析 YAML 文件
    - 与数据库已有任务对比，仅新增不存在的任务
    - 返回 TaskDefinition 列表

- [ ] Task 4: 集成 Scheduler 到 FastAPI 应用生命周期
  - [ ] SubTask 4.1: 修改 `agent_backend/main.py`
    - 在 startup 事件中初始化 SchedulerManager：创建表 → 加载配置文件默认任务 → 恢复数据库已有任务 → 启动调度器
    - 在 shutdown 事件中关闭调度器（在现有 shutdown_event 中追加）
  - [ ] SubTask 4.2: 修改 `docker-compose.yml`
    - 新增环境变量 SCHEDULER_ENABLED（默认 true）
    - 新增环境变量 SCHEDULED_TASKS_CONFIG_PATH（默认 /app/configs/scheduled_tasks.yaml）
    - 确保 configs 目录挂载包含新配置文件

- [ ] Task 5: 创建 schedule_task Agent Tool
  - [ ] SubTask 5.1: 创建 `agent_backend/agent/tools/scheduler_tool.py`
    - 定义 ScheduleTaskInput Pydantic 模型：action(create/list/pause/resume/delete)、task_name、interval_seconds、cron_expr、description、task_id
    - 实现 schedule_task 函数，根据 action 调用 SchedulerManager 对应方法
    - create 动作：创建新任务 → 写入数据库 → 注册到调度器 → 返回确认
    - list 动作：查询所有活跃任务 → 返回列表
    - pause/resume/delete 动作：调用对应管理方法 → 返回确认
  - [ ] SubTask 5.2: 修改 `agent_backend/agent/tools/__init__.py`，导入并注册 schedule_task 到 ALL_TOOLS
  - [ ] SubTask 5.3: 修改 `agent_backend/agent/prompts.py`，在 SYSTEM_PROMPT 中添加 schedule_task 工具说明
  - [ ] SubTask 5.4: 修改 `agent_backend/agent/state.py`，AgentState 新增 `scheduler_results: list[dict]` 字段
  - [ ] SubTask 5.5: 修改 `agent_backend/agent/nodes.py`，tool_result_node 新增 schedule_task 结果处理逻辑

- [ ] Task 6: 创建任务管理 REST API
  - [ ] SubTask 6.1: 创建 `agent_backend/api/v1/scheduler.py`
    - GET /scheduler/tasks — 获取任务列表
    - GET /scheduler/tasks/{task_id}/results — 获取任务执行结果
    - POST /scheduler/tasks/{task_id}/run — 手动触发任务
    - PUT /scheduler/tasks/{task_id}/pause — 暂停任务
    - PUT /scheduler/tasks/{task_id}/resume — 恢复任务
    - DELETE /scheduler/tasks/{task_id} — 删除任务
  - [ ] SubTask 6.2: 修改 `agent_backend/api/routes.py`，注册 scheduler_router

- [ ] Task 7: 验证测试
  - [ ] SubTask 7.1: 验证应用启动时调度器正常初始化，默认任务从配置文件加载
  - [ ] SubTask 7.2: 验证定时任务按配置间隔执行，结果写入 agent_task_result 表
  - [ ] SubTask 7.3: 验证通过聊天对话创建定时任务（schedule_task Tool Calling）
  - [ ] SubTask 7.4: 验证任务管理 API 端点功能正常
  - [ ] SubTask 7.5: 验证应用重启后任务自动恢复
  - [ ] SubTask 7.6: 验证任务执行异常不影响其他任务和调度器运行

# Task Dependencies

- [Task 2] depends on [Task 1] (需要数据库表和依赖)
- [Task 3] depends on [Task 2] (需要 SchedulerManager 接口)
- [Task 4] depends on [Task 2, Task 3] (需要核心模块和配置文件)
- [Task 5] depends on [Task 2] (需要 SchedulerManager 接口)
- [Task 6] depends on [Task 2] (需要 SchedulerManager 接口)
- [Task 7] depends on [Task 4, Task 5, Task 6] (需要全部功能就绪)
- [Task 5] 和 [Task 6] 可并行执行
