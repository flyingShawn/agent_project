# 监控智能体（Monitor Agent）实施方案

## 一、可行性分析报告

### 1.1 技术可行性

| 维度 | 评估 | 说明 |
|------|------|------|
| **调度机制** | ✅ 高度可行 | 项目当前无任何定时调度，需引入 APScheduler（轻量、成熟、与 FastAPI 集成良好） |
| **数据库共享** | ✅ 高度可行 | 现有 `ConnectionManager` 为会话级单连接模式，监控智能体需建立独立连接池，两者互不干扰 |
| **模块解耦** | ✅ 高度可行 | 现有 `sql_agent/`、`rag_engine/`、`chat/` 三模块已完全解耦，新增 `monitor_agent/` 遵循同样模式 |
| **配置驱动** | ✅ 高度可行 | 项目已有 `schema_metadata.yaml` 配置驱动模式，监控规则同样采用 YAML 配置，避免硬编码 |
| **LLM 集成** | ✅ 高度可行 | 现有 `OllamaChatClient` 已封装同步/流式调用，监控智能体可直接复用 |
| **FastAPI 集成** | ✅ 高度可行 | 使用现代 `lifespan` 上下文管理器替代已废弃的 `on_event`，同时升级现有生命周期管理 |

### 1.2 架构适配性分析

现有系统采用**规则路由 + Pipeline 模式**，非 ReAct Agent 模式。监控智能体同样采用 Pipeline 模式：

```
定时触发 → 规则配置加载 → SQL 执行 → 结果分析 → 事件生成 → 存储/通知
```

这与现有 SQL Agent 的 Pipeline 模式（模板匹配 → RAG 检索 → LLM 生成 → 安全校验 → 执行）高度一致，架构风格统一。

### 1.3 风险评估

| 风险 | 等级 | 规避措施 |
|------|------|----------|
| 数据库连接竞争 | 中 | 监控智能体使用独立连接池，与聊天智能体的 `ConnectionManager` 完全隔离 |
| 轮询 SQL 对生产库造成压力 | 中 | 限制查询频率、强制 LIMIT、只读事务隔离 |
| APScheduler 与 FastAPI 生命周期冲突 | 低 | 使用 `lifespan` 上下文管理器统一管理启动/关闭 |
| 监控规则配置错误导致异常 | 低 | Pydantic 强类型校验 + 默认值兜底 + 异常隔离（单规则失败不影响其他规则） |
| 线程安全 | 低 | 监控智能体在独立线程中运行，结果存储使用线程安全的数据结构 |

---

## 二、系统架构设计

### 2.1 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                     FastAPI Application                          │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  Chat Agent  │  │  RAG Engine  │  │    Monitor Agent       │ │
│  │  (现有)       │  │  (现有)       │  │    (新增)               │ │
│  │              │  │              │  │                        │ │
│  │ Intent Router│  │ Hybrid Search│  │ ┌──────────────────┐  │ │
│  │ SQL Pipeline │  │ Doc Ingest   │  │ │ Scheduler        │  │ │
│  │ RAG Pipeline │  │              │  │ │ (APScheduler)    │  │ │
│  └──────┬───────┘  └──────┬───────┘  │ └────────┬─────────┘  │ │
│         │                 │          │ ┌────────▼─────────┐  │ │
│         │                 │          │ │ Rule Engine      │  │ │
│         │                 │          │ │ (配置驱动)        │  │ │
│         │                 │          │ └────────┬─────────┘  │ │
│         │                 │          │ ┌────────▼─────────┐  │ │
│         │                 │          │ │ Event Store      │  │ │
│         │                 │          │ │ (内存+持久化)     │  │ │
│         │                 │          │ └────────┬─────────┘  │ │
│         │                 │          │ ┌────────▼─────────┐  │ │
│         │                 │          │ │ LLM Summarizer   │  │ │
│         │                 │          │ │ (复用OllamaClient)│  │ │
│         │                 │          │ └──────────────────┘  │ │
│         │                 │          └────────────────────────┘ │
│         │                 │                     │               │
│  ┌──────▼─────────────────▼─────────────────────▼───────────┐  │
│  │              Shared Infrastructure                        │  │
│  │  ┌─────────────────┐  ┌──────────────┐  ┌────────────┐  │  │
│  │  │ ConnectionMgr   │  │ MonitorConn  │  │ LLM Client │  │  │
│  │  │ (聊天会话级)     │  │ Pool (监控)   │  │ (Ollama)   │  │  │
│  │  └────────┬────────┘  └──────┬───────┘  └────────────┘  │  │
│  └───────────┼──────────────────┼──────────────────────────┘  │
│              │                  │                              │
└──────────────┼──────────────────┼──────────────────────────────┘
               │                  │
        ┌──────▼──────────────────▼──────┐
        │       MySQL / PostgreSQL       │
        │    (只读查询，两个连接池隔离)    │
        └───────────────────────────────┘
```

### 2.2 监控智能体内部架构

```
MonitorAgent (独立执行循环)
│
├── Scheduler (APScheduler)
│   ├── 启动时加载 monitor_rules.yaml
│   ├── 为每条规则注册定时任务
│   └── 支持运行时动态增删规则
│
├── Rule Engine (配置驱动)
│   ├── MonitorRule (单条规则定义)
│   │   ├── name: 规则名称
│   │   ├── description: 规则描述
│   │   ├── interval_seconds: 轮询周期
│   │   ├── sql: 查询SQL (从 schema_metadata.yml 的 query_patterns 扩展)
│   │   ├── params: SQL参数
│   │   ├── condition: 触发条件表达式
│   │   ├── severity: 严重级别 (info/warning/critical)
│   │   └── enabled: 是否启用
│   │
│   └── RuleExecutor (规则执行器)
│       ├── 获取独立数据库连接
│       ├── 执行 SQL 查询
│       ├── 评估触发条件
│       └── 生成 MonitorEvent
│
├── Event Store (事件存储)
│   ├── 内存环形缓冲区 (最近N条事件，快速读取)
│   ├── 事件去重 (同规则同指纹在时间窗口内不重复)
│   └── 事件查询 API
│
├── LLM Summarizer (可选)
│   ├── 对事件进行自然语言总结
│   ├── 复用现有 OllamaChatClient
│   └── 独立 system prompt
│
└── Monitor API (HTTP接口)
    ├── GET /api/v1/monitor/status     - 调度器状态
    ├── GET /api/v1/monitor/events     - 事件列表
    ├── GET /api/v1/monitor/rules      - 规则列表
    └── POST /api/v1/monitor/rules/{name}/toggle - 启停规则
```

---

## 三、详细实施步骤

### 步骤 1：添加依赖并升级应用生命周期

**目标**：引入 APScheduler，将 FastAPI 生命周期从废弃的 `on_event` 升级为现代 `lifespan` 上下文管理器。

**文件变更**：
- `requirements.txt` — 添加 `APScheduler>=3.10`
- `agent_backend/main.py` — 重构为 `lifespan` 模式

**具体实现**：

1. `requirements.txt` 添加：
```
APScheduler>=3.10
```

2. `main.py` 重构为 lifespan 模式：
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("🚀 应用启动中...")
    
    # 启动监控调度器（如果启用）
    from agent_backend.monitor_agent.scheduler import get_monitor_scheduler
    scheduler = get_monitor_scheduler()
    if scheduler.enabled:
        scheduler.start()
        logger.info("✅ 监控调度器已启动")
    
    yield
    
    # Shutdown
    logger.info("🔻 应用正在关闭...")
    
    # 停止监控调度器
    if scheduler.enabled:
        scheduler.shutdown()
        logger.info("✅ 监控调度器已停止")
    
    # 关闭数据库连接
    conn_manager = get_connection_manager()
    conn_manager.shutdown()
    logger.info("✅ 应用关闭完成")

def create_app() -> FastAPI:
    app = FastAPI(title="desk-agent-backend", lifespan=lifespan)
    # ... 中间件、路由注册不变
```

---

### 步骤 2：创建监控规则配置体系

**目标**：设计 YAML 配置驱动的监控规则，避免硬编码，支持灵活扩展。

**新增文件**：
- `agent_backend/configs/monitor_rules.yaml` — 监控规则配置
- `agent_backend/monitor_agent/models.py` — Pydantic 模型定义

**monitor_rules.yaml 结构设计**：

```yaml
version: "0.1"
enabled: true                    # 全局开关
default_interval_seconds: 300    # 默认轮询周期（5分钟）
max_events_per_rule: 100         # 每条规则最多保留事件数
dedup_window_seconds: 300        # 事件去重时间窗口

rules:
  - name: online_client_count
    description: "在线客户端数量统计"
    interval_seconds: 60         # 每分钟检查一次
    enabled: true
    severity: info
    sql: "SELECT COUNT(*) as count FROM onlineinfo"
    params: {}
    condition: "result[0]['count'] != prev_result[0]['count']"  # 数量变化时触发
    summary_template: "在线客户端数量从 {prev_count} 变为 {curr_count}"

  - name: remote_access_record
    description: "客户端远程访问记录"
    interval_seconds: 300
    enabled: true
    severity: info
    sql: >-
      SELECT r.ip, r.machinename, r.department, r.lasttime, r.managerid
      FROM a_remoteinfo r
      ORDER BY r.lasttime DESC
      LIMIT 10
    params: {}
    condition: "has_new_records(result, prev_result, 'lasttime')"
    summary_template: "检测到新的远程访问记录"

  - name: hardware_change_detection
    description: "设备资产变化检测"
    interval_seconds: 600
    enabled: true
    severity: warning
    sql: >-
      SELECT h.MtID, m.Name_C, m.Ip_C, g.GroupName, h.ChangeTime, h.CPU, h.Memory
      FROM a_clienthardinfo2 h
      JOIN s_machine m ON h.MtID = m.ID
      LEFT JOIN s_group g ON m.Groupid = g.id
      WHERE h.IsChange = 1 AND h.IsNew = 1
      ORDER BY h.ChangeTime DESC
      LIMIT 50
    params: {}
    condition: "len(result) > 0"
    summary_template: "检测到 {count} 台设备硬件变更"

  - name: long_offline_client
    description: "长期未上线客户端识别"
    interval_seconds: 3600       # 每小时检查一次
    enabled: true
    severity: warning
    sql: >-
      SELECT m.Name_C, m.Ip_C, g.GroupName, m.MtGetDate, u.UserName
      FROM s_machine m
      LEFT JOIN s_group g ON m.Groupid = g.id
      LEFT JOIN s_user u ON m.ClientId = u.ID
      WHERE m.MtGetDate IS NOT NULL
        AND m.MtGetDate < DATE_SUB(NOW(), INTERVAL 30 DAY)
      ORDER BY m.MtGetDate ASC
      LIMIT 100
    params: {}
    condition: "len(result) > 0"
    summary_template: "发现 {count} 台设备超过30天未上线"
```

**Pydantic 模型** (`monitor_agent/models.py`)：

```python
class MonitorRule(BaseModel):
    name: str
    description: str
    interval_seconds: int = 300
    enabled: bool = True
    severity: Literal["info", "warning", "critical"] = "info"
    sql: str
    params: dict[str, Any] = {}
    condition: str = "len(result) > 0"
    summary_template: str = ""

class MonitorRulesConfig(BaseModel):
    version: str = "0.1"
    enabled: bool = True
    default_interval_seconds: int = 300
    max_events_per_rule: int = 100
    dedup_window_seconds: int = 300
    rules: list[MonitorRule] = []

class MonitorEvent(BaseModel):
    id: str
    rule_name: str
    severity: str
    triggered_at: datetime
    result: list[dict[str, Any]]
    prev_result: list[dict[str, Any]] | None = None
    summary: str = ""
    fingerprint: str = ""       # 用于去重
```

---

### 步骤 3：实现监控调度器核心

**目标**：实现基于 APScheduler 的定时轮询调度器，支持配置驱动的规则加载和执行。

**新增文件**：
- `agent_backend/monitor_agent/__init__.py`
- `agent_backend/monitor_agent/scheduler.py` — 调度器核心
- `agent_backend/monitor_agent/executor.py` — 规则执行器
- `agent_backend/monitor_agent/event_store.py` — 事件存储
- `agent_backend/monitor_agent/config_loader.py` — 配置加载器

**scheduler.py 核心设计**：

```python
class MonitorScheduler:
    """监控调度器 - 独立运行状态和执行循环"""
    
    def __init__(self):
        self._scheduler: BackgroundScheduler | None = None
        self._enabled: bool = False
        self._rules: dict[str, MonitorRule] = {}
        self._executor: RuleExecutor | None = None
        self._event_store: EventStore | None = None
        self._prev_results: dict[str, list[dict]] = {}  # 上次查询结果
        self._lock = threading.Lock()
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    def start(self) -> None:
        """启动调度器"""
        config = load_monitor_rules()
        if not config.enabled:
            return
        
        self._enabled = True
        self._event_store = EventStore(max_per_rule=config.max_events_per_rule)
        self._executor = RuleExecutor()
        
        self._scheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60}
        )
        
        for rule in config.rules:
            if rule.enabled:
                self._rules[rule.name] = rule
                self._scheduler.add_job(
                    self._execute_rule,
                    "interval",
                    seconds=rule.interval_seconds,
                    id=f"monitor_{rule.name}",
                    args=[rule],
                    name=f"监控规则: {rule.description}",
                )
        
        self._scheduler.start()
    
    def shutdown(self) -> None:
        """关闭调度器"""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=True)
        if self._executor:
            self._executor.close()
        self._enabled = False
    
    def _execute_rule(self, rule: MonitorRule) -> None:
        """执行单条监控规则"""
        try:
            result = self._executor.execute(rule)
            prev_result = self._prev_results.get(rule.name)
            
            if self._evaluate_condition(rule, result, prev_result):
                event = self._create_event(rule, result, prev_result)
                if not self._event_store.is_duplicate(event, rule):
                    self._event_store.add(event)
            
            self._prev_results[rule.name] = result
        except Exception as e:
            logger.error(f"监控规则 {rule.name} 执行失败: {e}")
```

**executor.py 核心设计**：

```python
class RuleExecutor:
    """规则执行器 - 使用独立数据库连接池"""
    
    def __init__(self):
        self._engine: Engine | None = None
        self._lock = threading.Lock()
    
    def _get_engine(self) -> Engine:
        """获取或创建独立引擎（带连接池）"""
        if self._engine is None:
            with self._lock:
                if self._engine is None:
                    database_url = get_database_url()
                    self._engine = create_engine(
                        database_url,
                        pool_size=2,           # 监控只需小连接池
                        max_overflow=1,
                        pool_pre_ping=True,
                        pool_recycle=1800,
                        connect_args={"readonly": True}  # 只读事务
                    )
        return self._engine
    
    def execute(self, rule: MonitorRule) -> list[dict[str, Any]]:
        """执行规则SQL，返回结果"""
        engine = self._get_engine()
        with engine.connect() as conn:
            # 设置只读事务
            conn.execute(text("SET TRANSACTION READ ONLY"))
            result = conn.execute(text(rule.sql), rule.params)
            rows = result.mappings().all()
            return [dict(row) for row in rows]
    
    def close(self) -> None:
        """关闭连接池"""
        if self._engine:
            self._engine.dispose()
            self._engine = None
```

**event_store.py 核心设计**：

```python
class EventStore:
    """线程安全的事件存储"""
    
    def __init__(self, max_per_rule: int = 100):
        self._events: dict[str, deque[MonitorEvent]] = defaultdict(
            lambda: deque(maxlen=max_per_rule)
        )
        self._lock = threading.Lock()
        self._dedup_window: int = 300
    
    def add(self, event: MonitorEvent) -> None:
        with self._lock:
            self._events[event.rule_name].append(event)
    
    def is_duplicate(self, event: MonitorEvent, rule: MonitorRule) -> bool:
        """检查事件是否在去重窗口内重复"""
        with self._lock:
            for existing in self._events.get(event.rule_name, []):
                if (existing.fingerprint == event.fingerprint and
                    (event.triggered_at - existing.triggered_at).total_seconds() < self._dedup_window):
                    return True
        return False
    
    def get_events(self, rule_name: str | None = None, limit: int = 50) -> list[MonitorEvent]:
        with self._lock:
            if rule_name:
                return list(self._events.get(rule_name, []))[-limit:]
            all_events = []
            for events in self._events.values():
                all_events.extend(events)
            return sorted(all_events, key=lambda e: e.triggered_at, reverse=True)[:limit]
```

---

### 步骤 4：实现条件评估引擎

**目标**：支持灵活的条件表达式，避免硬编码判断逻辑。

**新增文件**：
- `agent_backend/monitor_agent/condition_eval.py` — 条件评估器

**设计思路**：使用安全的表达式求值（非 `eval`），支持内置函数和简单比较运算。

```python
class ConditionEvaluator:
    """安全条件评估器"""
    
    # 内置函数白名单
    BUILTIN_FUNCTIONS = {
        "len": len,
        "has_new_records": _has_new_records,  # 自定义：比较新旧结果
        "abs": abs,
        "str": str,
        "int": int,
        "float": float,
    }
    
    def evaluate(self, condition: str, result: list[dict], prev_result: list[dict] | None) -> bool:
        """安全评估条件表达式"""
        context = {
            "result": result,
            "prev_result": prev_result or [],
            "count": len(result),
            **self.BUILTIN_FUNCTIONS,
        }
        # 使用 ast.literal_eval 的安全替代方案
        # 或使用简单的 DSL 解析器
        ...
```

**支持的内置函数**：
- `len(result)` — 结果行数
- `has_new_records(result, prev_result, key)` — 基于指定key检测新记录
- `abs(a - b) > threshold` — 数值变化超过阈值

---

### 步骤 5：实现监控 API 接口

**目标**：提供监控状态查询和规则管理的 HTTP 接口。

**新增文件**：
- `agent_backend/api/v1/monitor.py` — API 路由

**API 设计**：

| 路径 | 方法 | 功能 |
|------|------|------|
| `/api/v1/monitor/status` | GET | 获取调度器状态（是否运行、已注册规则数、最近执行时间） |
| `/api/v1/monitor/events` | GET | 获取事件列表（支持 `?rule_name=&limit=&severity=` 过滤） |
| `/api/v1/monitor/rules` | GET | 获取所有规则及其状态 |
| `/api/v1/monitor/rules/{name}/toggle` | POST | 启用/禁用指定规则 |

**路由注册**：修改 `agent_backend/api/routes.py`，添加 monitor_router。

---

### 步骤 6：实现 LLM 总结能力

**目标**：监控智能体拥有独立的 system prompt，可对事件进行自然语言总结。

**新增文件**：
- `agent_backend/monitor_agent/summarizer.py` — LLM 总结器

**独立 System Prompt**：

```
你是一个IT运维监控助手。你的职责是分析监控事件数据，生成简洁、专业的总结报告。

要求：
1. 用自然语言描述发生了什么
2. 指出需要关注的关键信息
3. 如果有异常，给出可能的原因和建议
4. 语言简洁，重点突出
5. 使用中文回复
```

**调用方式**：复用现有 `OllamaChatClient.chat_complete()`，传入独立的 system prompt。

---

### 步骤 7：环境变量与配置集成

**目标**：在 `.env` 和 `docker-compose.yml` 中添加监控相关配置。

**新增环境变量**：

```env
# 监控智能体配置
MONITOR_ENABLED=true                    # 是否启用监控智能体
MONITOR_RULES_CONFIG=./agent_backend/configs/monitor_rules.yaml  # 规则配置文件路径
MONITOR_DB_POOL_SIZE=2                  # 监控独立连接池大小
MONITOR_DEFAULT_INTERVAL=300            # 默认轮询周期（秒）
```

**docker-compose.yml 变更**：在 backend 服务的 environment 中添加上述变量。

---

### 步骤 8：前端展示接口预留

**目标**：为后续前端开发预留数据接口，当前阶段仅实现后端 API。

前端展示窗口（后续开发）将展示三项重要监控指标：
1. 在线客户端数量统计
2. 设备资产变化检测
3. 长期未上线客户端

权重计算功能暂不实现，API 返回所有事件数据，前端自行决定展示优先级。

---

## 四、新增文件清单

```
agent_backend/
├── monitor_agent/                    # 监控智能体模块（新增）
│   ├── __init__.py                   # 模块入口
│   ├── models.py                     # Pydantic 模型定义
│   ├── scheduler.py                  # APScheduler 调度器
│   ├── executor.py                   # 规则执行器（独立连接池）
│   ├── event_store.py                # 事件存储（线程安全）
│   ├── condition_eval.py             # 条件评估引擎
│   ├── summarizer.py                 # LLM 总结器
│   └── config_loader.py              # 监控规则配置加载
├── configs/
│   ├── schema_metadata.yaml          # 现有（后续补充 SQL 配置）
│   └── monitor_rules.yaml            # 监控规则配置（新增）
└── api/v1/
    └── monitor.py                    # 监控 API 路由（新增）
```

**修改文件清单**：

| 文件 | 变更内容 |
|------|----------|
| `requirements.txt` | 添加 `APScheduler>=3.10` |
| `agent_backend/main.py` | 重构为 `lifespan` 模式，集成监控调度器启停 |
| `agent_backend/api/routes.py` | 添加 monitor_router |
| `.env.example` | 添加监控相关环境变量 |
| `docker-compose.yml` | 添加监控环境变量 |

---

## 五、线程安全与事务隔离方案

### 5.1 数据库连接隔离

```
聊天智能体                          监控智能体
    │                                  │
    ▼                                  ▼
ConnectionManager                   RuleExecutor
(单例模式)                          (独立实例)
    │                                  │
    ▼                                  ▼
会话级单连接                         SQLAlchemy Engine
session_id → Engine+Connection      pool_size=2, max_overflow=1
    │                                  │
    ▼                                  ▼
每次请求获取/复用连接                每次执行从池中获取
60分钟过期清理                       执行完归还池
```

**关键隔离措施**：
1. 监控智能体使用独立的 `Engine` 实例，与 `ConnectionManager` 完全无关
2. 监控连接池极小（2+1），避免占用过多数据库连接
3. 监控查询使用只读事务（`SET TRANSACTION READ ONLY`）
4. 两者共享同一 `database_url`，但连接池各自管理

### 5.2 共享状态保护

| 共享资源 | 保护机制 |
|----------|----------|
| `EventStore._events` | `threading.Lock` 保护所有读写 |
| `MonitorScheduler._prev_results` | 调度器内部锁保护 |
| `RuleExecutor._engine` | 双重检查锁定（懒初始化） |
| `monitor_rules.yaml` 配置 | 启动时一次性加载，运行时只读 |

---

## 六、监控规则配置方案（避免硬编码）

### 6.1 配置驱动架构

```
monitor_rules.yaml (配置文件)
        │
        ▼
config_loader.py (加载+校验)
        │
        ▼
Pydantic MonitorRulesConfig (强类型)
        │
        ▼
MonitorScheduler (注册定时任务)
        │
        ▼
RuleExecutor (执行SQL + 评估条件)
```

### 6.2 规则扩展方式

新增监控项只需在 `monitor_rules.yaml` 中添加一条规则，无需修改代码：

```yaml
rules:
  - name: new_monitor_item
    description: "新的监控项"
    interval_seconds: 300
    enabled: true
    severity: info
    sql: "SELECT ..."
    condition: "len(result) > 0"
    summary_template: "发现 {count} 条新记录"
```

### 6.3 SQL 来源策略

当前阶段 SQL 直接写在 `monitor_rules.yaml` 中。待 `schema_metadata.yml` 中 SQL 配置补全后，可切换为引用模式：

```yaml
# 当前阶段：直接写SQL
sql: "SELECT COUNT(*) as count FROM onlineinfo"

# 后续阶段：引用 schema_metadata.yml 中的 query_pattern
sql_ref: "shutdown_online_machines"   # 引用 query_patterns 中的模板名
```

---

## 七、多智能体方案适用性建议

### 7.1 当前方案：同进程多智能体

```
FastAPI 进程
├── Chat Agent (请求驱动，被动响应)
└── Monitor Agent (定时驱动，主动巡检)
```

**适用场景**：单机部署、中小规模、智能体间需要共享内存状态。

**优势**：
- 部署简单，无需额外进程/容器
- 共享 LLM 客户端和配置加载器
- 内存中直接交换事件数据

**局限**：
- 监控智能体的故障可能影响聊天智能体
- 无法独立扩缩容

### 7.2 未来演进：独立进程/容器

当监控规模增长时，可将 `MonitorAgent` 拆分为独立服务：

```
┌──────────────┐    ┌──────────────┐
│  Chat Agent  │    │ Monitor Agent │
│  (FastAPI)   │    │  (独立进程)    │
│  端口 8000   │    │  端口 8001    │
└──────┬───────┘    └──────┬───────┘
       │                   │
       └───────┬───────────┘
               │
        ┌──────▼──────┐
        │   MySQL/PG  │
        └─────────────┘
```

**当前设计已为此预留空间**：
- `monitor_agent/` 模块完全自包含，可独立提取为服务
- 使用独立的数据库连接池，无状态耦合
- API 接口已独立定义，前端通过不同路径访问

### 7.3 建议

**当前阶段推荐同进程方案**，理由：
1. 项目处于初期，监控规则较少，资源消耗可控
2. 部署运维成本低，Docker 单容器即可运行
3. 智能体间共享 LLM 客户端，减少 Ollama 并发压力
4. 模块解耦设计确保未来可平滑拆分

---

## 八、实施优先级与里程碑

| 优先级 | 步骤 | 说明 |
|--------|------|------|
| P0 | 步骤1：依赖与生命周期升级 | 基础设施，所有后续步骤依赖 |
| P0 | 步骤2：监控规则配置体系 | 核心设计，定义数据模型 |
| P0 | 步骤3：调度器核心实现 | 核心功能，定时轮询机制 |
| P0 | 步骤4：条件评估引擎 | 核心功能，触发判断逻辑 |
| P1 | 步骤5：监控 API 接口 | 对外暴露，前端集成基础 |
| P1 | 步骤7：环境变量与配置集成 | 部署配置 |
| P2 | 步骤6：LLM 总结能力 | 增强功能，可后续迭代 |
| P2 | 步骤8：前端展示预留 | 后续开发 |

---

## 九、验证方案

### 9.1 单元测试

- `test_condition_eval.py`：条件表达式评估
- `test_event_store.py`：事件存储与去重
- `test_config_loader.py`：规则配置加载与校验

### 9.2 集成测试

- 启动 FastAPI 应用，验证调度器自动启动
- 访问 `/api/v1/monitor/status` 确认调度器状态
- 访问 `/api/v1/monitor/events` 确认事件生成
- 触发规则启停，验证动态控制

### 9.3 压力测试

- 模拟多条规则同时执行，验证线程安全
- 验证数据库连接池在监控查询下的稳定性
- 验证事件存储在高频触发下的内存占用
