"""
Agent工具定义模块入口

文件功能：
    汇总所有Agent可用的Tool定义，统一导出ALL_TOOLS列表。
    供agent_node绑定到LLM（llm.bind_tools）和tool_result_node查找Tool。

在系统架构中的定位：
    位于Agent工具层入口，是Tool注册的中心化点。
    新增Tool时需在此模块导入并添加到ALL_TOOLS列表。

核心导出：
    - sql_query: SQL查询工具，生成SQL并执行数据库查询
    - rag_search: RAG检索工具，从知识库检索文档片段
    - metadata_query: 元数据查询工具，查询数据库表结构
    - ALL_TOOLS: 所有Tool的列表，供LLM bind_tools使用

关联文件：
    - agent_backend/agent/nodes.py: agent_node绑定ALL_TOOLS，tool_result_node查找Tool
    - agent_backend/agent/tools/sql_tool.py: sql_query实现
    - agent_backend/agent/tools/rag_tool.py: rag_search实现
    - agent_backend/agent/tools/metadata_tool.py: metadata_query实现
"""
from agent_backend.agent.tools.sql_tool import sql_query
from agent_backend.agent.tools.rag_tool import rag_search
from agent_backend.agent.tools.metadata_tool import metadata_query
from agent_backend.agent.tools.time_tool import get_current_time
from agent_backend.agent.tools.calculator_tool import calculator
from agent_backend.agent.tools.chart_tool import generate_chart
from agent_backend.agent.tools.export_tool import export_data
from agent_backend.agent.tools.web_search_tool import web_search

ALL_TOOLS = [
    sql_query,
    rag_search,
    metadata_query,
    get_current_time,
    calculator,
    generate_chart,
    export_data,
    web_search,
]
