"""
LangGraph StateGraph构建模块

文件功能：
    构建和编译LangGraph StateGraph，定义节点、边和条件路由的编排关系。
    对外提供编译后的Graph单例，供API层调用。

在系统架构中的定位：
    位于Agent编排层，是整个Agent流程的"骨架"。
    将nodes.py中的节点函数按业务逻辑编排为有向图。

主要使用场景：
    - API层通过get_agent_graph()获取编译后的Graph实例
    - stream.py通过graph.astream_events()实现流式输出

Graph拓扑结构：
    init → agent → [条件路由 should_continue]
                      ├── "tools" → tools → agent（循环）
                      └── "respond" → respond → END

核心函数：
    - get_agent_graph: 获取编译后的StateGraph单例（首次调用时构建并缓存）

专有技术说明：
    - 使用LangGraph StateGraph的add_conditional_edges实现条件路由
    - should_continue返回"tools"或"respond"决定流程走向
    - 单例模式避免重复构建Graph

关联文件：
    - agent_backend/agent/nodes.py: 节点函数和条件路由的实现
    - agent_backend/agent/state.py: AgentState状态类型定义
    - agent_backend/agent/stream.py: 通过Graph实例实现流式输出
    - agent_backend/api/v1/chat.py: 调用get_agent_graph获取Graph
"""
from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from agent_backend.agent.nodes import (
    agent_node,
    init_node,
    respond_node,
    should_continue,
    tool_result_node,
)
from agent_backend.agent.state import AgentState

logger = logging.getLogger(__name__)

_graph_instance = None


def get_agent_graph() -> StateGraph:
    """
    获取编译后的LangGraph StateGraph单例。

    首次调用时构建Graph并编译，后续调用直接返回缓存实例。
    Graph拓扑：init → agent → [tools循环 / respond → END]

    返回：
        CompiledGraph: 编译后的LangGraph图实例，可直接调用stream/astream_events

    性能注意事项：
        - 单例模式避免重复构建，首次调用有轻微构建开销
        - 编译后的Graph是线程安全的
    """
    global _graph_instance
    if _graph_instance is not None:
        return _graph_instance

    workflow = StateGraph(AgentState)

    workflow.add_node("init", init_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_result_node)
    workflow.add_node("respond", respond_node)

    workflow.set_entry_point("init")
    workflow.add_edge("init", "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "respond": "respond",
        },
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge("respond", END)

    _graph_instance = workflow.compile()
    logger.info("[get_agent_graph] Agent Graph 构建完成")
    return _graph_instance
