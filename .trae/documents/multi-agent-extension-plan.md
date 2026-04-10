# 多智能体扩展可行性调研与实施建议方案

> 基于 `d:\work_space\agent_project` 现有架构的系统性分析

---

## 一、现状架构总结

### 1.1 当前单智能体架构特征

| 维度           | 现状                                                         |
| -------------- | ------------------------------------------------------------ |
| **智能体数量** | 1 个（桌管智能体 desk-agent）                                |
| **API 入口**   | `POST /api/v1/chat`（统一 SSE 流式）                         |
| **意图路由**   | 关键词/正则分类 → SQL / RAG 二分流                           |
| **数据库连接** | 单一 `ConnectionManager` 单例，单一 `DATABASE_URL`           |
| **向量存储**   | 单一 Qdrant collection `desk_agent_docs`                     |
| **知识库路径** | `./data/desk-agent/docs` + `./data/desk-agent/sql`           |
| **配置体系**   | `.env` 环境变量 + `schema_metadata.yaml` + `prompt_config.yaml` |
| **前端**       | 单页 Vue 3 SPA，硬编码欢迎语 "桌管系统 AI 助手"              |
| **容器化**     | 单 backend 容器 + 单 frontend 容器 + 单 qdrant 容器          |

### 1.2 关键耦合点识别

1. **`config_helper.py`**：全局读取 `DATABASE_URL`，无 agent_id 参数
2. **`connection_manager.py`**：单例模式，仅支持一个数据库连接池
3. **`handlers.py`**：硬编码 "桌管系统AI助手" 提示词
4. **`ChatBox.vue`**：硬编码欢迎语
5. **`retrieval.py` → `get_rag_settings()`**：全局环境变量，无 agent 上下文
6. **`schema_metadata.yaml`**：单文件，无 agent 分区
7. **`prompt_config.yaml`**：单文件，无 agent 分区

---

## 二、智能体分类与配置调研分析

### 2.1 六大智能体架构适配性评估

| 智能体         | 核心能力          | 数据库需求         | 知识库需求        | 适配难度 | 说明                      |
| -------------- | ----------------- | ------------------ | ----------------- | -------- | ------------------------- |
| **桌管智能体** | Text-to-SQL + RAG | MySQL（peerlan5）  | 桌管操作文档      | ⭐ 已实现 | 当前系统即为此            |
| **运维智能体** | Text-to-SQL + RAG | 独立运维库         | 运维手册/排障文档 | ⭐⭐ 低    | 结构与桌管高度一致        |
| **工单智能体** | Text-to-SQL + RAG | 工单系统数据库     | 工单流程文档      | ⭐⭐ 低    | 结构与桌管高度一致        |
| **跨网智能体** | RAG 为主          | 可选（跨网配置库） | 跨网策略/操作文档 | ⭐⭐ 低    | 可能无 SQL 需求，更偏 RAG |
| **准入智能体** | Text-to-SQL + RAG | 准入控制数据库     | 准入策略文档      | ⭐⭐ 低    | 结构与桌管高度一致        |
| **资产智能体** | Text-to-SQL + RAG | 资产管理数据库     | 资产管理文档      | ⭐⭐ 低    | 结构与桌管高度一致        |

**结论**：六大智能体的核心能力模型高度一致（SQL + RAG），当前架构可完全复用，仅需实现配置隔离与动态路由。

### 2.2 独立向量数据库与知识库目录方案

#### 2.2.1 目录结构规划

```
data/
├── desk_agent/                    # 桌管智能体
│   ├── docs/                      # 知识库文档
│   │   ├── 移动端使用手册.docx
│   │   └── ...
│   └── sql/                       # SQL 示例
│       └── sql-example.md
├── ops_agent/                     # 运维智能体
│   ├── docs/
│   └── sql/
├── ticket_agent/                  # 工单智能体
│   ├── docs/
│   └── sql/
├── crossnet_agent/                # 跨网智能体
│   ├── docs/
│   └── sql/
├── access_agent/                  # 准入智能体
│   ├── docs/
│   └── sql/
└── asset_agent/                   # 资产智能体
    ├── docs/
    └── sql/
```

#### 2.2.2 Qdrant Collection 隔离策略

采用 **按智能体独立 Collection** 方案：

| 智能体     | 文档 Collection       | SQL Collection       |
| ---------- | --------------------- | -------------------- |
| 桌管智能体 | `desk_agent_docs`     | `desk_agent_sql`     |
| 运维智能体 | `ops_agent_docs`      | `ops_agent_sql`      |
| 工单智能体 | `ticket_agent_docs`   | `ticket_agent_sql`   |
| 跨网智能体 | `crossnet_agent_docs` | `crossnet_agent_sql` |
| 准入智能体 | `access_agent_docs`   | `access_agent_sql`   |
| 资产智能体 | `asset_agent_docs`    | `asset_agent_sql`    |

**选择理由**：
- Collection 级隔离确保检索范围精确，避免跨领域知识干扰
- 共享同一 Qdrant 实例，资源开销可控
- 每个智能体的 embedding 模型可独立配置（虽然当前统一使用 bge-small-zh）
- Collection 可独立删除/重建，运维灵活

#### 2.2.3 数据库连接隔离策略

每个智能体配置独立的数据库连接地址，`ConnectionManager` 改造为支持多数据库连接池：

```python
# 改造前：单一连接池
conn_manager.get_or_create_connection(session_id, database_url)

# 改造后：按 agent_id 隔离连接池
conn_manager.get_or_create_connection(session_id, agent_id="desk_agent")
```

内部实现：`_connections` 字典的 key 从 `session_id` 改为 `(agent_id, session_id)` 元组，每个 agent_id 对应独立的 `database_url`。

### 2.3 独立 Prompt 提示词外部配置方案

#### 2.3.1 当前问题

- `handlers.py` 中硬编码了 "你是一个专业且友好的桌管系统AI助手"
- `prompt_builder.py` 中硬编码了 SQL 生成系统提示词
- 欢迎语硬编码在前端 `ChatBox.vue` 中

#### 2.3.2 设计方案

每个智能体拥有独立的 `agent_config.yaml`，包含完整的提示词模板：

```yaml
# agent_configs/desk_agent.yaml 示例
agent:
  id: "desk_agent"
  name: "桌管智能体"
  description: "桌面管理系统智能问答助手"
  enabled: true
  icon: "🖥️"

welcome:
  message: |
    你好！我是桌管系统 AI 助手。我可以帮助你：
    - 查询设备资产信息
    - 了解策略配置方法
    - 排查常见问题
    - 分析数据统计
    
    请问有什么可以帮你的？

database:
  type: "mysql"
  host: "${DB_HOST}"
  port: "${DB_PORT}"
  name: "${DB_NAME}"
  user: "${DB_USER}"
  password: "${DB_PASSWORD}"
  # 或直接使用 url
  url: "${DATABASE_URL}"

knowledge:
  docs_dir: "./data/desk_agent/docs"
  sql_dir: "./data/desk_agent/sql"
  qdrant_collection_docs: "desk_agent_docs"
  qdrant_collection_sql: "desk_agent_sql"
  embedding_model: "BAAI/bge-small-zh-v1.5"
  hybrid_alpha: 0.7
  top_k: 5
  candidate_k: 30
  sql_top_k: 3
  sql_candidate_k: 15
  sql_hybrid_alpha: 0.8

prompts:
  system_prompt: "你是一个专业且友好的桌管系统AI助手，善于用自然语言总结数据库查询结果..."
  rag_system_prompt: "你是一个专业的AI助手，基于以下文档内容回答用户问题..."
  sql_answer_prompt: |
    你是一个专业且友好的桌管系统AI助手，需要基于数据库查询结果以人性化的方式回答用户问题。
    ...
  welcome_prompt: "你好！我是桌管系统 AI 助手。"

access:
  path_prefix: "/desk_agent"
  port: null  # null 表示使用路径后缀方案

schema_metadata: "./agent_backend/configs/desk_agent_schema_metadata.yaml"
prompt_config: "./agent_backend/configs/desk_agent_prompt_config.yaml"
```

**关键设计**：
- 支持环境变量插值 `${VAR_NAME}`，运行时解析
- 提示词模板支持 Jinja2 风格变量替换（如 `{{agent_name}}`）
- 配置文件热加载：监听文件变更，自动重载（可选）

---

## 三、智能体访问方式分析与选择

### 3.1 方案对比

| 维度                | 多端口方案                            | 路径后缀方案                                               |
| ------------------- | ------------------------------------- | ---------------------------------------------------------- |
| **架构示意**        | `localhost:3001`、`localhost:3002`... | `localhost:3000/desk_agent`、`localhost:3000/ops_agent`... |
| **进程模型**        | 每个智能体独立 uvicorn 进程           | 单进程，内部按路径路由                                     |
| **资源占用**        | 高（N 个进程 × N 套内存）             | 低（共享进程、共享 embedding 模型）                        |
| **隔离性**          | 强（进程级隔离）                      | 中（逻辑隔离，共享 GIL）                                   |
| **部署复杂度**      | 高（端口管理、进程监控）              | 低（单一入口）                                             |
| **前端适配**        | 每个智能体独立前端实例                | 单前端，动态切换                                           |
| **Nginx 配置**      | 多 upstream + 多 server block         | 单 upstream + location 路由                                |
| **Qdrant 连接**     | 各进程独立连接                        | 共享连接池                                                 |
| **Embedding 模型**  | 各进程独立加载（内存浪费）            | 共享单例（节省 ~500MB/进程）                               |
| **Docker 端口映射** | 多端口暴露                            | 单端口暴露                                                 |
| **横向扩展**        | 天然支持                              | 需改造                                                     |
| **故障隔离**        | 单智能体崩溃不影响其他                | 需额外异常隔离机制                                         |

### 3.2 决策：采用路径后缀方案

**核心理由**：

1. **资源效率**：当前项目使用本地 Ollama + FastEmbed，embedding 模型加载约 500MB 内存。6 个独立进程意味着额外 2.5GB+ 内存开销，对当前"适合当前规模"的单体架构不经济。

2. **架构一致性**：项目定位为"前后端分离的单体应用"，路径后缀方案与单体架构理念一致。

3. **共享资源优势**：Qdrant 连接池、Embedding 模型、Ollama 客户端均可共享，避免重复初始化。

4. **运维简洁性**：单一进程、单一端口、单一日志流，监控和排障更简单。

5. **渐进式演进**：未来如需独立部署，可将路径后缀方案平滑迁移为多端口方案（路由层不变，仅改变进程绑定）。

### 3.3 路径后缀方案详细设计

#### 3.3.1 API 路由结构

```
/api/v1/
├── agents/                          # 智能体管理
│   ├── GET /                        # 列出所有智能体及状态
│   └── GET /{agent_id}              # 获取单个智能体详情
├── {agent_id}/                      # 智能体命名空间
│   ├── POST /chat                   # 聊天（SSE）
│   ├── POST /chat/end               # 结束对话
│   ├── POST /sql/generate           # SQL 生成
│   ├── GET /metadata/summary        # Schema 元数据
│   ├── POST /rag/sync               # 文档同步
│   └── GET /rag/sync/{job_id}       # 同步状态
└── health                           # 全局健康检查
```

**示例**：
- `POST /api/v1/desk_agent/chat` → 桌管智能体聊天
- `POST /api/v1/ops_agent/chat` → 运维智能体聊天
- `GET /api/v1/agents` → 列出所有智能体

#### 3.3.2 向后兼容

保留 `/api/v1/chat` 作为默认路由，指向配置中的 `DEFAULT_AGENT`（默认 `desk_agent`），确保现有客户端不受影响。

#### 3.3.3 智能体欢迎内容配置读取机制

**后端**：
- 新增 `GET /api/v1/{agent_id}/welcome` 端点
- 从 `agent_config.yaml` 的 `welcome.message` 字段读取
- 支持动态变量插值（如 `{{user_name}}`）

**前端**：
- 页面加载时，根据 URL 路径（如 `/desk_agent`）确定当前智能体
- 调用 `GET /api/v1/{agent_id}/welcome` 获取欢迎语
- 动态渲染 header 标题、描述和欢迎消息

#### 3.3.4 前端路由设计

```
/                           → 重定向到 /desk_agent
/desk_agent                 → 桌管智能体
/ops_agent                  → 运维智能体
/ticket_agent               → 工单智能体
/crossnet_agent             → 跨网智能体
/access_agent               → 准入智能体
/asset_agent                → 资产智能体
```

前端使用 Vue Router，每个路径对应同一个 `ChatBox` 组件，但传入不同的 `agentId` prop。

---

## 四、容器化与进程架构设计

### 4.1 单容器多智能体资源分配与隔离策略

#### 4.1.1 资源分配

| 资源                     | 策略                 | 说明                                  |
| ------------------------ | -------------------- | ------------------------------------- |
| **CPU**                  | 协程级共享，无需分配 | FastAPI async 天然支持                |
| **内存 - Embedding**     | 全局单例共享         | 6 智能体共享 1 个 EmbeddingModel 实例 |
| **内存 - Qdrant 客户端** | 全局单例共享         | 共享 1 个 Qdrant 客户端连接           |
| **内存 - LLM 客户端**    | 全局单例共享         | 共享 OllamaChatClient                 |
| **内存 - DB 连接池**     | 按 agent_id 隔离     | 每个 agent 独立连接池，避免跨库串连   |
| **内存 - 配置**          | 按需加载             | AgentConfig 按 agent_id 缓存          |

#### 4.1.2 隔离策略

```python
class AgentContext:
    """智能体运行时上下文 - 请求级别的隔离"""
    agent_id: str
    config: AgentConfig
    db_url: str
    qdrant_collection_docs: str
    qdrant_collection_sql: str
    schema_metadata: dict  # 含 display_fields（替代原 prompt_config）
```

- **请求级隔离**：每个 HTTP 请求通过 `agent_id` 获取对应的 `AgentContext`
- **配置级隔离**：各智能体的数据库连接、知识库路径、提示词完全独立
- **连接级隔离**：数据库连接池按 `agent_id` 隔离，避免跨库查询

### 4.2 多进程架构分析（暂不推荐）

**当前阶段不建议采用多进程架构**，理由如下：

1. **资源浪费**：每个进程需独立加载 embedding 模型（~500MB），6 进程额外消耗 ~2.5GB
2. **管理复杂**：需引入进程管理器（supervisord / gunicorn），增加运维复杂度
3. **共享困难**：Qdrant 客户端、Embedding 模型跨进程共享需 IPC 机制
4. **规模不匹配**：当前定位为"适合当前规模的单体应用"

**未来演进路径**：若单进程性能不足，可按以下优先级扩展：
1. **垂直扩展**：增加容器 CPU/内存
2. **读写分离**：将 RAG 文档同步拆为独立 worker
3. **智能体分组**：高频智能体独立进程，低频智能体共享进程
4. **微服务化**：完全拆分为独立服务

### 4.3 智能体启用/禁用配置开关机制

#### 4.3.1 自动发现机制（零代码新增智能体）

**核心设计**：取消 `agent_registry.yaml`，改为**目录扫描自动发现**。`agent_configs/` 目录下的每个 `.yaml` 文件即为一个智能体，文件名即 `agent_id`。

**新增第7个智能体的操作流程**：

```
1. 在 agent_configs/ 目录下新建 cloud_desktop_agent.yaml
2. 填写配置（enabled: true、数据库、提示词等）
3. 在 data/ 目录下创建 cloud_desktop_agent/docs/ 和 sql/
4. 重启服务（或调用热重载 API）
→ 智能体自动注册，前端自动展示，API 自动可用
```

**无需修改任何其他文件**，无需在注册表中手动添加条目。

```python
class AgentRegistry:
    """智能体注册中心 - 基于目录自动发现"""
    
    CONFIG_DIR = "./agent_backend/configs/agent_configs"
    
    def __init__(self):
        self._agents: dict[str, AgentConfig] = {}
        self._discover_agents()
    
    def _discover_agents(self):
        """扫描 agent_configs/ 目录，自动发现所有智能体"""
        config_dir = Path(self.CONFIG_DIR)
        if not config_dir.exists():
            return
        
        for yaml_file in sorted(config_dir.glob("*.yaml")):
            agent_id = yaml_file.stem  # 文件名即 agent_id
            try:
                config = self._load_agent_config(yaml_file)
                self._agents[agent_id] = config
                status = "✅ 启用" if config.agent.enabled else "⏸️ 禁用"
                logger.info(f"{status} 智能体: {agent_id} ({config.agent.name})")
            except Exception as e:
                logger.error(f"❌ 加载智能体配置失败: {agent_id} - {e}")
    
    def get_agent(self, agent_id: str) -> AgentConfig:
        if agent_id not in self._agents:
            raise AgentNotFoundError(agent_id)
        config = self._agents[agent_id]
        if not config.agent.enabled:
            raise AgentDisabledError(agent_id)
        return config
    
    @property
    def enabled_agents(self) -> list[str]:
        return [aid for aid, cfg in self._agents.items() if cfg.agent.enabled]
    
    def list_agents(self, include_disabled: bool = False) -> list[AgentInfo]:
        ...
    
    def reload(self):
        """热重载 - 重新扫描目录"""
        self._agents.clear()
        self._discover_agents()
```

**关键设计**：
- `agent_id` = YAML 文件名（不含扩展名），如 `desk_agent.yaml` → `desk_agent`
- `enabled` 字段在每个 YAML 文件的 `agent.enabled` 中控制
- 启动时仅加载 `enabled: true` 的智能体配置
- 禁用的智能体访问时返回 `403 Agent Disabled`
- `GET /api/v1/agents` 端点返回所有智能体及启用状态

#### 4.3.2 前端同步机制

- 前端启动时调用 `GET /api/v1/agents` 获取可用智能体列表
- 仅展示 `enabled: true` 的智能体
- 侧边栏/标签页动态渲染，禁用的智能体不显示
- 若当前访问的智能体被禁用，自动重定向到默认智能体

---

## 五、智能体配置文件体系设计

### 5.1 配置文件层次结构

```
agent_backend/
├── configs/
│   ├── agent_configs/                   # 各智能体独立配置（自动发现目录）
│   │   ├── desk_agent.yaml              # 桌管智能体配置
│   │   ├── ops_agent.yaml               # 运维智能体配置
│   │   ├── ticket_agent.yaml            # 工单智能体配置
│   │   ├── crossnet_agent.yaml          # 跨网智能体配置
│   │   ├── access_agent.yaml            # 准入智能体配置
│   │   ├── asset_agent.yaml             # 资产智能体配置
│   │   └── cloud_desktop_agent.yaml     # 云桌面智能体（随时可新增）
│   ├── desk_agent_schema_metadata.yaml  # 桌管 Schema 元数据（含展示配置）
│   ├── ops_agent_schema_metadata.yaml   # 运维 Schema 元数据（含展示配置）
│   └── ...                              # 其他智能体 Schema 元数据
├── .env                                 # 全局环境变量（保留）
```

**关键变化**：
- ❌ 取消 `agent_registry.yaml` → 改为目录扫描自动发现
- ❌ 取消 `prompt_config.yaml` → 合并到 `schema_metadata.yaml` 的 `display_fields` 中
- 每个智能体仅需 **2 个配置文件**：`{agent_id}.yaml` + `{agent_id}_schema_metadata.yaml`

### 5.2 统一配置文件格式（AgentConfig）

每个智能体的 YAML 配置文件包含以下完整结构：

```yaml
# ==================== 智能体基本信息 ====================
agent:
  id: "desk_agent"                    # 唯一标识，必须与文件名一致
  name: "桌管智能体"                   # 显示名称
  description: "桌面管理系统智能问答助手" # 描述
  enabled: true                       # 启用状态（核心开关）
  icon: "🖥️"                          # 前端图标
  order: 1                            # 前端展示排序
  tags: ["桌面管理", "设备查询"]        # 标签（可选）

# ==================== 欢迎内容 ====================
welcome:
  message: |
    你好！我是桌管系统 AI 助手。我可以帮助你：
    - 查询设备资产信息
    - 了解策略配置方法
    - 排查常见问题
    - 分析数据统计
    
    请问有什么可以帮你的？
  suggestions:                        # 快捷提问建议（可选）
    - "查询192.168.1.100的设备信息"
    - "如何设置移动端权限"
    - "统计各部门在线设备数"

# ==================== 数据库连接参数 ====================
database:
  type: "mysql"                       # mysql / postgresql
  host: "${DESK_DB_HOST}"             # 支持环境变量插值
  port: "${DESK_DB_PORT}"
  name: "${DESK_DB_NAME}"
  user: "${DESK_DB_USER}"
  password: "${DESK_DB_PASSWORD}"
  url: "${DESK_DATABASE_URL}"         # 优先使用完整 URL
  max_rows: 500                       # SQL 查询最大行数
  use_llm_sql: true                   # 是否启用 LLM 生成 SQL

# ==================== 知识库路径配置 ====================
knowledge:
  docs_dir: "./data/desk_agent/docs"           # 知识库文档目录
  sql_dir: "./data/desk_agent/sql"             # SQL 示例目录
  qdrant_collection_docs: "desk_agent_docs"    # 文档向量集合
  qdrant_collection_sql: "desk_agent_sql"      # SQL 向量集合
  embedding_model: "BAAI/bge-small-zh-v1.5"    # 向量模型
  hybrid_alpha: 0.7                            # 混合检索权重
  top_k: 5                                     # 文档检索数量
  candidate_k: 30                              # 候选文档数量
  sql_top_k: 3                                 # SQL 检索数量
  sql_candidate_k: 15                          # SQL 候选数量
  sql_hybrid_alpha: 0.8                        # SQL 混合权重

# ==================== 提示词模板 ====================
prompts:
  system_prompt: |
    你是一个专业且友好的桌管系统AI助手，善于用自然语言总结数据库查询结果，
    回答时要人性化、富有同理心，避免生硬的表达方式。
  rag_system_prompt: |
    你是一个专业的AI助手，基于以下文档内容回答用户问题。
    如果文档中没有相关信息，请如实告知。
  sql_answer_template: |
    你是一个专业且友好的桌管系统AI助手，需要基于数据库查询结果以人性化的方式回答用户问题。
    
    用户问题：{question}
    
    查询结果：
    {data_summary}
    
    请用自然语言回答用户的问题，要求：
    1. 回答要友好、自然，富有同理心
    2. 严格基于查询结果生成回答，不得编造任何数据
    3. 如果是统计类问题，先简洁回答具体数字
    4. 不要暴露数据库表名、列名等技术细节
    5. 如果查询结果为空，如实告知并提供可能的原因
    6. 使用自然的口语化表达
    7. 回答简洁一些，不要超过3句话
    
    请直接回答。

# ==================== 网络访问参数 ====================
access:
  path_prefix: "/desk_agent"          # URL 路径前缀
  cors_origins: ["*"]                 # CORS 配置（可选）

# ==================== 外部配置文件引用 ====================
schema_metadata: "./agent_backend/configs/desk_agent_schema_metadata.yaml"
```

### 5.3 schema_metadata.yaml 改造（合并 prompt_config）

**当前问题**：`prompt_config.yaml` 与 `schema_metadata.yaml` 的 `display_fields` 高度重复。

对比分析：

| 字段 | `prompt_config.yaml` | `schema_metadata.yaml` display_fields |
|------|---------------------|---------------------------------------|
| 部门名称 | ✅ | ✅ `s_group.GroupName` |
| 父部门 | ✅ + note | ✅ `s_group.ParentID` |
| 机器名 | ✅ + required | ✅ `s_machine.Name_C` |
| MAC地址 | ✅ + required | ✅ `s_machine.Mac_c` |
| ... | ... | ... |

`schema_metadata.yaml` 的 `display_fields` 已经包含了字段名→列名的映射，比 `prompt_config.yaml` 信息更丰富。`prompt_config.yaml` 仅多了 `required`、`note`、`fallback` 三个属性。

**改造方案**：将 `required`、`note`、`fallback` 合并到 `display_fields` 中，彻底消除 `prompt_config.yaml`。

改造后的 `display_fields` 示例：

```yaml
display_fields:
  department:
    - name: 部门名称
      column: s_group.GroupName
      required: true
    - name: 父部门
      column: s_group.ParentID
      required: true
      note: "父部门id为0是最外层的\"所有部门\""
    - name: 部门路径
      column: s_group.deppath
      required: true
    - name: 直属于部门下的机器数
      column: COUNT(s_machine.ID)
      aggregate: true
      required: true

  machine:
    - name: 机器名
      column: s_machine.Name_C
      required: true
    - name: IP地址
      column: s_machine.Ip_C
      required: true
    - name: MAC地址
      column: s_machine.Mac_c
      required: true
    - name: 用户
      column: s_user.UserName
      required: false
      fallback: "空"
    - name: 所属部门
      column: s_group.deppath
      required: true
      note: "用部门全路径表示"
    - name: 设备类型
      column: s_machine.MtPingPai
    - name: 客户端版本
      column: s_machine.VersionNum
    - name: 是否在线
      column: onlineinfo.mtid
      display: true
    - name: 客户端安装时间
      column: s_machine.VersionTime
    - name: 最近上线时间
      column: s_machine.MtGetDate

  hardware:
    - name: 设备名
      column: s_machine.Name_C
      required: true
    - name: 部门
      column: s_group.deppath
      required: true
      note: "用部门全路径表示"
    - name: CPU
      column: a_clienthardinfo2.CUP
    - name: 内存
      column: a_clienthardinfo2.Memory
    - name: 硬盘信息
      column: a_clienthardinfo2.DiskInfo
    - name: 硬盘大小
      column: a_clienthardinfo2.DiskSize
    - name: 显卡
      column: a_clienthardinfo2.ViewCard
    - name: 网卡列表
      column: a_clienthardinfo2.NetCardList
    - name: 网卡数量
      column: a_clienthardinfo2.netcardnum
    - name: USB设备列表
      column: a_clienthardinfo2.USBList
```

**合并后的收益**：
- 每个智能体减少 1 个配置文件（从 3 个减到 2 个）
- 字段定义只维护一处，避免 `prompt_config` 与 `display_fields` 不一致
- `display_fields` 同时服务于 SQL Prompt 构建（字段提示）和结果展示（字段映射），一石二鸟

### 5.4 配置加载、验证与更新机制

#### 5.4.1 加载流程

```
应用启动
  │
  ├─ 1. 加载 .env 全局环境变量
  │
  ├─ 2. 扫描 agent_configs/ 目录
  │     └─ 每个 *.yaml 文件 = 一个智能体
  │        ├─ 文件名 → agent_id
  │        ├─ enabled: true → 加载
  │        └─ enabled: false → 跳过（但记录在列表中）
  │
  ├─ 3. 逐个加载 enabled 的智能体配置
  │     ├─ 环境变量插值：${VAR} → os.getenv("VAR")
  │     ├─ Pydantic 模型验证：AgentConfig
  │     └─ 加载引用的 schema_metadata（含 display_fields）
  │
  ├─ 4. 初始化共享资源
  │     ├─ EmbeddingModel（全局单例）
  │     ├─ QdrantVectorStore（按 collection 隔离）
  │     └─ OllamaChatClient（全局单例）
  │
  └─ 5. 注册 API 路由
        └─ 为每个 enabled agent 注册 /api/v1/{agent_id}/* 路由
```

#### 5.4.2 Pydantic 验证模型

```python
class AgentConfig(BaseModel):
    agent: AgentInfo
    welcome: WelcomeConfig
    database: DatabaseConfig
    knowledge: KnowledgeConfig
    prompts: PromptConfig
    access: AccessConfig
    schema_metadata: str
    
    @model_validator(mode='after')
    def resolve_env_vars(self):
        """解析配置中的 ${VAR} 环境变量"""
        ...
    
    @model_validator(mode='after')
    def validate_paths(self):
        """验证知识库路径和配置文件路径是否存在"""
        ...
    
    @model_validator(mode='after')
    def validate_agent_id(self):
        """验证 agent.id 与文件名一致"""
        ...
```

#### 5.4.3 热更新机制

- **配置文件监听**：使用 `watchfiles` 库监听 `agent_configs/` 目录变更
- **变更检测**：文件修改时，对比 YAML 内容哈希
- **安全重载**：
  - 仅重载变更的智能体配置
  - 不影响正在进行的请求（请求级使用旧配置快照）
  - 新请求使用新配置
  - 新增 YAML 文件自动发现并注册
- **API 触发**：`POST /api/v1/admin/reload` 手动触发重载

---

## 六、详细实施步骤

### 阶段一：基础设施改造（核心框架）

| 步骤 | 任务                             | 涉及文件                                                     | 说明                                 |
| ---- | -------------------------------- | ------------------------------------------------------------ | ------------------------------------ |
| 1.1  | 创建 `AgentConfig` Pydantic 模型 | `agent_backend/core/agent_config.py`（新建）                 | 定义配置数据结构（不含 prompt_config） |
| 1.2  | 创建 `AgentRegistry` 注册中心    | `agent_backend/core/agent_registry.py`（新建）               | 目录扫描自动发现，加载/管理/查询智能体配置 |
| 1.3  | 改造 `ConnectionManager`         | `agent_backend/sql_agent/connection_manager.py`              | 支持 `agent_id` 参数，多数据库连接池 |
| 1.4  | 创建 `desk_agent.yaml`           | `agent_backend/configs/agent_configs/desk_agent.yaml`（新建） | 从现有 .env 迁移桌管配置             |
| 1.5  | 合并 `prompt_config` 到 `schema_metadata` | `agent_backend/configs/schema_metadata.yaml`         | 在 display_fields 中增加 required/note/fallback |
| 1.6  | 迁移现有配置到 YAML              | `.env`                                                       | 保留全局配置，智能体配置迁移到 YAML  |

### 阶段二：API 层改造

| 步骤 | 任务               | 涉及文件                                 | 说明                         |
| ---- | ------------------ | ---------------------------------------- | ---------------------------- |
| 2.1  | 创建智能体管理 API | `agent_backend/api/v1/agents.py`（新建） | 列出/查询智能体              |
| 2.2  | 改造路由系统       | `agent_backend/api/routes.py`            | 动态注册 `{agent_id}/*` 路由 |
| 2.3  | 改造 Chat API      | `agent_backend/api/v1/chat.py`           | 支持 `agent_id` 参数         |
| 2.4  | 改造 RAG API       | `agent_backend/api/v1/rag.py`            | 按 `agent_id` 隔离同步任务   |
| 2.5  | 改造 SQL Agent API | `agent_backend/api/v1/sql_agent.py`      | 按 `agent_id` 隔离           |
| 2.6  | 改造 Metadata API  | `agent_backend/api/v1/metadata.py`       | 按 `agent_id` 加载 schema    |

### 阶段三：业务逻辑层改造

| 步骤 | 任务                     | 涉及文件                                    | 说明                                   |
| ---- | ------------------------ | ------------------------------------------- | -------------------------------------- |
| 3.1  | 改造 `handlers.py`       | `agent_backend/chat/handlers.py`            | 从 `AgentContext` 读取配置，消除硬编码 |
| 3.2  | 改造 `router.py`         | `agent_backend/chat/router.py`              | 意图识别支持 agent 级关键词配置        |
| 3.3  | 改造 `prompt_builder.py` | `agent_backend/sql_agent/prompt_builder.py` | 从 `AgentConfig.prompts` 读取提示词    |
| 3.4  | 改造 `service.py`        | `agent_backend/sql_agent/service.py`        | 按 `agent_id` 获取数据库连接           |
| 3.5  | 改造 `retrieval.py`      | `agent_backend/rag_engine/retrieval.py`     | 按 `agent_id` 获取 RAG 配置            |
| 3.6  | 改造 `config_helper.py`  | `agent_backend/core/config_helper.py`       | 支持 `agent_id` 参数获取数据库 URL     |

### 阶段四：前端改造

| 步骤 | 任务                  | 涉及文件                                                  | 说明                                |
| ---- | --------------------- | --------------------------------------------------------- | ----------------------------------- |
| 4.1  | 引入 Vue Router       | `agent_frontend/src/router/`（新建）                      | 多智能体页面路由                    |
| 4.2  | 创建智能体选择组件    | `agent_frontend/src/components/AgentSelector.vue`（新建） | 侧边栏/标签页切换                   |
| 4.3  | 改造 `ChatBox.vue`    | `agent_frontend/src/components/ChatBox.vue`               | 接收 `agentId` prop，动态加载欢迎语 |
| 4.4  | 改造 `App.vue`        | `agent_frontend/src/App.vue`                              | 集成路由和智能体选择                |
| 4.5  | 改造 `chat.js`        | `agent_frontend/src/api/chat.js`                          | API 路径包含 `agent_id`             |
| 4.6  | 改造 `vite.config.js` | `agent_frontend/vite.config.js`                           | 代理规则适配新路径                  |

### 阶段五：Docker 与部署改造

| 步骤 | 任务                      | 涉及文件                    | 说明                       |
| ---- | ------------------------- | --------------------------- | -------------------------- |
| 5.1  | 改造 `docker-compose.yml` | `docker-compose.yml`        | 挂载多智能体配置和数据目录 |
| 5.2  | 改造 `Dockerfile.backend` | `docker/Dockerfile.backend` | 包含 agent_configs 目录    |
| 5.3  | 改造 `nginx.conf`         | `docker/nginx.conf`         | 适配新 API 路径结构        |
| 5.4  | 创建新智能体数据目录      | `data/ops_agent/` 等        | 初始化目录结构             |

### 阶段六：新增智能体接入（零代码扩展）

新增一个智能体（如"云桌面智能体"）仅需以下操作：

| 步骤 | 任务                                        | 说明                                      |
| ---- | ------------------------------------------- | ----------------------------------------- |
| 6.1  | 创建 `cloud_desktop_agent.yaml`             | 在 `agent_configs/` 目录下新建，设置 `enabled: true` |
| 6.2  | 创建 `cloud_desktop_agent_schema_metadata.yaml` | 数据库 Schema 元数据（含 display_fields） |
| 6.3  | 准备知识库文档                              | 放入 `data/cloud_desktop_agent/docs/`     |
| 6.4  | 准备 SQL 示例                               | 放入 `data/cloud_desktop_agent/sql/`      |
| 6.5  | 重启服务或调用热重载 API                    | 智能体自动注册，前端自动展示              |

**无需修改任何代码文件**，无需修改注册表，无需修改前端。

---

## 七、潜在风险及规避措施

| 风险                       | 影响                             | 概率 | 规避措施                                                     |
| -------------------------- | -------------------------------- | ---- | ------------------------------------------------------------ |
| **单进程故障扩散**         | 一个智能体异常可能影响其他智能体 | 中   | 请求级 try-catch 隔离；关键资源（DB 连接）独立管理；未来可演进为多进程 |
| **配置文件复杂度**         | 6 个 YAML 配置文件维护成本       | 中   | 严格 Pydantic 验证；提供配置模板和文档；开发配置校验 CLI 工具 |
| **Qdrant Collection 数量** | 12 个 Collection（6×2）管理复杂  | 低   | 自动化 Collection 创建/删除；统一命名规范；Qdrant 本身支持大量 Collection |
| **数据库连接池膨胀**       | 6 个独立连接池占用连接数         | 中   | 每个连接池设置 max_size 限制；空闲连接超时回收；监控连接数   |
| **前端路由复杂度**         | Vue Router 多页面状态管理        | 低   | 复用 ChatBox 组件，仅通过 prop 区分；使用 URL 参数而非复杂状态 |
| **环境变量插值安全**       | `${VAR}` 可能泄露敏感信息        | 低   | 仅在服务端解析；日志中脱敏；配置文件权限控制                 |
| **向后兼容性**             | 现有客户端 API 调用失效          | 低   | 保留 `/api/v1/chat` 默认路由；渐进式迁移                     |
| **Embedding 模型切换**     | 不同智能体可能需要不同模型       | 低   | 当前统一使用 bge-small-zh；架构预留模型切换能力；共享时需确保维度一致 |

---

## 八、多智能体方案适用性专业建议

### 8.1 适用场景

✅ **强烈推荐采用多智能体方案的情况**：
- 各业务域数据完全隔离（不同数据库、不同知识库）
- 用户群体有明确的领域区分需求
- 需要独立控制各智能体的启用/禁用
- 需要各智能体展示不同的品牌/欢迎信息

### 8.2 不适用场景

❌ **不建议采用多智能体方案的情况**：
- 所有业务域共享同一数据库，仅提示词不同 → 建议用单智能体 + 多角色切换
- 用户不需要区分业务域 → 建议用统一入口 + 自动路由
- 智能体间需要频繁协作 → 建议用 LangGraph 多 Agent 编排

### 8.3 当前项目评估

**推荐采用**。理由：
1. 六大智能体对应不同业务系统，数据库物理隔离
2. 用户群体有明确的领域区分（桌管/运维/工单等）
3. 各智能体知识库内容完全不同，独立检索可提升精度
4. 当前架构与方案高度适配，改造成本可控

### 8.4 演进路线建议

```
Phase 1（当前）: 单智能体（desk-agent）
    ↓
Phase 2（本次）: 配置化多智能体（路径后缀方案）
    ↓
Phase 3（未来）: 智能体间协作（LangGraph Supervisor 模式）
    ↓
Phase 4（远期）: 微服务化（按需独立部署高频智能体）
```

---

## 九、核心代码改造要点

### 9.1 AgentContext 请求级上下文

```python
# agent_backend/core/agent_context.py
from dataclasses import dataclass
from agent_backend.core.agent_config import AgentConfig

@dataclass
class AgentContext:
    agent_id: str
    config: AgentConfig
    
    @property
    def db_url(self) -> str:
        return self.config.database.resolved_url
    
    @property
    def docs_collection(self) -> str:
        return self.config.knowledge.qdrant_collection_docs
    
    @property
    def sql_collection(self) -> str:
        return self.config.knowledge.qdrant_collection_sql
    
    @property
    def display_fields(self) -> dict:
        """从 schema_metadata 中获取展示字段配置（替代原 prompt_config）"""
        return self.config.loaded_schema_metadata.get("display_fields", {})
```

### 9.2 FastAPI 依赖注入

```python
# agent_backend/core/dependencies.py
from fastapi import Depends, Path
from agent_backend.core.agent_registry import AgentRegistry

registry = AgentRegistry()  # 自动扫描 agent_configs/ 目录

async def get_agent_context(
    agent_id: str = Path(..., description="智能体ID"),
) -> AgentContext:
    config = registry.get_agent(agent_id)
    return AgentContext(agent_id=agent_id, config=config)
```

### 9.3 路由动态注册

```python
# agent_backend/api/routes.py
from agent_backend.core.agent_registry import AgentRegistry

registry = AgentRegistry()  # 自动扫描 agent_configs/ 目录

router = APIRouter()

# 全局路由
router.include_router(health_router, prefix="/api/v1")
router.include_router(agents_router, prefix="/api/v1")

# 为每个启用的智能体自动注册路由
for agent_id in registry.enabled_agents:
    agent_router = create_agent_router(agent_id)
    router.include_router(agent_router, prefix=f"/api/v1/{agent_id}")

# 向后兼容：默认路由
router.include_router(chat_router, prefix="/api/v1")
```

### 9.4 ConnectionManager 改造

```python
# 改造 key 结构
# 旧: _connections[session_id]
# 新: _connections[(agent_id, session_id)]

def get_or_create_connection(
    self, 
    session_id: str, 
    agent_id: str,
    database_url: str | None = None,
) -> Any:
    key = (agent_id, session_id)
    # ... 使用 key 管理连接
```

---

## 十、总结

本方案基于对现有项目架构的深入分析，提出了以 **路径后缀方案 + 配置化隔离** 为核心的多智能体扩展策略。方案的核心优势：

1. **零代码扩展**：新增智能体仅需创建 YAML 配置文件 + 准备数据目录，无需修改任何代码。目录扫描自动发现机制让第 7、第 8 个智能体的接入成本趋近于零
2. **最小侵入**：核心业务逻辑（SQL 生成、RAG 检索、LLM 调用）完全复用，仅改造配置层和路由层
3. **配置精简**：每个智能体仅需 2 个配置文件（`{agent_id}.yaml` + `{agent_id}_schema_metadata.yaml`），消除冗余的 `prompt_config.yaml`，字段定义只维护一处
4. **资源高效**：共享进程、共享 Embedding 模型、共享 Qdrant 客户端，避免资源浪费
5. **运维友好**：单一进程、单一端口、统一配置管理
6. **可扩展**：架构预留了向多进程、微服务演进的能力

预计改造工作量集中在阶段一至阶段四（基础设施 + API + 业务逻辑 + 前端），阶段五和六（Docker + 新智能体接入）为增量工作。
