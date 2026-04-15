# 智能体定时任务调度系统 Spec

## Why

当前智能体聊天平台仅支持即时交互式查询（用户问→Agent答），缺乏自动化定时巡检能力。运维人员需要定期统计在线客户端数量、资产变更、USB日志等指标，目前只能手动反复询问Agent，效率低下。需要为智能体增加定时任务调度能力，支持从配置文件加载默认任务，也支持通过聊天对话动态创建任务，任务执行结果持久化到数据库供后续查询和推送。

## What Changes

- 新增 `agent_backend/scheduler/` 模块，基于 APScheduler AsyncIOScheduler 实现定时任务调度核心
- 新增 `agent_task` 数据库表，存储定时任务执行结果
- 新增 `agent_backend/configs/scheduled_tasks.yaml` 配置文件，定义默认定时任务
- 新增 Agent Tool `schedule_task`，支持通过聊天对话动态创建/管理定时任务
- 新增 API 端点 `/api/v1/scheduler/tasks` 等，提供任务管理 REST 接口
- 更新 `agent_backend/main.py`，集成 Scheduler 生命周期管理
- 更新 `agent_backend/agent/tools/__init__.py`，注册新工具
- 更新 `agent_backend/agent/prompts.py`，添加定时任务工具说明
- 更新 `agent_backend/agent/state.py`，添加调度相关状态字段
- 更新 `agent_backend/agent/nodes.py`，处理调度工具结果
- 更新 `docker-compose.yml`，同步相关配置
- 更新 `requirements.txt`，新增 APScheduler 依赖

## Impact

- Affected specs: Agent 工具体系、API 路由层、数据库层、应用生命周期
- Affected code:
  - `agent_backend/main.py` — 应用启动/关闭时管理 Scheduler
  - `agent_backend/agent/tools/__init__.py` — 注册新工具
  - `agent_backend/agent/prompts.py` — 系统提示词更新
  - `agent_backend/agent/state.py` — 状态字段扩展
  - `agent_backend/agent/nodes.py` — 工具结果处理
  - `agent_backend/api/routes.py` — 路由注册
  - `docker-compose.yml` — 配置同步
  - `requirements.txt` — 新依赖

## 技术方案调研与选型

### 调度框架对比

| 维度 | APScheduler | Celery Beat | asyncio 手写循环 |
|------|-------------|-------------|------------------|
| **复杂度** | 低，单进程内嵌 | 高，需消息代理(Redis/RabbitMQ) | 最低，但功能有限 |
| **异步支持** | ✅ AsyncIOScheduler | ❌ 需 worker 进程 | ✅ 原生 |
| **动态任务** | ✅ 运行时增删改 | ❌ 需重启/数据库支持 | ✅ 但需自管理 |
| **持久化** | ✅ SQLAlchemy jobstore | ✅ 依赖 broker | ❌ 需自实现 |
| **触发器** | interval/cron/date | cron only | interval only |
| **FastAPI集成** | ✅ 生命周期绑定 | 需独立进程 | ✅ 简单 |
| **依赖** | apscheduler | celery + broker | 无 |
| **适合场景** | 中小规模单进程 | 大规模分布式 | 极简场景 |

### 最终选型：APScheduler (AsyncIOScheduler)

**理由**：
1. **轻量内嵌**：无需外部消息代理，单进程内运行，与当前单容器部署架构一致
2. **原生异步**：AsyncIOScheduler 与 FastAPI 的 async 事件循环完美兼容
3. **动态任务**：运行时可通过 API 动态添加/修改/删除任务，满足聊天创建任务的需求
4. **持久化**：SQLAlchemy jobstore 可将任务定义持久化到当前连接的数据库，重启后自动恢复
5. **触发器丰富**：支持 interval（每隔N分钟）、cron（定时表达式）、date（单次），覆盖所有需求场景
6. **成熟稳定**：APScheduler 3.x 是 Python 生态最成熟的调度库之一

### 任务执行架构

```
定时触发 → Scheduler 调度 → TaskExecutor 执行
  ├── 读取任务定义（SQL模板/描述）
  ├── 复用现有 SQL 生成+执行链路
  │   ├── 模板任务：直接执行预定义 SQL
  │   └── 自然语言任务：调用 get_sql_llm 生成 SQL → 安全校验 → 执行
  ├── 结果写入 agent_task 表
  └── 记录执行日志
```

### agent_task 表设计

```sql
CREATE TABLE agent_task (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL COMMENT '任务定义ID（唯一标识一个定时任务）',
    agent_name VARCHAR(128) NOT NULL COMMENT '智能体名称（如 desk-agent）',
    task_name VARCHAR(256) NOT NULL COMMENT '任务名称（如 统计在线客户端数量）',
    task_type VARCHAR(32) NOT NULL DEFAULT 'interval' COMMENT '任务类型：interval/cron/date',
    task_config TEXT COMMENT '任务配置JSON（interval_seconds/cron_expr等）',
    sql_template TEXT COMMENT '预定义SQL模板（模板任务使用）',
    description TEXT COMMENT '任务描述（自然语言，动态任务使用）',
    status VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT '任务状态：active/paused/completed/error',
    last_run_at DATETIME COMMENT '上次执行时间',
    next_run_at DATETIME COMMENT '下次执行时间',
    created_by VARCHAR(64) DEFAULT 'system' COMMENT '创建者：system/chat/user',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_task_id (task_id),
    INDEX idx_agent_name (agent_name),
    INDEX idx_status (status)
) COMMENT='智能体定时任务定义表';

CREATE TABLE agent_task_result (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL COMMENT '关联任务ID',
    agent_name VARCHAR(128) NOT NULL COMMENT '智能体名称',
    run_at DATETIME NOT NULL COMMENT '执行时间',
    status VARCHAR(16) NOT NULL DEFAULT 'success' COMMENT '执行状态：success/error',
    result_data TEXT COMMENT '执行结果数据JSON',
    result_summary TEXT COMMENT '结果摘要文本',
    error_message TEXT COMMENT '错误信息（失败时）',
    duration_ms INT COMMENT '执行耗时毫秒',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    INDEX idx_task_id (task_id),
    INDEX idx_agent_name (agent_name),
    INDEX idx_run_at (run_at)
) COMMENT='智能体定时任务执行结果表';
```

**设计要点**：
- **任务定义与结果分离**：`agent_task` 存储任务定义，`agent_task_result` 存储每次执行结果，避免单表膨胀
- `task_id` 全局唯一标识一个定时任务，关联两张表
- `agent_name` 字段满足需求，支持多智能体场景
- `sql_template` 用于模板任务直接执行，`description` 用于动态任务由 LLM 生成 SQL
- `task_config` JSON 灵活存储不同触发器类型的配置
- `created_by` 区分任务来源：system（配置文件）、chat（聊天创建）

### 默认任务配置文件设计

```yaml
# agent_backend/configs/scheduled_tasks.yaml
agent_name: desk-agent

tasks:
  - task_id: online_client_count
    task_name: 统计在线客户端数量
    task_type: interval
    interval_seconds: 1800  # 30分钟
    sql_template: |
      SELECT COUNT(*) AS online_count
      FROM s_machine
      WHERE IsOnline = 1
    description: 每隔30分钟统计在线客户端数量

  - task_id: asset_change_detection
    task_name: 统计新增资产变更的设备
    task_type: interval
    interval_seconds: 1800  # 30分钟
    sql_template: |
      SELECT m.MachineName, m.IP, m.GroupID, m.LastUpdateTime
      FROM s_machine m
      WHERE m.LastUpdateTime >= DATE_SUB(NOW(), INTERVAL 30 MINUTE)
    description: 每隔30分钟统计新增资产变更的设备

  - task_id: usb_log_stats
    task_name: 统计USB日志情况
    task_type: interval
    interval_seconds: 7200  # 2小时
    description: 每隔2小时统计USB日志情况
```

**设计要点**：
- 有 `sql_template` 的任务直接执行 SQL，无需 LLM 介入，高效可靠
- 无 `sql_template` 仅有 `description` 的任务，执行时调用 LLM 生成 SQL（动态任务模式）
- 配置文件中的任务 `created_by` 标记为 `system`

## ADDED Requirements

### Requirement: 定时任务调度核心

系统 SHALL 提供基于 APScheduler AsyncIOScheduler 的定时任务调度能力，与 FastAPI 应用生命周期绑定。

#### Scenario: 应用启动时初始化调度器
- **WHEN** FastAPI 应用启动
- **THEN** Scheduler 自动初始化，从数据库加载已有活跃任务并恢复调度，从配置文件加载默认任务（若数据库中不存在则创建）

#### Scenario: 应用关闭时清理调度器
- **WHEN** FastAPI 应用关闭
- **THEN** Scheduler 优雅关闭，等待当前执行中的任务完成（最多5秒超时）

#### Scenario: 调度器异常恢复
- **WHEN** 单次任务执行抛出异常
- **THEN** 异常被捕获并记录到 `agent_task_result` 表（status=error），不影响后续调度和其他任务

### Requirement: 任务定义持久化

系统 SHALL 将定时任务定义持久化到数据库 `agent_task` 表，支持重启后自动恢复。

#### Scenario: 新任务创建持久化
- **WHEN** 通过配置文件或聊天创建新任务
- **THEN** 任务定义写入 `agent_task` 表，状态为 active

#### Scenario: 应用重启恢复任务
- **WHEN** 应用重启时
- **THEN** 从 `agent_task` 表读取所有 status=active 的任务，重新注册到 Scheduler

#### Scenario: 配置文件默认任务初始化
- **WHEN** 应用首次启动，数据库中无任务记录
- **THEN** 从 `scheduled_tasks.yaml` 读取默认任务定义，写入数据库并注册调度

### Requirement: 任务执行与结果存储

系统 SHALL 执行定时任务并将结果存储到 `agent_task_result` 表。

#### Scenario: 模板任务执行
- **WHEN** 任务定义包含 `sql_template`
- **THEN** 直接执行预定义 SQL，将查询结果 JSON 写入 `result_data`，生成摘要写入 `result_summary`

#### Scenario: 自然语言任务执行
- **WHEN** 任务定义仅有 `description`（无 sql_template）
- **THEN** 调用 LLM 根据 description 生成 SQL，经安全校验后执行，结果存储同上

#### Scenario: 任务执行失败
- **WHEN** SQL 执行或 LLM 生成失败
- **THEN** 记录 status=error，error_message 包含具体错误信息，不影响后续调度

### Requirement: 聊天创建定时任务

系统 SHALL 提供 `schedule_task` Agent Tool，支持用户通过自然语言对话创建定时任务。

#### Scenario: 用户请求创建定时任务
- **WHEN** 用户说"每隔30分钟记录一下在线客户端数量"
- **THEN** Agent 调用 schedule_task 工具，解析出 interval=30分钟、任务描述="记录在线客户端数量"，创建任务并返回确认信息

#### Scenario: 用户请求查看已有任务
- **WHEN** 用户说"查看当前有哪些定时任务"
- **THEN** Agent 调用 schedule_task 工具（action=list），返回活跃任务列表

#### Scenario: 用户请求暂停/删除任务
- **WHEN** 用户说"暂停统计在线客户端的任务"或"删除USB日志统计任务"
- **THEN** Agent 调用 schedule_task 工具（action=pause/delete），执行对应操作并返回确认

### Requirement: 任务管理 REST API

系统 SHALL 提供任务管理的 REST API 端点。

#### Scenario: 获取任务列表
- **WHEN** GET /api/v1/scheduler/tasks
- **THEN** 返回所有任务定义列表，包含 task_id、task_name、status、last_run_at、next_run_at 等

#### Scenario: 获取任务执行结果
- **WHEN** GET /api/v1/scheduler/tasks/{task_id}/results
- **THEN** 返回指定任务的最近执行结果列表

#### Scenario: 手动触发任务
- **WHEN** POST /api/v1/scheduler/tasks/{task_id}/run
- **THEN** 立即执行一次指定任务，返回执行结果

#### Scenario: 暂停/恢复任务
- **WHEN** PUT /api/v1/scheduler/tasks/{task_id}/pause 或 /resume
- **THEN** 暂停或恢复指定任务的调度

#### Scenario: 删除任务
- **WHEN** DELETE /api/v1/scheduler/tasks/{task_id}
- **THEN** 删除指定任务（从 Scheduler 移除并标记数据库记录为 completed）

### Requirement: 定时任务工具集成到 Agent

系统 SHALL 将 schedule_task 注册为 Agent Tool，LLM 可通过 Tool Calling 自主调用。

#### Scenario: LLM 识别定时任务意图
- **WHEN** 用户消息包含"每隔"、"定时"、"定期"、"每天"、"每小时"等时间周期表述，且需要自动执行
- **THEN** LLM 调用 schedule_task 工具创建任务

#### Scenario: LLM 识别任务管理意图
- **WHEN** 用户消息包含"查看任务"、"暂停任务"、"删除任务"等管理意图
- **THEN** LLM 调用 schedule_task 工具执行对应管理操作

## MODIFIED Requirements

### Requirement: Agent 工具体系扩展

现有 Agent 工具体系 SHALL 新增 `schedule_task` 工具，注册到 `ALL_TOOLS` 列表，LLM 可通过 Tool Calling 自主调用。

- `agent_backend/agent/tools/__init__.py` 新增 `schedule_task` 导入和注册
- `agent_backend/agent/prompts.py` SYSTEM_PROMPT 新增定时任务工具说明
- `agent_backend/agent/state.py` AgentState 新增 `scheduler_results: list[dict]` 字段
- `agent_backend/agent/nodes.py` tool_result_node 新增 schedule_task 结果处理

### Requirement: 应用生命周期管理

`agent_backend/main.py` 的 create_app SHALL 在应用启动时初始化 Scheduler，在关闭时清理资源。

- 启动事件：初始化 Scheduler → 加载配置文件默认任务 → 恢复数据库已有任务
- 关闭事件：关闭 Scheduler → 等待执行中任务完成

### Requirement: API 路由注册

`agent_backend/api/routes.py` SHALL 新增 scheduler_router 注册。

### Requirement: Docker 配置同步

`docker-compose.yml` SHALL 新增定时任务相关环境变量配置（如 SCHEDULER_ENABLED、SCHEDULED_TASKS_CONFIG_PATH）。

## REMOVED Requirements

无移除的需求。
