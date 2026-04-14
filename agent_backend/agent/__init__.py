"""
Agent模块入口

文件功能：
    LangGraph Agent编排框架的顶层入口，对外暴露编译后的Agent Graph实例。

在系统架构中的定位：
    作为Agent模块的公共API，供API层（api/v1/chat.py）调用获取Graph实例。

核心导出：
    - get_agent_graph: 获取编译后的LangGraph StateGraph单例

关联文件：
    - agent_backend/agent/graph.py: Graph构建逻辑的实际实现
    - agent_backend/api/v1/chat.py: 通过此模块获取Graph实例
"""
from agent_backend.agent.graph import get_agent_graph
