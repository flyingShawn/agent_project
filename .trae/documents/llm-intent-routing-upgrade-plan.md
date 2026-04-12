# 意图路由升级方案：从规则引擎到 LLM 驱动

## 一、现状分析

### 1.1 当前意图路由机制

当前 [router.py](../agent_backend/chat/router.py) 采用**关键词 + 正则**的三层评分机制：

| 层级 | 逻辑 | 特点 |
|------|------|------|
| 第一层 | 通用对话正则匹配（问候/寒暄） | 直接返回 RAG |
| 第二层 | SQL/RAG 正则模式匹配 | IP地址、统计类 vs 操作类 |
| 第三层 | 关键词计数评分 | 33个SQL关键词 vs 25个RAG关键词 |

**只有两种意图**：`Intent.SQL` 和 `Intent.RAG`，没有"通用对话"类型（通用对话也走 RAG）。

### 1.2 当前痛点

1. **泛化能力弱**：口语化表达如"帮我看看有几台机器没开机"容易误判
2. **边界模糊**："查询水印策略的设置方法" 同时包含 SQL 和 RAG 关键词
3. **维护成本高**：每新增一种问法需手动添加关键词/正则
4. **无法理解语义**："上周在线率怎么样" 应走 SQL，但没有匹配到关键词
5. **无置信度**：规则引擎无法表达"不确定"，只能硬性二选一

### 1.3 当前处理流程

```
用户请求 → classify_intent() 规则路由
  ├── Intent.SQL → handle_sql_chat()
  │     → generate_secure_sql() (RAG检索SQL样本 + Schema元数据 + LLM生成)
  │     → execute_sql() (安全校验 + 执行)
  │     → LLM总结结果 → 流式返回
  └── Intent.RAG → handle_rag_chat()
        → hybrid_search() (向量+BM25混合检索)
        → 有结果: LLM基于文档生成回答 → 流式返回
        → 无结果: LLM普通对话 → 流式返回
```

---

## 二、框架选型调研

### 2.1 LangGraph

**核心概念**：将 Agent 流程建模为有向图（StateGraph），节点是处理函数，边定义转移逻辑，条件边实现分支。

**优点**：
- 图结构可视化、节点独立可测
- 原生支持循环（SQL校验重试）、条件分支、状态持久化
- 内置 Checkpointing（暂停/恢复/时间旅行调试）
- LangSmith 集成追踪

**缺点**：
- 引入 `langgraph` + `langchain-core`，依赖链较长（~15MB）
- 学习曲线较高（图范式、状态不可变等概念）
- **对当前 2 分支线性流程属于过度设计**

**适用场景**：需要 SQL 校验重试循环、多轮工具调用、人工审批、状态持久化等复杂流程时。

### 2.2 LangChain

**核心能力**：统一消息抽象、Runnable 链式编排、Tool 抽象、OutputParser。

**优点**：
- `langchain-core` 最小化引入（~5MB），规范化接口
- Tool 抽象可将 SQL/RAG 统一为工具
- PydanticOutputParser 可用于意图分类结构化输出

**缺点**：
- 全家桶引入过重，当前项目依赖仅 12 个包
- Agent 抽象（ReAct等）对当前场景不需要
- 增加一层抽象可能带来调试困难

**适用场景**：需要统一 Tool 抽象、Runnable 链式编排时，可仅引入 `langchain-core`。

### 2.3 纯 Pydantic + LLM JSON Mode（推荐）

**核心思路**：不引入任何框架，仅使用 LLM 的 JSON Mode 强制输出合法 JSON + Pydantic 做验证。

**优点**：
- **零额外依赖**，不增加 requirements.txt 复杂度
- 完全可控，没有框架黑盒
- 与现有代码无缝集成，直接替换 `classify_intent` 函数
- 渐进式升级，可先叠加 LLM 分类，保留规则引擎回退

**缺点**：
- 没有标准化 Tool/Runnable 抽象
- 复杂流程受限（if/elif 在多分支时难维护）
- 没有生态集成（LangSmith 追踪等）

### 2.4 选型结论

| 维度 | LangGraph | LangChain (core) | 纯 Pydantic |
|------|-----------|------------------|-------------|
| 额外依赖 | ~15MB | ~5MB | 0 |
| 代码量 | ~80行 | ~50行 | ~60行 |
| 学习成本 | 高 | 中 | 低 |
| 当前适配性 | 过度 | 适中 | **最佳** |
| 未来扩展性 | 极好 | 好 | 一般 |

**推荐方案：纯 Pydantic + LLM JSON Mode**，原因：
1. 当前只有 2 分支（SQL/RAG），流程简单线性
2. 项目依赖精简（12个包），不应为简单路由引入重框架
3. 可渐进式升级，先替换意图分类，保留规则引擎回退
4. 未来如需复杂流程（SQL重试循环等），再考虑引入 LangGraph

---

## 三、技术可行性验证

### 3.1 Qwen2.5 + Ollama 的 Function Calling 支持

✅ **Qwen2.5 原生支持 Function Calling / Tool Use**
- Ollama >= 0.4.0 支持 `tools` 参数
- Ollama >= 0.3.0 支持 `response_format: {"type": "json_object"}` JSON Mode
- 7B 模型简单场景准确度 85-90%

### 3.2 当前 LLM 客户端改造需求

当前 [clients.py](../agent_backend/llm/clients.py) 的 `chat_complete` 方法**不支持** `response_format` 和 `tools` 参数，需要扩展：

```python
# 当前签名
def chat_complete(self, messages, *, images_base64=None) -> str:

# 需要扩展为
def chat_complete(self, messages, *, images_base64=None, response_format=None, tools=None, tool_choice=None) -> str:
```

### 3.3 意图类型扩展

当前只有 `Intent.SQL` 和 `Intent.RAG`，建议新增 `Intent.CHAT`：

```python
class Intent(str, Enum):
    SQL = "sql"    # 数据库查询
    RAG = "rag"    # 文档知识问答
    CHAT = "chat"  # 通用对话（问候/闲聊/非业务问题）
```

这样 LLM 可以明确区分"需要查文档"和"只是聊天"，避免将闲聊问题也送去 RAG 检索浪费资源。

---

## 四、详细实施方案

### 4.1 整体架构变化

**改造前**：
```
用户请求 → classify_intent() [规则引擎]
  ├── SQL → handle_sql_chat()
  └── RAG → handle_rag_chat()
```

**改造后**：
```
用户请求 → classify_intent() [分层路由]
  │
  ├── 第一层：规则引擎快速匹配（确定性路由，毫秒级）
  │     - 命中 → 直接返回意图
  │     - 未命中 ↓
  │
  ├── 第二层：LLM 语义分类（100-300ms）
  │     - 高置信度(≥0.7) → 返回意图
  │     - 低置信度(<0.7) → 默认走 RAG（更安全）
  │
  ├── SQL → handle_sql_chat()（不变）
  ├── RAG → handle_rag_chat()（不变）
  └── CHAT → handle_rag_chat()（走普通对话，跳过检索）
```

### 4.2 改造步骤

#### 步骤1：扩展 Intent 类型

**文件**：[types.py](../agent_backend/chat/types.py)

```python
class Intent(str, Enum):
    SQL = "sql"
    RAG = "rag"
    CHAT = "chat"  # 新增：通用对话
```

#### 步骤2：扩展 LLM 客户端支持 JSON Mode

**文件**：[clients.py](../agent_backend/llm/clients.py)

在 `chat_complete` 方法中增加 `response_format` 参数支持：
- 透传 `response_format: {"type": "json_object"}` 到 Ollama API
- 返回值不变，仍为字符串（JSON 字符串）

#### 步骤3：新建 LLM 意图分类器

**文件**：新建 `agent_backend/chat/llm_router.py`

核心设计：
- 定义 `IntentResult` Pydantic 模型（intent + confidence + reasoning）
- 编写意图分类 System Prompt（含判断规则 + Few-shot 示例）
- 使用 `chat_complete(response_format={"type": "json_object"})` 获取结构化输出
- Pydantic 验证 + 置信度阈值检查
- 失败时回退到规则引擎

**意图分类 Prompt 设计**：

```python
INTENT_SYSTEM_PROMPT = """你是一个意图分类器。根据用户问题判断意图类型。

## 可选意图
- sql: 查询数据库中的数据、统计、设备状态、IP、告警等结构化信息
- rag: 操作方法、配置步骤、问题排查、文档知识等需要查阅文档的问题
- chat: 问候、闲聊、与桌管系统无关的问题

## 判断规则
1. 涉及"数量、统计、列表、在线状态、设备信息、告警、IP地址、趋势、查询数据"→ sql
2. 涉及"怎么操作、如何设置、为什么、排查问题、操作手册、流程步骤"→ rag
3. 问候、闲聊、与桌管系统无关 → chat

## 示例
- "多少机器在线" → {"intent": "sql", "confidence": 0.95, "reasoning": "询问在线设备数量"}
- "水印怎么设置" → {"intent": "rag", "confidence": 0.9, "reasoning": "询问操作方法"}
- "你好" → {"intent": "chat", "confidence": 0.99, "reasoning": "通用问候"}
- "192.168.1.10的告警" → {"intent": "sql", "confidence": 0.95, "reasoning": "查询特定IP告警"}
- "远程连接不通怎么排查" → {"intent": "rag", "confidence": 0.9, "reasoning": "问题排查"}

请严格输出JSON格式：{"intent": "sql|rag|chat", "confidence": 0.0-1.0, "reasoning": "简短理由"}"""
```

#### 步骤4：改造 classify_intent 为分层路由

**文件**：[router.py](../agent_backend/chat/router.py)

改造策略：
- 保留现有规则引擎逻辑作为第一层快速匹配
- 规则未命中时，调用 LLM 分类器
- LLM 分类失败时，回退到规则引擎的评分结果

```python
def classify_intent(question: str) -> Intent:
    # 第一层：规则引擎快速匹配（确定性路由）
    rule_result = _classify_by_rules(question)
    if rule_result.is_confident:
        return rule_result.intent
    
    # 第二层：LLM 语义分类
    try:
        llm_result = classify_intent_llm(question)
        if llm_result.confidence >= 0.7:
            return llm_result.intent
        # 低置信度默认走 RAG
        return Intent.RAG
    except Exception:
        # LLM 分类失败，回退到规则引擎
        return rule_result.intent
```

#### 步骤5：改造 API 层支持 CHAT 意图

**文件**：[chat.py](../agent_backend/api/v1/chat.py)

在路由分发时增加 CHAT 分支：
- `Intent.SQL` → `handle_sql_chat()`
- `Intent.RAG` → `handle_rag_chat()`
- `Intent.CHAT` → `handle_rag_chat()` 但跳过检索步骤

#### 步骤6：改造 handlers 支持 CHAT 模式

**文件**：[handlers.py](../agent_backend/chat/handlers.py)

为 `handle_rag_chat` 增加 `skip_search` 参数，CHAT 模式直接走 LLM 对话：

```python
def handle_rag_chat(
    question, history, images_base64=None, session_id=None,
    *, llm_client=None, store=None, embedding_model=None,
    skip_search=False,  # 新增：CHAT模式跳过检索
) -> Iterator[str]:
```

### 4.3 需要修改的文件清单

| 文件 | 修改内容 | 改动量 |
|------|---------|--------|
| `chat/types.py` | 新增 `Intent.CHAT` | 小 |
| `llm/clients.py` | `chat_complete` 增加 `response_format` 参数 | 小 |
| `chat/llm_router.py` | **新建**：LLM 意图分类器 | 中 |
| `chat/router.py` | 改造为分层路由（规则+LLM） | 中 |
| `api/v1/chat.py` | 增加 CHAT 分支路由 | 小 |
| `chat/handlers.py` | `handle_rag_chat` 增加 `skip_search` 参数 | 小 |

### 4.4 不需要修改的部分

- **SQL Agent 全流程**（生成/校验/执行/权限包装）→ 完全不变
- **RAG Engine 全流程**（解析/分块/嵌入/检索/入库）→ 完全不变
- **Prompt 模板**（SQL生成/结果总结/RAG问答）→ 完全不变
- **安全机制**（SQL校验/受限表/敏感列/行级权限）→ 完全不变
- **前端**→ 完全不变（SSE 事件格式兼容）

---

## 五、关键设计决策

### 5.1 为什么不引入 LangChain/LangGraph？

1. **当前流程简单**：只有 2+1 个分支（SQL/RAG/CHAT），线性流程，无循环无重试
2. **依赖精简原则**：当前 12 个依赖包，引入框架会翻倍
3. **完全可控**：纯 Python 实现比框架更透明，调试更容易
4. **渐进式升级**：先验证 LLM 路由效果，再考虑是否需要框架

### 5.2 为什么用 JSON Mode 而不是 Function Calling？

1. **更简单**：JSON Mode 只需 `response_format` 参数，Function Calling 需要 `tools` + `tool_choice`
2. **更兼容**：JSON Mode 在 Ollama 0.3+ 就支持，Function Calling 需要 0.4+
3. **够用**：意图分类只需返回一个 JSON 对象，不需要 Function Calling 的多工具选择能力
4. **未来可升级**：如果后续需要 LLM 自主选择工具（SQL/RAG），再切换到 Function Calling

### 5.3 为什么保留规则引擎？

1. **快速路径**：确定性匹配（如 IP 地址正则）毫秒级返回，无需等 LLM
2. **回退保障**：LLM 不可用时系统仍可运行
3. **成本控制**：规则命中时省去一次 LLM 调用
4. **渐进式**：降低改造风险，可逐步调优

### 5.4 新增 CHAT 意图的必要性

当前系统将闲聊也走 RAG 检索，浪费资源且可能检索到不相关文档。新增 CHAT 意图后：
- 闲聊问题直接走 LLM 对话，跳过检索
- 减少无效的向量检索和 BM25 计算
- 提升响应速度（省去检索耗时）

---

## 六、性能影响评估

| 环节 | 改造前 | 改造后 | 变化 |
|------|--------|--------|------|
| 规则命中时 | ~1ms | ~1ms | 无变化 |
| 规则未命中时 | ~1ms（关键词评分） | ~200-500ms（LLM分类） | 增加 |
| RAG 检索 | 总是执行 | CHAT 模式跳过 | 减少 |
| 总体首字延迟 | 规则命中:快 / 未命中:快但可能错 | 规则命中:快 / 未命中:慢但更准 | 准确率换延迟 |

**缓解措施**：
- 规则引擎覆盖高频确定性场景（IP查询、统计类），大部分请求仍走快速路径
- LLM 分类使用 `chat_complete`（同步调用），模型小（7B），延迟可控
- 可考虑对 LLM 分类做异步预分类（前端 debounce 后提前发送）

---

## 七、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| LLM 分类延迟高 | 用户等待时间长 | 规则引擎快速路径 + 异步预分类 |
| LLM 分类错误 | 路由到错误通道 | 置信度阈值 + 规则回退 + 前端手动切换 |
| LLM 不可用 | 无法分类 | 回退到规则引擎 |
| JSON 输出格式错误 | 解析失败 | Pydantic 验证 + 异常捕获 + 回退 |
| Ollama 版本不支持 JSON Mode | 无法强制 JSON | Prompt 约束 + 正则提取 JSON |

---

## 八、未来扩展方向

1. **Function Calling 路由**：当 Qwen2.5 + Ollama 的 Function Calling 更成熟后，可切换为工具选择模式
2. **SQL 校验重试循环**：如果需要 SQL 生成失败后自动修正重试，可考虑引入 LangGraph
3. **多轮工具调用**：如果需要 LLM 连续调用多个工具（先查 SQL 再查文档），需要更复杂的编排
4. **语义路由**：使用向量相似度做意图匹配，无需每次调用 LLM
5. **A/B 测试**：对比规则引擎和 LLM 分类的准确率，持续优化
