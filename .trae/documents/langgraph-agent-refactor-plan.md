# LangGraph Agent 重构实施计划

## 概述

将桌面管理系统AI助手从规则驱动架构重构为基于LangGraph的Agent架构。核心变更：
- 用LLM Tool Calling替代关键词+正则意图识别
- 用LangGraph StateGraph替代硬编码SQL/RAG双分支
- 删除权限包装和受限表检查（按需求不再需要）
- 强化SQL生成中的样本模仿提示
- 保持SSE流式输出和前端API契约不变

---

## 阶段一：基础设施搭建

### 步骤 1.1：更新依赖
- 在 `requirements.txt` 中新增：
  - `langgraph>=0.2,<0.3`
  - `langchain-openai>=0.3`
  - `langchain-core>=0.3`
- 运行 `pip install -r requirements.txt` 验证安装

### 步骤 1.2：创建 agent 模块骨架
- 创建 `agent_backend/agent/__init__.py`
- 创建 `agent_backend/agent/state.py` — AgentState TypedDict 定义
  - `messages: Annotated[list[BaseMessage], add_messages]`
  - `question: str`
  - `session_id: str`
  - `lognum: str`
  - `images_base64: list[str] | None`
  - `sql_results: list[dict]`
  - `rag_results: list[dict]`
  - `metadata_results: list[dict]`
  - `tool_call_count: int`
  - `max_tool_calls: int`（默认5）
  - `data_tables: list[str]`
  - `references: list[str]`

### 步骤 1.3：创建 LLM 客户端配置
- 创建 `agent_backend/agent/llm.py`
  - 封装 `ChatOpenAI` 初始化，从环境变量读取 `LLM_BASE_URL`、`LLM_API_KEY`、`CHAT_MODEL`
  - 提供 `get_llm()` 工厂函数，配置 `streaming=True`
  - 处理不同后端的特殊参数（如 DeepSeek 的 thinking 禁用）

### 步骤 1.4：创建 Prompt 定义
- 创建 `agent_backend/agent/prompts.py`
  - 定义 `SYSTEM_PROMPT`：包含角色描述、3个Tool的使用说明、决策规则、回答规则
  - 定义 `SQL_SUMMARY_PROMPT`：SQL结果总结的prompt模板
  - 定义 `RAG_ANSWER_PROMPT`：RAG回答的prompt模板

### 步骤 1.5：创建最简 Graph（无Tool）
- 创建 `agent_backend/agent/nodes.py`
  - `init_node(state)`: 注入系统Prompt到messages
  - `agent_node(state, llm)`: 调用LLM（绑定Tools），返回AIMessage
  - `respond_node(state, llm)`: 最终回答节点（流式生成）
- 创建 `agent_backend/agent/graph.py`
  - 构建 StateGraph：init → agent → respond → END
  - 提供 `get_agent_graph()` 工厂函数
  - 提供 `stream_graph_response()` 异步生成器（基于 astream_events）

### 步骤 1.6：验证基础链路
- 启动后端服务，通过API发送简单问题（如"你好"）
- 验证LLM能正常连接并流式返回回答

---

## 阶段二：Tool 定义与实现

### 步骤 2.1：创建 Tool 模块
- 创建 `agent_backend/agent/tools/__init__.py`
- 创建 `agent_backend/agent/tools/sql_tool.py`
- 创建 `agent_backend/agent/tools/rag_tool.py`
- 创建 `agent_backend/agent/tools/metadata_tool.py`

### 步骤 2.2：实现 sql_query Tool
- 使用 `@tool` 装饰器定义 `sql_query`
- 入参：`question: str`
- 内部流程：
  1. 调用 `search_sql_samples(question)` 检索SQL样本
  2. 调用 `build_sql_prompt(runtime, question, sql_samples=sql_samples)` 构建Prompt
  3. **在prompt末尾追加强化模仿指令**："你必须严格模仿参考SQL样本的写法风格、表关联方式和别名规则"
  4. 调用 `ChatOpenAI.invoke()` 生成SQL（注意：这里用同步调用，不是Agent的LLM）
  5. 清理Markdown格式（复用 `_clean_sql_markdown`）
  6. 安全校验：`validate_sql_basic(sql)` + `enforce_deny_select_columns(sql, deny_cols)`
  7. **校验失败不抛异常**，返回错误信息字符串让LLM修正
  8. 调用 `execute_sql(sql=sql, params={}, session_id=...)` 执行
  9. 调用 `_build_markdown_table(rows)` 格式化
  10. 返回JSON字符串结果（含sql、rows、row_count、columns、data_table）
- **不调用** `enforce_restricted_tables`（删除）
- **不调用** `wrap_with_permission`（删除）

### 步骤 2.3：实现 rag_search Tool
- 使用 `@tool` 装饰器定义 `rag_search`
- 入参：`question: str`
- 内部流程：
  1. 初始化 `EmbeddingModel` 和 `QdrantVectorStore`（复用现有逻辑）
  2. 调用 `hybrid_search(query_text=question, store=store, embedding_model=embedding_model, ...)`
  3. 格式化检索结果为文本（包含来源、标题、内容）
  4. 返回格式化文本

### 步骤 2.4：实现 metadata_query Tool
- 使用 `@tool` 装饰器定义 `metadata_query`
- 入参：`table_name: str | None = None`
- 内部流程：
  1. 调用 `get_schema_runtime()`
  2. 根据 table_name 过滤返回对应表结构
  3. 返回格式化的表/列信息

### 步骤 2.5：完善 StateGraph（含Tool循环）
- 更新 `agent_backend/agent/graph.py`
  - 添加 sql_query、rag_search、metadata_query 节点
  - 添加条件路由 `should_continue(state)`：
    - 有 tool_calls → 返回Tool名称（支持并行）
    - 无 tool_calls → 返回 "respond"
    - tool_call_count >= max_tool_calls → 强制返回 "respond"
  - 添加 Tool → agent 回边
  - 使用 `graph.add_node("sql_query", sql_query)` 注册Tool节点
- 更新 `agent_backend/agent/nodes.py`
  - `agent_node` 中绑定Tools到LLM
  - Tool节点使用LangGraph的ToolNode或手动实现

### 步骤 2.6：验证 Tool Calling 链路
- 测试"查询在线设备数量" → LLM调用sql_query → 返回结果
- 测试"如何设置权限" → LLM调用rag_search → 返回结果
- 测试"查询在线设备数量并说明离线排查方法" → LLM并行调用sql_query和rag_search
- 测试SQL安全校验（发送包含危险关键字的请求）

---

## 阶段三：API 层适配与 SSE 流式输出

### 步骤 3.1：创建 SSE 流式适配器
- 创建 `agent_backend/agent/stream.py`
  - `stream_graph_response(graph, initial_state)` 异步生成器
  - 使用 `graph.astream_events(initial_state, version="v2")`
  - 捕获 `on_chat_model_stream` 事件 → yield SSE delta
  - 捕获 `on_tool_start` 事件 → yield SSE tool_start（可选）
  - 捕获 `on_tool_end` 事件 → yield SSE tool_end（可选）
  - 收集最终State中的 data_tables 和 references

### 步骤 3.2：重写 api/v1/chat.py
- 保留 `ChatRequest` 模型，但移除 `mode` 字段（不再需要auto/sql/rag）
- 保留 `EndChatRequest` 和 `end_chat` 端点
- 重写 `chat()` 端点：
  1. 构建 `initial_state` 字典
  2. 注入 SystemMessage + 历史消息 + HumanMessage
  3. 处理图片多模态（使用 LangChain 的 HumanMessage content 数组格式）
  4. 调用 `stream_graph_response(graph, initial_state)`
  5. 生成 SSE 事件流：start → delta(多次) → done
  6. 在 done 之前拼接 data_tables 和 references
- 保持 SSE 事件格式完全不变：
  - `event: start` → `data: {"intent": "agent", "session_id": "..."}`
  - `event: delta` → `data: "文本片段"`
  - `event: done` → `data: {"route": "agent", "session_id": "...", "meta": {}}`
  - `event: error` → `data: {"error": "..."}`

### 步骤 3.3：验证前端兼容性
- 启动前端和后端
- 发送各类问题，验证SSE事件格式和显示效果
- 验证图片上传功能
- 验证对话历史功能

---

## 阶段四：清理旧代码与优化

### 步骤 4.1：删除旧文件
- 删除 `agent_backend/chat/router.py`
- 删除 `agent_backend/chat/handlers.py`
- 删除 `agent_backend/chat/types.py`
- 删除 `agent_backend/sql_agent/permission_wrapper.py`

### 步骤 4.2：修改 sql_agent/service.py
- 移除 `enforce_restricted_tables` 调用
- 移除 `permission_name` 相关逻辑
- 移除 `{allowed_group_ids_sql}` 占位符处理
- 保留模板匹配逻辑（`select_query_pattern`，可作为SQL Tool的辅助优化）

### 步骤 4.3：修改 sql_agent/types.py
- `SqlGenRequest` 移除 `permission_name` 字段

### 步骤 4.4：修改 sql_agent/prompt_builder.py
- 移除权限相关prompt片段（`{allowed_group_ids_sql}` 相关行）
- **强化SQL样本模仿提示**：在instructions中追加更明确的模仿要求

### 步骤 4.5：修改 api/v1/sql_agent.py
- 移除 `permission_name` 参数
- 移除 `use_template` 参数（模板匹配在Tool内部自动处理）

### 步骤 4.6：修改 chat/__init__.py
- 移除对 router/handlers/types 的导出

### 步骤 4.7：全局检查
- 搜索所有对已删除模块的引用，确保无残留
- `grep -r "classify_intent\|handle_sql_chat\|handle_rag_chat\|Intent\.\|permission_wrapper\|wrap_with_permission" agent_backend/`
- 修复所有import错误

### 步骤 4.8：全面测试
- 测试SQL查询类问题
- 测试RAG检索类问题
- 测试混合意图问题
- 测试普通对话
- 测试图片输入
- 测试SSE流式输出
- 测试SQL安全校验
- 启动后端服务验证无运行时错误

---

## 文件变更汇总

### 新建文件（11个）
1. `agent_backend/agent/__init__.py`
2. `agent_backend/agent/llm.py`
3. `agent_backend/agent/state.py`
4. `agent_backend/agent/graph.py`
5. `agent_backend/agent/nodes.py`
6. `agent_backend/agent/prompts.py`
7. `agent_backend/agent/tools/__init__.py`
8. `agent_backend/agent/tools/sql_tool.py`
9. `agent_backend/agent/tools/rag_tool.py`
10. `agent_backend/agent/tools/metadata_tool.py`
11. `agent_backend/agent/stream.py`

### 删除文件（4个）
1. `agent_backend/chat/router.py`
2. `agent_backend/chat/handlers.py`
3. `agent_backend/chat/types.py`
4. `agent_backend/sql_agent/permission_wrapper.py`

### 修改文件（5个）
1. `requirements.txt` — 新增3个依赖
2. `agent_backend/api/v1/chat.py` — 重写为调用Graph
3. `agent_backend/sql_agent/service.py` — 移除权限相关
4. `agent_backend/sql_agent/types.py` — 移除permission_name
5. `agent_backend/sql_agent/prompt_builder.py` — 移除权限片段+强化模仿
6. `agent_backend/api/v1/sql_agent.py` — 移除权限参数
7. `agent_backend/chat/__init__.py` — 清理导出
