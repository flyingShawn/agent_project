"""
LangGraph Agent节点定义模块

文件功能：
    定义LangGraph StateGraph中的所有节点函数和条件路由逻辑。
    每个节点接收AgentState，执行业务逻辑，返回状态更新。

在系统架构中的定位：
    位于Agent编排层核心，是StateGraph节点和边的实际实现。
    graph.py负责编排，nodes.py负责执行。

主要使用场景：
    - StateGraph构建时注册节点函数
    - 条件路由判断（should_continue）

核心函数：
    - init_node: 初始化节点，注入系统Prompt和初始状态
    - agent_node: LLM决策节点，调用LLM决定是否使用工具
    - tool_result_node: 工具执行节点，调用具体Tool并收集结果
    - should_continue: 条件路由，判断继续调用工具还是进入回答
    - respond_node: 最终回答节点（当前为空操作，回答由LLM流式输出）

专有技术说明：
    - agent_node使用llm.bind_tools(ALL_TOOLS)绑定工具，LLM通过Tool Calling自主决策
    - tool_result_node将Tool执行结果转为ToolMessage写回messages，LLM可继续决策
    - 安全校验失败时返回错误ToolMessage而非抛异常，让LLM有机会修正
    - tool_call_count限制最大迭代次数，防止无限循环

关联文件：
    - agent_backend/agent/graph.py: 注册本模块的节点函数
    - agent_backend/agent/llm.py: get_llm提供LLM实例
    - agent_backend/agent/prompts.py: SYSTEM_PROMPT系统提示词
    - agent_backend/agent/tools/: ALL_TOOLS工具列表
    - agent_backend/agent/state.py: AgentState状态定义
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from agent_backend.agent.llm import get_llm
from agent_backend.agent.prompts import SYSTEM_PROMPT
from agent_backend.agent.state import AgentState
from agent_backend.agent.tools import ALL_TOOLS
from agent_backend.agent.tools.sql_tool import _SqlJsonEncoder

logger = logging.getLogger(__name__)


def init_node(state: AgentState) -> dict:
    """
    初始化节点，注入系统Prompt和初始状态字段。

    检查messages中是否已包含SystemMessage，若没有则注入SYSTEM_PROMPT。
    同时初始化工具调用计数和结果累积列表。

    参数：
        state: 当前AgentState

    返回：
        dict: 包含messages、tool_call_count、max_tool_calls及各结果列表的初始值
    """
    messages = state.get("messages", [])
    has_system = any(isinstance(m, SystemMessage) for m in messages)
    if not has_system:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

    return {
        "messages": messages,
        "tool_call_count": 0,
        "max_tool_calls": state.get("max_tool_calls", 5),
        "sql_results": [],
        "rag_results": [],
        "metadata_results": [],
        "time_results": [],
        "calculator_results": [],
        "chart_configs": [],
        "export_results": [],
        "web_search_results": [],
        "data_tables": [],
        "references": [],
    }


def agent_node(state: AgentState) -> dict:
    """
    LLM决策节点，调用绑定了Tools的LLM决定下一步操作。

    LLM根据对话历史和工具描述，自主决定：
    - 调用哪些工具（返回tool_calls）
    - 直接回答用户（返回文本内容）

    参数：
        state: 当前AgentState，包含对话历史和工具执行结果

    返回：
        dict: {"messages": [AIMessage]}，AIMessage可能包含tool_calls或直接内容

    性能注意事项：
        - 使用invoke阻塞调用，耗时由LLM推理速度决定
        - 流式输出由stream.py的astream_events捕获on_chat_model_stream实现
    """
    t0 = time.time()
    llm = get_llm()
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    messages = state["messages"]
    logger.info(f"\n[agent_node] 调用LLM, 消息数: {len(messages)}, 已调用工具: {state.get('tool_call_count', 0)}")

    response = llm_with_tools.invoke(messages)

    elapsed = time.time() - t0
    if hasattr(response, "tool_calls") and response.tool_calls:
        tool_names = [tc["name"] for tc in response.tool_calls]
        logger.info(f"\n[agent_node] LLM决定调用工具: {tool_names}, 耗时: {elapsed:.2f}秒")
    else:
        logger.info(f"\n[agent_node] LLM直接回答, 耗时: {elapsed:.2f}秒")

    return {"messages": [response]}


def tool_result_node(state: AgentState) -> dict:
    """
    工具执行节点，遍历LLM返回的tool_calls并依次执行对应Tool。

    执行流程：
    1. 解析AIMessage中的tool_calls列表
    2. 根据tool_name查找对应的Tool函数
    3. 调用Tool.invoke执行，收集结果
    4. 将结果转为ToolMessage写回messages
    5. 累积data_tables和references用于最终输出

    参数：
        state: 当前AgentState，messages末尾应为包含tool_calls的AIMessage

    返回：
        dict: 包含tool_messages、更新后的tool_call_count和各结果列表

    安全注意事项：
        - SQL安全校验在sql_query Tool内部执行，校验失败返回错误ToolMessage
        - 工具执行异常时返回错误信息而非抛异常，让LLM有机会修正
    """
    t0 = time.time()
    last_message = state["messages"][-1]

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {}

    tool_call_count = state.get("tool_call_count", 0)
    tool_messages = []
    new_data_tables = list(state.get("data_tables", []))
    new_references = list(state.get("references", []))
    new_sql_results = list(state.get("sql_results", []))
    new_rag_results = list(state.get("rag_results", []))
    new_metadata_results = list(state.get("metadata_results", []))
    new_time_results = list(state.get("time_results", []))
    new_calculator_results = list(state.get("calculator_results", []))
    new_chart_configs = list(state.get("chart_configs", []))
    new_export_results = list(state.get("export_results", []))
    new_web_search_results = list(state.get("web_search_results", []))

    tool_map = {t.name: t for t in ALL_TOOLS}

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]

        logger.info(f"\n[tool_result_node] 执行工具: {tool_name}, 参数: {tool_args}")
        t_tool = time.time()

        try:
            selected_tool = tool_map.get(tool_name)
            if not selected_tool:
                result = json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)
            else:
                result = selected_tool.invoke(tool_args)

            tool_call_count += 1
            logger.info(f"\n[tool_result_node] 工具 {tool_name} 执行完成, 耗时: {time.time() - t_tool:.2f}秒")

            if tool_name == "sql_query":
                try:
                    parsed = json.loads(result)
                    if "data_table" in parsed and parsed["data_table"]:
                        new_data_tables.append(parsed["data_table"])
                    new_sql_results.append(parsed)
                    result_for_llm = {k: v for k, v in parsed.items() if k != "sql"}
                    if "download_url" in parsed:
                        new_export_results.append({
                            "download_url": parsed["download_url"],
                            "filename": parsed.get("download_filename", ""),
                        })
                    result = json.dumps(result_for_llm, ensure_ascii=False, cls=_SqlJsonEncoder)
                except (json.JSONDecodeError, TypeError):
                    pass

            elif tool_name == "rag_search":
                try:
                    parsed = json.loads(result)
                    if "sources" in parsed:
                        new_references.extend(parsed["sources"])
                    new_rag_results.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    pass

            elif tool_name == "metadata_query":
                new_metadata_results.append({"result": result})

            elif tool_name == "get_current_time":
                try:
                    parsed = json.loads(result)
                    new_time_results.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    new_time_results.append({"result": result})

            elif tool_name == "calculator":
                try:
                    parsed = json.loads(result)
                    new_calculator_results.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    new_calculator_results.append({"result": result})

            elif tool_name == "generate_chart":
                try:
                    parsed = json.loads(result)
                    new_chart_configs.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    new_chart_configs.append({"result": result})

            elif tool_name == "export_data":
                try:
                    parsed = json.loads(result)
                    new_export_results.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    new_export_results.append({"result": result})

            elif tool_name == "web_search":
                try:
                    parsed = json.loads(result)
                    new_web_search_results.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    new_web_search_results.append({"result": result})

        except Exception as e:
            logger.error(f"[tool_result_node] 工具执行异常: {tool_name}: {e}")
            result = json.dumps({"error": f"工具执行失败: {type(e).__name__}: {e}"}, ensure_ascii=False)

        tool_messages.append(
            ToolMessage(content=str(result), tool_call_id=tool_id, name=tool_name)
        )

    logger.info(f"\n[tool_result_node] 所有工具执行完成, 总耗时: {time.time() - t0:.2f}秒")

    return {
        "messages": tool_messages,
        "tool_call_count": tool_call_count,
        "data_tables": new_data_tables,
        "references": new_references,
        "sql_results": new_sql_results,
        "rag_results": new_rag_results,
        "metadata_results": new_metadata_results,
        "time_results": new_time_results,
        "calculator_results": new_calculator_results,
        "chart_configs": new_chart_configs,
        "export_results": new_export_results,
        "web_search_results": new_web_search_results,
    }


def should_continue(state: AgentState) -> str:
    """
    条件路由函数，判断Agent应继续调用工具还是进入最终回答。

    路由逻辑：
    - tool_call_count >= max_tool_calls → "respond"（强制结束，防死循环）
    - AIMessage包含tool_calls → "tools"（继续执行工具）
    - 否则 → "respond"（LLM已生成最终回答）

    参数：
        state: 当前AgentState

    返回：
        str: "tools" 或 "respond"
    """
    last_message = state["messages"][-1]
    tool_call_count = state.get("tool_call_count", 0)
    max_tool_calls = state.get("max_tool_calls", 5)

    if tool_call_count >= max_tool_calls:
        logger.info(f"\n[should_continue] 达到最大工具调用次数 {max_tool_calls}，进入respond")
        return "respond"

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"

    return "respond"


def respond_node(state: AgentState) -> dict:
    """
    最终回答节点。

    正常情况下LLM的最终回答已通过astream_events流式输出，此节点仅作为终止标记。
    但当达到max_tool_calls被强制截断时，LLM最后一条消息可能包含tool_calls而非文本回答，
    此时需要再调用一次LLM（不绑定工具）让其基于已收集的工具结果生成最终总结。
    """
    last_message = state["messages"][-1]
    tool_call_count = state.get("tool_call_count", 0)
    max_tool_calls = state.get("max_tool_calls", 5)

    if tool_call_count >= max_tool_calls and isinstance(last_message, AIMessage) and last_message.tool_calls:
        logger.info(f"\n[respond_node] 达到max_tool_calls且LLM仍在请求工具调用，强制生成最终回答")
        llm = get_llm()
        summary_prompt = SystemMessage(
            content="你已达到最大工具调用次数限制，无法再调用任何工具。请基于已收集到的工具执行结果，"
                    "为用户生成一个完整、有用的最终回答。如果已有查询结果数据，请务必在回答中包含具体的数据内容。"
        )
        messages = state["messages"] + [summary_prompt]
        try:
            response = llm.invoke(messages)
            logger.info(f"\n[respond_node] 强制总结回答生成完成")
            return {"messages": [response]}
        except Exception as e:
            logger.error(f"\n[respond_node] 强制总结回答生成失败: {e}")
            return {}

    return {}
