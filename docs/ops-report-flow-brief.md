# 运维简报流程简报

## 1. 先说结论

### `agent_backend/scheduler` 目录现在还有没有用

结论：这套代码还在仓库里，但按当前主流程看，已经没有真正接入运行链路，属于“保留实现，但当前版本基本不生效”。

直接证据有 3 个：

1. 应用启动时只启动了运维简报管理器，没有启动 `SchedulerManager`
   - `agent_backend/main.py:79` 先执行 `init_db()`
   - `agent_backend/main.py:80-81` 获取并启动 `get_ops_report_manager()`
   - 同一个 `lifespan()` 里没有 `get_scheduler_manager().start()`

2. 后端主路由只挂了运维简报路由，没有挂 `scheduler` 路由
   - `agent_backend/api/routes.py:35` 导入 `ops_router`
   - `agent_backend/api/routes.py:43` 挂载 `ops_router`
   - 同文件里没有 `scheduler_router` 的导入和挂载

3. Agent 可用工具列表里没有把 scheduler 相关工具接进去
   - `agent_backend/agent/tools/__init__.py:33` 定义 `ALL_TOOLS`
   - 这个列表里只有 `sql_query`、`rag_search`、`metadata_query`、`get_current_time`、`calculator`、`generate_chart`、`export_data`、`web_search`
   - 没有 `schedule_task()`，也没有 `manage_scheduled_task()`

所以现在的状态不是“目录完全没价值”，而是：

- `agent_backend/scheduler/manager.py` 里那套通用 SQL 定时任务能力仍然完整存在
- `agent_backend/scheduler/executor.py` 也还能执行并落库结果
- `agent_backend/configs/scheduled_tasks.yaml` 里还有默认任务定义
- 但因为没有启动入口，也没有路由和工具注册，所以当前版本默认不会跑起来

一句话概括：`scheduler` 更像是旧的通用定时任务系统；新加的运维简报没有复用它，而是自己单独实现了一套 `ops_reports` 调度链路。

## 2. 运维简报从哪里开始

真正的启动入口在：

- `agent_backend/main.py:78` `lifespan(app)`

启动顺序是：

```text
uvicorn agent_backend.main:app
  -> create_app()
  -> lifespan(app)
  -> init_db()
  -> get_ops_report_manager()
  -> OpsReportManager.start()
  -> AsyncIOScheduler 注册运维简报任务
```

关键代码位置：

- `agent_backend/main.py:79` `await init_db()`
- `agent_backend/main.py:80` `ops_report_manager = get_ops_report_manager()`
- `agent_backend/main.py:81` `await ops_report_manager.start()`
- `agent_backend/main.py:85` `await ops_report_manager.shutdown()`

这说明运维简报是在应用生命周期里自动启动的，不依赖外部手工初始化。

## 3. 运维简报核心类怎么分工

### `OpsReportManager`

文件：`agent_backend/ops_reports/manager.py`

它负责“调度和对外管理”，不是负责真正的数据采集。

关键方法：

- `37` `start()`
  - 读取 `agent_backend/configs/ops_reports.yaml`
  - 创建 `OpsReportExecutor`
  - 创建 `AsyncIOScheduler`
  - 给每个 `report_key` 注册定时间隔任务

- `103` `run_report_now(report_key=None)`
  - 手动触发一次简报生成
  - 最终转发给 `OpsReportExecutor.generate_report(...)`

- `219` `_run_report_job(report_key)`
  - APScheduler 定时触发时真正调用的方法
  - 内部还是走 `run_report_now(report_key)`

- `116` `list_reports(...)`
- `146` `get_latest_report()`
- `166` `get_report(report_id)`
- `196` `mark_report_read(report_id)`
  - 这几个方法负责给 API/前端读取简报、未读数、详情和已读状态

### `OpsReportExecutor`

文件：`agent_backend/ops_reports/executor.py`

它负责“真正生成一份简报”，也就是采集数据、做趋势对比、识别异常、拼摘要、生成 Markdown、最后入库。

关键方法：

- `37` `generate_report(report_key, config)`
  - 这是整条生成链路的总入口

- `97` `_collect_online_metrics(...)`
  - 查在线设备、总设备数、未开机设备数、缺失运行记录数

- `150` `_collect_remote_metrics(...)`
  - 从 `AdminLog` 中解析远程协助日志
  - 汇总出远程协助次数、Top 客户端、最后远程时间

- `248` `_collect_usb_metrics(...)`
  - 统计 USB 使用总数、Top 设备、Top 电脑

- `311` `_load_previous_snapshot(report_key)`
  - 取上一期快照，给趋势对比使用

- `332` `_build_trends(current, previous)`
  - 计算和上一期相比的增减变化

- `397` `_detect_anomalies(current, previous, thresholds)`
  - 按阈值识别异常，比如在线数下降、未开机数增加、远程/USB 激增

- `465` `_build_template_summary(snapshot)`
  - 先生成一版规则模板摘要

- `524` `_polish_summary(summary, snapshot)`
  - 如果配置允许，就调用 LLM 把摘要润色得更自然
  - 这里只润色语气，不应该改数字和事实

- `550` `_build_markdown_report(...)`
  - 生成最终 Markdown 正文

- `685` `_store_report(...)`
  - 把简报正文和结构化快照一起落库

### ORM 模型

文件：`agent_backend/db/models.py`

- `189` `OpsReport`
  - 一份简报的主记录
  - 重点字段：
    - `202` `report_id`
    - `206` `content_md`
    - `208` `unread`

- `215` `OpsMetricSnapshot`
  - 一份简报对应的结构化快照
  - 重点字段：
    - `229` `report_id`
    - `231` `snapshot_data`

一句话概括：

- `OpsReportManager` 负责“什么时候生成、怎么给外部访问”
- `OpsReportExecutor` 负责“这一份简报具体怎么做出来”
- `OpsReport` / `OpsMetricSnapshot` 负责“结果怎么存下来”

## 4. 定时生成链路

配置文件位置：

- `agent_backend/configs/ops_reports.yaml`

当前默认配置：

- `2` `report_key: default_ops_brief`
- `4` `interval_seconds: 7200`
- `5` `lookback_days: 3`
- `6` `top_n: 20`
- `7` `llm_polish_enabled: true`

也就是：

- 每 7200 秒生成一次
- 统计最近 3 天
- 远程协助和 USB 排 Top20
- 默认启用 LLM 润色摘要

定时链路如下：

```text
main.py / lifespan()
  -> OpsReportManager.start()
  -> _load_configs()
  -> AsyncIOScheduler.add_job(self._run_report_job, IntervalTrigger(...))
  -> APScheduler 到点触发 _run_report_job(report_key)
  -> run_report_now(report_key)
  -> OpsReportExecutor.generate_report(report_key, config)
  -> _store_report(...)
  -> 写入 ops_report + ops_metric_snapshot
```

## 5. 手动生成链路

除了定时触发，还可以手动触发。

后端 API 在：

- `agent_backend/api/v1/ops.py:36` `POST /api/v1/ops/reports/run`

调用链是：

```text
POST /api/v1/ops/reports/run
  -> api/v1/ops.py run_ops_report_now()
  -> OpsReportManager.run_report_now()
  -> OpsReportExecutor.generate_report()
  -> 入库并返回结果
```

所以“手动生成”和“定时生成”最后都会汇合到同一个入口：

- `agent_backend/ops_reports/executor.py:37` `generate_report(...)`

## 6. 一份简报在 `generate_report()` 里怎么做出来

按执行顺序看，`agent_backend/ops_reports/executor.py:37` 里的流程可以压成下面这几步：

```text
generate_report()
  -> 读取配置(top_n / lookback_days / thresholds / llm_polish_enabled)
  -> 计算统计窗口(now, cutoff)
  -> _load_previous_snapshot()
  -> _collect_online_metrics()
  -> _collect_remote_metrics()
  -> _collect_usb_metrics()
  -> 拼出 snapshot
  -> _build_trends()
  -> _detect_anomalies()
  -> _build_template_summary()
  -> _polish_summary()        # 可选，受 llm_polish_enabled 控制
  -> _build_severity()
  -> _build_markdown_report()
  -> _store_report()
```

这里最关键的几个设计点是：

1. 先采集结构化数据，再生成自然语言摘要  
   这样摘要只是“描述结果”，不是直接让 LLM自由发挥。

2. 先落结构化快照，再做下一期对比  
   这样趋势和异常判断可复用，不依赖重新扫历史文本。

3. LLM 只参与润色，不负责原始统计  
   这会比“直接让模型编运维简报”稳定很多。

## 7. 对外读取和前端展示链路

### 后端接口

路由挂载位置：

- `agent_backend/api/routes.py:43` 挂载 `ops_router`

API 文件：

- `agent_backend/api/v1/ops.py:12` `GET /api/v1/ops/reports`
- `agent_backend/api/v1/ops.py:21` `GET /api/v1/ops/reports/latest`
- `agent_backend/api/v1/ops.py:27` `GET /api/v1/ops/reports/{report_id}`
- `agent_backend/api/v1/ops.py:36` `POST /api/v1/ops/reports/run`
- `agent_backend/api/v1/ops.py:45` `PUT /api/v1/ops/reports/{report_id}/read`

健康检查里也暴露了运维简报调度器状态：

- `agent_backend/api/v1/health.py:32` `health_check()`
- `agent_backend/api/v1/health.py:34` `ops_reports.get_info()`

### 前端入口

前端总入口：

- `agent_frontend/src/App.vue:4` 引入 `OpsReportInbox`
- `agent_frontend/src/App.vue:29` `toggleOpsInbox()`
- `agent_frontend/src/App.vue:61` `handleOpsUnreadChange(count)`
- `agent_frontend/src/App.vue:146` 渲染 `<OpsReportInbox />`

前端 API 封装：

- `agent_frontend/src/api/opsReports.js:1` `API_BASE = '/api/v1/ops'`
- `17` `listOpsReports(...)`
- `22` `getLatestOpsReport()`
- `27` `getOpsReport(reportId)`
- `32` `markOpsReportRead(reportId)`
- `39` `runOpsReportNow()`

收件箱组件：

- `agent_frontend/src/components/OpsReportInbox.vue:34` `reports = ref([])`
- `77` `refreshUnreadMeta()`
- `86` `loadReports()`
- `116` `loadReport(reportId)`
- `143` `startPolling()`
- `156` `watch(() => props.open, ...)`
- `168` `onMounted(...)`

前端链路可以理解成：

```text
App.vue
  -> 打开 OpsReportInbox
  -> opsReports.js 调用 /api/v1/ops/*
  -> 后端 OpsReportManager 查询数据库
  -> 返回简报列表 / 详情 / 未读数
  -> Inbox 渲染摘要和 Markdown 正文
```

## 8. 和旧 scheduler 的关系

两套东西的边界要分清：

### 旧 `scheduler`

文件：

- `agent_backend/scheduler/manager.py`
- `agent_backend/scheduler/executor.py`
- `agent_backend/configs/scheduled_tasks.yaml`

它设计的是“通用 SQL 定时任务系统”：

- `manager.py:110` `start()`
- `manager.py:156` `add_task(...)`
- `manager.py:350` `get_tasks()`
- `manager.py:455` `run_task_now(task_id)`
- `manager.py:582` `_load_default_tasks()`
- `executor.py:63` `execute_task(task_id)`

还配了两类对外入口：

- `agent_backend/api/v1/scheduler.py:45` `GET /scheduler/tasks`
- `agent_backend/api/v1/scheduler.py:86` `POST /scheduler/tasks/{task_id}/run`
- `agent_backend/agent/tools/scheduler_tool.py:107` `schedule_task(...)`
- `agent_backend/agent/tools/scheduler_manage_tool.py:90` `manage_scheduled_task(...)`

但这些入口当前都没有真正接到主运行链路里。

### 新 `ops_reports`

文件：

- `agent_backend/ops_reports/manager.py`
- `agent_backend/ops_reports/executor.py`
- `agent_backend/configs/ops_reports.yaml`

它是专门为“运维简报”定制的一套轻量实现：

- 专门的配置模型
- 专门的指标采集 SQL
- 专门的摘要/异常/Markdown 生成逻辑
- 专门的前端收件箱

一句话概括：

- `scheduler` 解决的是“任意 SQL 定时执行”
- `ops_reports` 解决的是“固定业务口径的运维简报自动生成”

## 9. 如果你后面要继续改，应该优先看哪些点

如果你后面要继续改“运维简报”，建议按这个顺序看：

1. `agent_backend/main.py:78`
   - 看启动时怎么把调度器拉起来

2. `agent_backend/ops_reports/manager.py:37`
   - 看任务是怎么注册到 `AsyncIOScheduler` 的

3. `agent_backend/ops_reports/executor.py:37`
   - 看一份简报的完整生成主流程

4. `agent_backend/ops_reports/executor.py:97` / `150` / `248`
   - 看三个核心指标源头是怎么查的

5. `agent_backend/ops_reports/executor.py:397`
   - 看异常阈值判断

6. `agent_backend/configs/ops_reports.yaml`
   - 改时间窗口、频率、TopN、阈值

7. `agent_backend/api/v1/ops.py`
   - 看前端是通过哪些接口取数

8. `agent_frontend/src/components/OpsReportInbox.vue`
   - 看页面怎么轮询、怎么展示未读、怎么渲染 Markdown

## 10. 最后一句

当前后端里，真正在线上主流程生效的是 `ops_reports` 这条链路，不是 `scheduler` 这条链路。
