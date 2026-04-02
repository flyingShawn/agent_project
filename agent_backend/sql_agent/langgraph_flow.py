"""
LangGraph工作流模块

文件目的：
    - 使用LangGraph组织SQL生成流程
    - 提供状态机式的生成流程
    - 支持多步骤处理和验证

核心功能：
    1. 定义状态图（StateGraph）
    2. 组织生成流程节点
    3. 执行状态转换
    4. 返回生成的SQL

主要函数：
    - run_text_to_sql_graph(): 运行Text-to-SQL状态图

工作流程：
    1. 输入prompt
    2. LLM生成节点 -> 生成draft_sql
    3. 规整节点 -> normalize_sql
    4. 返回最终SQL

状态定义：
    - prompt: 输入提示词
    - draft_sql: 生成的SQL草稿

使用场景：
    - SQL生成流程编排
    - 多步骤SQL生成

相关文件：
    - agent_backend/sql_agent/service.py: SQL生成服务
    - agent_backend/sql_agent/llm_clients.py: LLM客户端
"""
from __future__ import annotations

from typing import Any, TypedDict

from agent_backend.core.errors import AppError
from agent_backend.sql_agent.llm_clients import LlmClient
from agent_backend.sql_agent.sql_safety import normalize_sql


class _GraphState(TypedDict, total=False):
    prompt: str
    draft_sql: str


def run_text_to_sql_graph(*, prompt: str, llm: LlmClient) -> str:
    """
    使用 LangGraph 组织一个最小的“生成 -> 规整”状态机。

    说明：
        - 该图只负责把 prompt 交给大模型并产出 draft_sql；
        - 安全校验与权限包装在 service 层完成，避免图里混入过多业务细节。
    """
    try:
        from langgraph.graph import END, StateGraph
    except Exception as e:
        raise AppError(
            code="dependency_missing",
            message="缺少依赖：langgraph",
            http_status=500,
            details={"reason": str(e)},
        ) from e

    def llm_generate(state: _GraphState) -> _GraphState:
        sql = llm.generate(state["prompt"])
        return {"draft_sql": normalize_sql(sql)}

    graph = StateGraph(_GraphState)
    graph.add_node("llm_generate", llm_generate)
    graph.set_entry_point("llm_generate")
    graph.add_edge("llm_generate", END)

    app = graph.compile()
    out: dict[str, Any] = app.invoke({"prompt": prompt})
    draft = (out.get("draft_sql") or "").strip()
    if not draft:
        raise AppError(code="llm_empty_response", message="大模型返回为空", http_status=502)
    return draft
