"""
Agent状态Schema定义模块

文件功能：
    定义LangGraph StateGraph的状态结构（AgentState），作为各节点间数据传递的契约。
    所有节点读取和更新State中的字段，实现跨节点的状态累积和传递。

在系统架构中的定位：
    位于Agent编排层核心，是StateGraph的类型基础。
    LangGraph通过AgentState的TypedDict定义自动管理消息合并（add_messages reducer）。

主要使用场景：
    - StateGraph初始化时作为状态类型参数
    - 各节点函数的输入输出类型约束
    - API层构建初始State

核心定义：
    - AgentState: TypedDict，包含消息列表、用户请求信息、工具执行结果、迭代控制等字段

字段说明：
    - messages: 对话消息列表，使用add_messages reducer自动合并
    - last_llm_input_messages: 最近一次实际传给LLM的消息列表快照（用于收尾日志）
    - question: 用户原始问题
    - session_id: 数据库连接会话ID
    - lognum: 用户工号
    - images_base64: 用户上传的图片（Base64编码）
    - sql_results: SQL查询结果累积列表
    - rag_results: RAG检索结果累积列表
    - metadata_results: 元数据查询结果累积列表
    - tool_call_count: 已执行的工具调用次数
    - max_tool_calls: 最大工具调用次数限制（防死循环）
    - data_tables: SQL查询结果的Markdown表格列表（用于最终输出拼接）
    - references: RAG检索的参考来源列表（用于最终输出拼接）

关联文件：
    - agent_backend/agent/graph.py: StateGraph使用AgentState作为状态类型
    - agent_backend/agent/nodes.py: 各节点读写AgentState字段
    - agent_backend/api/v1/chat.py: 构建初始AgentState
"""
from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    last_llm_input_messages: list
    question: str
    session_id: str
    lognum: str
    images_base64: list[str] | None
    sql_results: list[dict]
    rag_results: list[dict]
    metadata_results: list[dict]
    time_results: list[dict]
    calculator_results: list[dict]
    chart_configs: list[dict]
    export_results: list[dict]
    web_search_results: list[dict]
    tool_call_count: int
    max_tool_calls: int
    force_finalize_after_sql: bool
    force_finalize_reason: str
    data_tables: list[str]
    references: list[str]
    pre_sql_context: dict | None
