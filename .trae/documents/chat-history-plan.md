# 聊天历史记录功能 — 实施方案（v2 修订版）

## 一、现状分析

### 当前架构
- **前端**: Vue 3 + Vite + TailwindCSS，消息仅存于内存 `messages` ref，刷新即丢失
- **后端**: FastAPI + LangGraph，SSE 流式输出，无消息持久化
- **侧栏**: App.vue 中硬编码"暂无历史会话"占位，无数据源和交互
- **标题**: header 硬编码"新对话"，无动态标题
- **session_id**: 仅用于管理 SQL 查询的数据库连接复用（ConnectionManager），与聊天记录无关

### 缺失功能
| 功能 | 状态 |
|------|------|
| 消息持久化存储 | ❌ 完全缺失 |
| 会话列表/历史记录 | ❌ 侧栏空壳 |
| 会话标题自动生成 | ❌ 缺失 |
| 会话标题手动重命名 | ❌ 缺失 |
| 会话切换/恢复 | ❌ 缺失 |
| 侧栏独立组件 | ❌ 逻辑内嵌 App.vue |

---

## 二、数据库选型分析

### 方案对比

| 维度 | SQLite | MySQL/PostgreSQL | JSON 文件 |
|------|--------|------------------|-----------|
| 部署复杂度 | ✅ 零依赖，Python 内置 | ❌ 需额外服务 | ✅ 零依赖 |
| 查询能力 | ✅ 完整 SQL | ✅ 完整 SQL | ❌ 需全量加载 |
| 并发写入 | ⚠️ 单写者（对本场景足够） | ✅ 高并发 | ❌ 需加锁 |
| 数据量支持 | ✅ TB 级（远超需求） | ✅ 无限 | ❌ 性能差 |
| 备份迁移 | ✅ 单文件复制 | ⚠️ 需导出工具 | ✅ 单文件复制 |
| Docker 兼容 | ✅ Volume 挂载即可 | ❌ 需额外容器 | ✅ Volume 挂载 |
| 项目已有依赖 | ✅ SQLAlchemy 已在 requirements.txt | ⚠️ 已有但连的是外部库 | ✅ 无需依赖 |

### 结论：选择 SQLite

**理由**：
1. 用户明确倾向本地数据库，SQLite 是本地嵌入式数据库的最佳选择
2. 本项目是单用户/小团队使用的桌面 Agent，SQLite 的单写者限制完全不是问题
3. 项目已依赖 SQLAlchemy，可复用该依赖引入 ORM 模式（注意：现有代码仅使用 SQLAlchemy 原始 SQL 执行，本方案将引入全新的 ORM 使用模式，两者独立运行互不干扰）
4. 零运维成本，无需额外 Docker 容器
5. 数据文件随 Docker Volume 持久化，备份简单

---

## 三、核心概念澄清：session_id vs conversation_id

> **v2 修订重点**：明确区分两个完全不同的 ID 概念

| 维度 | session_id（现有） | conversation_id（新增） |
|------|-------------------|----------------------|
| 用途 | 管理**外部 MySQL 数据库连接**的复用 | 标识**聊天历史记录**的会话 |
| 生命周期 | 一次对话期间，调 /chat/end 即关闭 | 永久持久化，直到用户删除 |
| 生成方 | ConnectionManager.generate_session_id() | 后端 conversations API 创建 |
| 存储位置 | 内存（ConnectionManager._connections 字典） | SQLite conversations 表 |
| 关联关系 | 与 SQL 查询工具绑定 | 与聊天消息绑定 |
| 前端变量 | currentSessionId | currentConversationId |

**关键设计决策**：
- 两个 ID **独立生成、独立传递、互不关联**
- 前端同时维护 `currentSessionId` 和 `currentConversationId`
- ChatRequest 中两个字段并存：`session_id`（连接复用）+ `conversation_id`（历史记录）
- 切换会话时，session_id 会重新生成（新连接），conversation_id 沿用已有值

---

## 四、数据模型设计

### ER 图

```
┌──────────────────────┐       ┌──────────────────────────────┐
│   conversations      │       │         messages             │
├──────────────────────┤       ├──────────────────────────────┤
│ id (PK, TEXT, UUID)  │──1:N─→│ id (PK, INTEGER, AUTO)      │
│ title (TEXT)         │       │ conversation_id (FK, TEXT)   │
│ user_id (TEXT)       │       │ role (TEXT: user/assistant)  │
│ created_at (REAL)    │       │ content (TEXT)               │
│ updated_at (REAL)    │       │ intent (TEXT, nullable)      │
│ is_deleted (INTEGER) │       │ charts (TEXT, JSON, nullable)│
└──────────────────────┘       │ created_at (REAL)            │
                               └──────────────────────────────┘
```

### 表结构详细定义

**conversations 表**：
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | TEXT | PK | UUID 格式，**独立生成，不复用 session_id** |
| title | TEXT | NOT NULL, DEFAULT '新对话' | 会话标题，首条消息后自动更新，**支持用户手动重命名** |
| user_id | TEXT | NOT NULL, DEFAULT 'admin' | 用户标识，与现有 lognum 对应 |
| created_at | REAL | NOT NULL | 创建时间戳（time.time()） |
| updated_at | REAL | NOT NULL | 最后更新时间戳 |
| is_deleted | INTEGER | NOT NULL, DEFAULT 0 | 软删除标记 |

**messages 表**：
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | 自增主键 |
| conversation_id | TEXT | FK → conversations.id | 所属会话 |
| role | TEXT | NOT NULL | user 或 assistant |
| content | TEXT | NOT NULL, DEFAULT '' | 消息文本内容 |
| intent | TEXT | NULLABLE | 意图标签（sql/rag/agent） |
| charts | TEXT | NULLABLE | 图表配置 JSON 字符串 |
| created_at | REAL | NOT NULL | 创建时间戳 |

### 设计要点
- **conversation_id 独立 UUID**：不复用 session_id，两者概念完全不同
- **charts 存为 JSON 字符串**：SQLite 无原生 JSON 类型，但支持 JSON 函数查询
- **软删除**：`is_deleted` 标记，避免误删数据
- **时间戳用 REAL**：SQLite 推荐的 Unix 时间戳格式，便于排序和范围查询
- **user_id**：预留多用户扩展能力，当前默认 'admin'
- **数据库迁移**：初期通过 `create_all` 自动建表，不引入 Alembic。当表结构需要变更时，在 `database.py` 中编写版本化迁移函数（手动 ALTER TABLE），预留升级路径

---

## 五、后端实施方案

### 5.1 新增文件清单

```
agent_backend/
├── db/                          # 新增：本地数据库模块
│   ├── __init__.py
│   ├── database.py              # SQLite 连接管理 + 表初始化
│   └── models.py                # SQLAlchemy ORM 模型
├── api/v1/
│   └── conversations.py         # 新增：会话 CRUD API
```

### 5.2 数据库模块 (`db/database.py`)

核心职责：
- SQLite 连接管理（aiosqlite 异步驱动）
- 应用启动时自动建表
- 数据库文件路径配置（支持 Docker Volume 和本地开发）
- **独立 Base 和 engine**，与 ConnectionManager 的 engine 互不干扰

```python
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

SQLITE_DB_PATH = os.environ.get("CHAT_DB_PATH", "data/chat_history.db")

# 跨平台路径处理（Windows 反斜杠兼容）
db_path = Path(SQLITE_DB_PATH).resolve()
engine = create_async_engine(
    f"sqlite+aiosqlite:///{db_path.as_posix()}",
    echo=False,
    connect_args={"check_same_thread": False}
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
```

### 5.3 ORM 模型 (`db/models.py`)

> 注意：这是项目首次引入 SQLAlchemy ORM 模式。现有代码使用 SQLAlchemy 仅做原始 SQL 执行（create_engine + text() + Connection.execute），本模块使用全新的 DeclarativeBase + async_sessionmaker + relationship，两者独立运行互不干扰。

```python
from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False, default="新对话")
    user_id = Column(String, nullable=False, default="admin")
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)
    is_deleted = Column(Integer, nullable=False, default=0)
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False, default="")
    intent = Column(String, nullable=True)
    charts = Column(Text, nullable=True)
    created_at = Column(Float, nullable=False)
    conversation = relationship("Conversation", back_populates="messages")
```

### 5.4 会话 API (`api/v1/conversations.py`)

| 端点 | 方法 | 功能 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/conversations` | GET | 获取会话列表（按更新时间倒序） | query: user_id, limit, offset | `{items: [...], total: int}` |
| `/api/v1/conversations/{id}` | GET | 获取单个会话详情+消息列表 | - | `{id, title, messages: [...]}` |
| `/api/v1/conversations` | POST | 创建新会话 | `{user_id?}` | `{id, title, created_at}` |
| `/api/v1/conversations/{id}/title` | PUT | 更新会话标题（**支持重命名**） | `{title}` | `{success: bool, title: str}` |
| `/api/v1/conversations/{id}` | DELETE | 删除会话（软删除） | - | `{success: bool}` |

### 5.5 修改现有文件

**`chat.py`** — 在 SSE 流式响应中增加消息持久化：

```
修改点：
1. ChatRequest 新增 conversation_id: str | None = None 字段
2. generate() 中：如果 conversation_id 存在，保存 user message 到 messages 表
3. generate() 中：使用 try/finally 机制，在 finally 中保存 assistant 消息（无论正常完成/异常/中断）
4. 首条消息后：自动生成标题（取用户消息前30字）并更新 conversation.title
5. 每次消息后：更新 conversation.updated_at
6. 如果 conversation_id 不存在（首条消息），在 generate() 中创建 conversation 记录
7. 后端自行从数据库加载历史消息，不再依赖前端传 history
```

ChatRequest 变更：
```python
class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)  # 保留兼容，但后端优先从DB加载
    images_base64: list[str] | None = None
    lognum: str = Field(default="admin")
    token: str | None = None
    session_id: str | None = None          # 现有：连接复用
    conversation_id: str | None = None     # 新增：历史记录关联
```

generate() 核心逻辑：
```python
async def generate():
    assistant_content = ""  # 累积 assistant 回复内容
    conversation_id = req.conversation_id

    # 如果没有 conversation_id，创建新会话
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        # 创建 conversation 记录 + 保存 user message
        await create_conversation_with_message(conversation_id, req.question, req.lognum)
        # 自动生成标题
        await update_conversation_title(conversation_id, generate_title(req.question))
    else:
        # 保存 user message 到已有会话
        await save_message(conversation_id, "user", req.question)
        # 后端从 DB 加载历史消息构建 AgentState
        history_messages = await load_conversation_messages(conversation_id)

    yield _sse_event("start", {"intent": "agent", "session_id": session_id, "conversation_id": conversation_id})

    try:
        async for sse_event in stream_graph_response(graph, initial_state):
            # 从 delta 事件中提取 content 累加
            assistant_content += extract_delta_content(sse_event)
            yield sse_event
        yield _sse_event("done", {"route": "agent", "session_id": session_id, "conversation_id": conversation_id})
    except Exception as e:
        yield _sse_event("error", {"error": "..."})
    finally:
        # 无论正常完成/异常/中断，都保存已有内容
        if assistant_content:
            await save_message(conversation_id, "assistant", assistant_content, intent=...)
        await update_conversation_timestamp(conversation_id)
```

**`routes.py`** — 注册新路由：
```python
from agent_backend.api.v1.conversations import router as conversations_router
router.include_router(conversations_router, prefix="/api/v1")
```

**`main.py`** — 使用 lifespan 替代弃用 API：

> v2 修订：使用 FastAPI 推荐的 lifespan 上下文管理器，替代已弃用的 on_event，同时将现有 shutdown 逻辑迁移到 lifespan 中

```python
from contextlib import asynccontextmanager
from agent_backend.db.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await init_db()
    yield
    # shutdown
    conn_manager = get_connection_manager()
    conn_manager.shutdown()

app = FastAPI(title="desk-agent-backend", lifespan=lifespan)
# 移除原有的 @app.on_event("shutdown")
```

**`requirements.txt`** — 新增依赖：
```
aiosqlite>=0.20
```

**`docker-compose.yml`** — 新增 Volume 挂载：
```yaml
volumes:
  - chat_data:/app/data    # 新增：SQLite 数据持久化
  # 注意：/app/data 与 /data 是两个不同的目录
  # /data — 用于文档挂载（docs, sql）
  # /app/data — 用于应用本地数据（SQLite 数据库文件）

volumes:
  qdrant_data:
    driver: local
  chat_data:                  # 新增
    driver: local
```

---

## 六、前端实施方案

### 6.1 新增/修改文件清单

```
agent_frontend/src/
├── api/
│   ├── chat.js              # 修改：增加 conversation_id 参数
│   └── conversations.js     # 新增：会话 CRUD API 封装
├── components/
│   ├── ChatBox.vue          # 修改：加载/保存消息逻辑
│   └── Sidebar.vue          # 新增：侧栏独立组件（从 App.vue 抽离）
├── App.vue                  # 修改：使用 Sidebar 组件，动态标题
└── composables/
    └── useConversations.js  # 新增：会话状态管理 composable（模块级单例）
```

### 6.2 会话状态管理 (`composables/useConversations.js`)

> v2 修订：使用模块级变量确保跨组件共享同一份状态

```javascript
import { ref, computed } from 'vue'

// 模块级变量 — 所有组件共享同一份状态（单例模式）
const conversations = ref([])
const currentConversationId = ref(null)

const currentTitle = computed(() => {
  const conv = conversations.value.find(c => c.id === currentConversationId.value)
  return conv?.title || '新对话'
})

export function useConversations() {
  async function loadConversations() { /* GET /api/v1/conversations */ }
  async function createConversation() { /* POST /api/v1/conversations */ }
  async function switchConversation(id) { /* GET /api/v1/conversations/{id} + 设置 currentConversationId */ }
  async function deleteConversation(id) { /* DELETE /api/v1/conversations/{id} */ }
  async function renameConversation(id, title) { /* PUT /api/v1/conversations/{id}/title */ }

  return {
    conversations,
    currentConversationId,
    currentTitle,
    loadConversations,
    createConversation,
    switchConversation,
    deleteConversation,
    renameConversation,
  }
}
```

### 6.3 侧栏组件 (`components/Sidebar.vue`)

从 App.vue 抽离侧栏逻辑，增加会话列表交互：

```
┌──────────────────────────┐
│  阳途智能助手      [收起] │
│  ┌────────────────────┐  │
│  │ ＋ 开启新会话       │  │
│  └────────────────────┘  │
│  历史会话                │
│  ┌────────────────────┐  │
│  │ 📋 苹果提醒iPhone...│  │ ← 当前选中高亮
│  │ 📋 查看客户端在线...│  │
│  │ 📋 今日远程操作...  │  │
│  │ 📋 老旧资产设备...  │  │
│  └────────────────────┘  │
└──────────────────────────┘
```

交互细节：
- 点击会话项 → 切换到该会话，加载消息
- 当前会话高亮显示
- 鼠标悬停显示操作按钮（删除 + 重命名）
- **双击标题 → 进入编辑模式 → 输入新标题 → Enter 确认 / Esc 取消**（重命名功能）
- 会话列表按 updated_at 倒序排列
- 标题过长时截断显示（CSS text-overflow: ellipsis）

### 6.4 ChatBox.vue 修改

```
修改点：
1. 新增 props: conversationId（从 App.vue 传入）
2. 新增 emit: conversation-created(conversationId)（通知 App 新会话已创建）
3. sendMessage 中：传递 conversation_id 给后端，后端负责创建/关联 conversation
4. SSE start 事件中：接收 conversation_id（后端可能新建了 conversation）
5. SSE done 事件后：无需前端主动保存消息（后端已在 finally 中保存）
6. switchConversation 时：清空 messages，从后端加载历史消息
7. 移除底部"新对话"按钮（统一由侧栏操作）
```

### 6.5 App.vue 修改

```
修改点：
1. 引入 Sidebar 组件和 useConversations composable
2. header 标题改为动态：{{ currentTitle || '新对话' }}
3. 侧栏区域替换为 <Sidebar /> 组件
4. 会话切换时传递 conversationId 给 ChatBox
5. 监听 ChatBox 的 conversation-created 事件更新会话列表
```

### 6.6 API 封装 (`api/conversations.js`)

```javascript
const API_BASE = '/api/v1'

export async function getConversations(userId = 'admin', limit = 50, offset = 0) { ... }
export async function getConversation(id) { ... }
export async function createConversation(userId = 'admin') { ... }
export async function updateConversationTitle(id, title) { ... }
export async function deleteConversation(id) { ... }
```

### 6.7 chat.js 修改

```javascript
// sendChatMessage 参数新增 conversation_id
export async function sendChatMessage({
  question,
  history = [],
  images_base64 = null,
  lognum = 'admin',
  mode = 'auto',
  session_id = null,
  conversation_id = null,  // 新增
  onEvent,
}) {
  // body 中增加 conversation_id
  body: JSON.stringify({
    question,
    history,
    images_base64,
    lognum,
    mode,
    session_id,
    conversation_id,  // 新增
  }),
}
```

---

## 七、核心交互流程

### 7.1 新建对话流程（延迟创建策略）

> v2 修订：采用延迟创建策略，避免产生空会话记录

```
用户点击"开启新会话"
  → 前端仅重置本地状态（不调用后端）
  → currentConversationId = null
  → messages = []
  → header 标题显示"新对话"
  → 侧栏无新项出现
  → 等待用户实际发送第一条消息时才创建 conversation 记录
```

### 7.2 发送首条消息流程

```
用户输入"资讯：苹果三次提醒 iPhone 用户更新系统保安全"
  → 前端 POST /api/v1/chat（conversation_id = null）
  → 后端检测无 conversation_id，自动创建 conversation 记录
  → 后端保存 user message 到 messages 表
  → 后端自动更新 conversation.title = "苹果三次提醒iPhone用户更新系统保安全"（截取前30字）
  → SSE start 事件携带 conversation_id 返回前端
  → 前端设置 currentConversationId = 新 conversation_id
  → 前端刷新侧栏列表（该会话出现）
  → SSE 流式返回 assistant 回答
  → SSE done 后，后端在 finally 中保存 assistant message
  → 前端更新侧栏标题和 header 标题
```

### 7.3 后续消息流程

```
用户继续输入
  → 前端 POST /api/v1/chat（conversation_id = 当前会话 ID）
  → 后端保存 user message
  → 后端从 DB 加载历史消息构建 AgentState（不再依赖前端传 history）
  → SSE 流式返回
  → finally 中保存 assistant message + 更新 conversation.updated_at
  → 前端更新侧栏排序（该会话置顶）
```

### 7.4 切换会话流程

```
用户点击侧栏某历史会话
  → 前端调用 GET /api/v1/conversations/{id}
  → 后端返回 {id, title, messages: [...]}
  → 前端 currentConversationId = id
  → 前端 messages = 从后端加载的消息列表
  → header 标题更新为该会话标题
  → 侧栏高亮切换
```

### 7.5 页面刷新恢复流程

```
页面加载
  → 前端调用 GET /api/v1/conversations 获取会话列表
  → 侧栏渲染会话列表
  → 默认不加载任何会话的消息（显示欢迎页）
  → 用户点击某会话时才加载消息（按需加载，避免大量数据传输）
```

### 7.6 删除会话流程

```
用户悬停会话项 → 显示删除按钮 → 点击删除
  → 前端弹出确认提示
  → 确认后调用 DELETE /api/v1/conversations/{id}
  → 后端软删除（is_deleted = 1）
  → 前端从列表移除该项
  → 如果删除的是当前会话，重置为欢迎页
```

### 7.7 重命名会话标题流程（新增）

```
用户双击侧栏会话标题
  → 标题文本变为可编辑 input
  → input 预填当前标题，自动全选
  → 用户修改后按 Enter
  → 前端调用 PUT /api/v1/conversations/{id}/title {title: "新标题"}
  → 后端更新 conversation.title
  → 前端更新本地会话列表中的标题
  → 如果是当前会话，同步更新 header 标题
  → 按 Esc 取消编辑，恢复原标题
```

---

## 八、标题生成与重命名策略

### 自动生成规则
- 取用户首条消息内容
- 去除前缀关键词（如"资讯："、"查询："等）
- 截取前 30 个字符
- 超过 30 字加省略号

### 手动重命名规则
- 侧栏双击标题进入编辑模式
- 标题长度限制 1-50 字符
- 空标题不允许提交，恢复原标题
- 重命名后立即同步到 header 标题

---

## 九、Docker 部署适配

### docker-compose.yml 修改

```yaml
backend:
  volumes:
    # ... 现有挂载 ...
    - chat_data:/app/data    # 新增：SQLite 数据持久化
    # 注意：/app/data 与 /data 是两个不同的目录
    # /data — 用于文档挂载（docs, sql），由 HOST_DOCS_DIR/HOST_SQL_DIR 映射
    # /app/data — 用于应用本地数据（SQLite 数据库文件），由 chat_data volume 管理

volumes:
  qdrant_data:
    driver: local
  chat_data:                  # 新增
    driver: local
```

### Dockerfile.backend 修改

```dockerfile
# 确保 data 目录存在
RUN mkdir -p /data/docs /app/.qdrant_local /app/data
```

### 环境变量

```yaml
- CHAT_DB_PATH=${CHAT_DB_PATH:-/app/data/chat_history.db}
```

---

## 十、实施步骤（按顺序执行）

### 阶段一：后端数据层（5 步）
1. 新增 `aiosqlite` 依赖到 `requirements.txt`
2. 创建 `agent_backend/db/` 模块（`__init__.py`、`database.py`、`models.py`）
3. 创建 `agent_backend/api/v1/conversations.py`（会话 CRUD + 重命名 API）
4. 修改 `agent_backend/api/routes.py` 注册新路由
5. 修改 `agent_backend/main.py`，使用 lifespan 初始化数据库（同时迁移现有 shutdown 逻辑）

### 阶段二：后端消息持久化（2 步）
6. 修改 `agent_backend/api/v1/chat.py`，ChatRequest 新增 conversation_id，generate() 中实现消息保存（try/finally）和标题自动生成
7. 修改 Docker 配置（`docker-compose.yml`、`Dockerfile.backend`）

### 阶段三：前端会话管理（4 步）
8. 创建 `agent_frontend/src/api/conversations.js`（API 封装）
9. 创建 `agent_frontend/src/composables/useConversations.js`（模块级单例状态管理）
10. 创建 `agent_frontend/src/components/Sidebar.vue`（侧栏组件，含重命名交互）
11. 修改 `agent_frontend/src/App.vue`（集成 Sidebar + 动态标题）

### 阶段四：前端消息联动（2 步）
12. 修改 `agent_frontend/src/components/ChatBox.vue`（消息加载/会话切换/延迟创建）
13. 修改 `agent_frontend/src/api/chat.js`（传递 conversation_id）

### 阶段五：验证与收尾（1 步）
14. 端到端功能测试：新建对话 → 发消息 → 刷新恢复 → 切换会话 → 删除会话 → 重命名标题

---

## 十一、风险与注意事项

1. **SQLite 并发**：FastAPI 异步框架下需使用 aiosqlite，避免阻塞事件循环
2. **Docker 数据持久化**：必须通过 Volume 挂载 `/app/data`，否则容器重建数据丢失
3. **SSE 流中断保存**：使用 try/finally 机制，无论正常完成/异常/用户中断，都保存已接收的 assistant 消息内容
4. **标题更新时机**：首条消息发送后立即更新标题，不等待 AI 回复完成
5. **大量消息加载**：单个会话消息过多时考虑分页加载（初期可不做，预留接口）
6. **图片消息**：当前图片以 base64 传输，暂不持久化图片内容（仅保存文本消息），后续可扩展
7. **session_id 与 conversation_id 独立**：两者互不关联，前端同时维护，后端分别处理
8. **延迟创建空会话**：点击"新会话"不创建数据库记录，首条消息时才创建，避免空会话污染
9. **历史消息加载策略**：后端根据 conversation_id 从 DB 加载历史构建 AgentState，前端不再需要传完整 history（减少网络传输，更可靠）
10. **Windows 路径兼容**：SQLite 连接字符串使用 `Path.as_posix()` 处理反斜杠，确保跨平台兼容
