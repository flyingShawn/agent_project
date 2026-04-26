"""
LangGraph Agent 节点定义模块

文件功能：
    定义 LangGraph StateGraph 中的节点函数和条件路由逻辑。
    各节点通过 AgentState 读取上下文、执行 LLM 或工具调用，并返回状态增量。

在系统架构中的定位：
    位于 Agent 编排层核心，负责承接 graph.py 中注册的节点执行逻辑。
    chat.py 负责构造初始状态，nodes.py 负责具体处理每一步状态流转。

主要使用场景：
    - 初始化图状态字段
    - 调用 LLM 决策是否使用工具
    - 执行工具并把结果写回消息列表
    - 在达到工具调用上限时生成兜底总结

关联文件：
    - agent_backend/agent/graph.py: 注册本模块中的节点与边
    - agent_backend/agent/state.py: 定义 AgentState 结构
    - agent_backend/api/v1/chat.py: 构造初始消息列表并写入系统提示词
    - agent_backend/agent/tools/__init__.py: 导出 ALL_TOOLS
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from agent_backend.agent.state import AgentState
from agent_backend.agent.tools import ALL_TOOLS
from agent_backend.agent.tools.sql_tool import _SqlJsonEncoder
from agent_backend.core.config import get_summary_prompt
from agent_backend.llm.factory import get_llm

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS_FALLBACK_MESSAGE = (
    "抱歉，我已经达到本次信息收集上限，但暂时还没找到足够可靠的结果。"
    "建议你换个角度再问，或者缩小查询范围后重试。"
)
EMPTY_SQL_FINALIZE_SYSTEM_PROMPT = (
    "上一轮 sql_query 已明确没有查到符合条件的数据，或统计结果为 0。"
    "请直接基于已有结果给出最终回答："
    "1. 用友好、自然的中文告诉用户暂未查询到相关数据；"
    "2. 如有必要，可补充 1 到 2 个常见原因，例如时间范围内暂无记录或筛选条件较严；"
    "3. 不要再次调用任何工具；"
    "4. 不要输出 SQL 或技术实现细节。"
)


def _format_log_content(content: Any) -> str:
    """把消息内容稳定转成字符串，便于 warning 日志完整输出。"""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False, default=str)
    except TypeError:
        return str(content)


def _compact_log_content(content: str, head: int = 20, tail: int = 200) -> str:
    """长日志内容只保留首尾，避免整段上下文刷屏。"""
    if len(content) <= head + tail:
        return content
    return f"{content[:head]}\n...\n{content[-tail:]}"


def _message_role_for_log(message: Any) -> str:
    """把 LangChain 消息类型映射成更直观的日志角色名。"""
    message_type = getattr(message, "type", "") or message.__class__.__name__
    role_map = {
        "system": "system",
        "human": "user",
        "ai": "assistant",
        "tool": "tool",
    }
    return role_map.get(message_type, message_type)


def _format_messages_for_llm_log(messages: list[Any]) -> str:
    """按顺序格式化消息列表，方便排查最终送给 LLM 的完整上下文。"""
    parts: list[str] = []
    for index, message in enumerate(messages, start=1):
        role = _message_role_for_log(message)
        block = [f"--- message {index} [{role}] ---"]

        # 对于系统消息，只显示标记，不显示内容
        if role != "system":
            content = _format_log_content(getattr(message, "content", message))
            block.append(_compact_log_content(content))
        else:
            content = _format_log_content(getattr(message, "content", message))
            block.append(_compact_log_content(content, head=50, tail=800))


        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            block.append(f"tool_calls: {_format_log_content(tool_calls)}")

        tool_call_id = getattr(message, "tool_call_id", None)
        if tool_call_id:
            block.append(f"tool_call_id: {tool_call_id}")

        name = getattr(message, "name", None)
        if name:
            block.append(f"name: {name}")

        parts.append("\n".join(block))
    return "\n\n".join(parts)


def _format_system_prompts_for_llm_log(messages: list[Any]) -> str:
    """提取消息列表中的所有系统提示词，单独打印用于核对。"""
    system_prompts = [
        _format_log_content(message.content)
        for message in messages
        if isinstance(message, SystemMessage)
    ]
    if not system_prompts:
        return "(未找到 SystemMessage)"
    return "\n\n".join(system_prompts)


def _log_final_llm_messages(tag: str, messages: list[Any]) -> None:
    """只在最终收尾时打印一次完整LLM输入，避免每轮工具迭代都刷屏。"""
    logger.warning(
        f"\n[{tag}] 提供给LLM的聊天内容与所有提示词组合之后的内容:\n{_format_messages_for_llm_log(messages)}"
    )


def _build_sql_query_arg_error(tool_args: Any) -> str | None:
    """在执行 sql_query 前做最小参数校验，避免模型传错字段后直接打库。"""
    if isinstance(tool_args, dict):
        question = tool_args.get("question")
        if isinstance(question, str) and question.strip():
            return None
    else:
        question = None

    if not isinstance(tool_args, dict):
        reason = "tool_args_not_object"
    elif "sql" in tool_args:
        reason = "received_sql_instead_of_question"
    elif "question" in tool_args:
        reason = "question_empty"
    else:
        reason = "question_missing"

    logger.warning(
        "\n[tool_result_node] sql_query 参数不合法，拒绝执行。原因=%s | 原始参数=%s",
        reason,
        _format_log_content(tool_args),
    )
    return json.dumps(
        {
            "error": "sql_query 调用参数错误",
            "error_code": "sql_query_invalid_args",
            "reason": reason,
            "hint": 'sql_query 只接受 question（自然语言问题），不要传 sql；示例：{"question":"查看客户端在线状态"}',
            "received_args": tool_args,
        },
        ensure_ascii=False,
    )


def _has_meaningful_content(message: Any) -> bool:
    """判断模型返回里是否真的带了可展示的文本内容。"""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        for item in content:
            if isinstance(item, str) and item.strip():
                return True
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    return True
    return False


def _should_force_finalize_after_sql(parsed: Any) -> bool:
    """空明细或统计值为 0 时直接收口，避免同一轮对话反复重查。"""
    return isinstance(parsed, dict) and not parsed.get("error") and parsed.get("result_state") == "empty"


def init_node(state: AgentState) -> dict[str, Any]:
    """
    初始化图运行过程中会累计的状态字段。

    注意：
        系统提示词已经在 chat.py 构造 initial_state 时放到 messages 第一位。
        这里不要再返回完整 messages 列表，否则会被 add_messages 追加合并，
        重新引入“系统提示词跑到用户问题后面”的顺序问题。
    """
    return {
        "tool_call_count": 0,
        "max_tool_calls": state.get("max_tool_calls", 10),
        "sql_results": [],
        "rag_results": [],
        "metadata_results": [],
        "time_results": [],
        "calculator_results": [],
        "chart_configs": [],
        "export_results": [],
        "web_search_results": [],
        "force_finalize_after_sql": False,
        "force_finalize_reason": "",
        "data_tables": [],
        "references": [],
    }


def agent_node(state: AgentState) -> dict[str, Any]:
    """调用绑定工具的 LLM，让模型决定直接回答还是发起工具调用。"""
    t0 = time.time()
    llm = get_llm()

    messages = list(state["messages"])
    logger.info(
        f"\n[agent_node] 调用LLM, 消息数: {len(messages)}, 已调用工具: {state.get('tool_call_count', 0)}"
    )

    final_messages = messages
    if state.get("force_finalize_after_sql"):
        logger.info("\n[agent_node] 检测到空结果终态，改为直接生成最终回答")
        finalize_prompt = EMPTY_SQL_FINALIZE_SYSTEM_PROMPT
        if state.get("force_finalize_reason"):
            finalize_prompt = f"{EMPTY_SQL_FINALIZE_SYSTEM_PROMPT}\n补充提示：{state['force_finalize_reason']}"
        final_messages = messages + [SystemMessage(content=finalize_prompt)]
        response = llm.invoke(final_messages)
    else:
        llm_with_tools = llm.bind_tools(ALL_TOOLS)
        response = llm_with_tools.invoke(messages)

    elapsed = time.time() - t0
    if getattr(response, "tool_calls", None):
        tool_names = [tool_call["name"] for tool_call in response.tool_calls]
        logger.info(f"\n[agent_node] LLM决定调用工具: {tool_names}, 耗时: {elapsed:.2f}秒")
    else:
        logger.info(f"\n[agent_node] LLM直接回答, 耗时: {elapsed:.2f}秒")

    return {
        "messages": [response],
        "last_llm_input_messages": final_messages,
    }


def tool_result_node(state: AgentState) -> dict[str, Any]:
    """执行 LLM 请求的工具，并把结果整理成 ToolMessage 回写到状态中。"""
    t0 = time.time()
    last_message = state["messages"][-1]

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {}

    tool_call_count = state.get("tool_call_count", 0)
    tool_messages: list[ToolMessage] = []
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
    force_finalize_after_sql = bool(state.get("force_finalize_after_sql", False))
    force_finalize_reason = state.get("force_finalize_reason", "")
    pre_sql_context = state.get("pre_sql_context")
    pre_sql_context_consumed = False

    tool_map = {tool.name: tool for tool in ALL_TOOLS}

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
            elif tool_name == "sql_query":
                arg_error = _build_sql_query_arg_error(tool_args)
                if arg_error is not None:
                    result = arg_error
                elif pre_sql_context and not pre_sql_context_consumed:
                    enhanced_args = dict(tool_args)
                    enhanced_args["pre_sql_context"] = pre_sql_context
                    result = selected_tool.invoke(enhanced_args)
                    pre_sql_context_consumed = True
                    logger.info("\n[tool_result_node] sql_query 使用预检索上下文，跳过RAG检索")
                else:
                    result = selected_tool.invoke(tool_args)
            else:
                result = selected_tool.invoke(tool_args)

            tool_call_count += 1
            logger.info(
                f"\n[tool_result_node] 工具 {tool_name} 执行完成, 耗时: {time.time() - t_tool:.2f}秒"
            )

            if tool_name == "sql_query":
                try:
                    parsed = json.loads(result)
                    if parsed.get("data_table"):
                        new_data_tables.append(parsed["data_table"])
                    new_sql_results.append(parsed)
                    if _should_force_finalize_after_sql(parsed):
                        force_finalize_after_sql = True
                        force_finalize_reason = parsed.get("summary_hint", "")
                    if "download_url" in parsed:
                        new_export_results.append(
                            {
                                "download_url": parsed["download_url"],
                                "filename": parsed.get("download_filename", ""),
                                "row_count": parsed.get("row_count", 0),
                                "preview_row_count": parsed.get("preview_row_count", 0),
                                "export_row_count": parsed.get("export_row_count", 0),
                                "has_more": bool(parsed.get("has_more", False)),
                                "overflow_capped": bool(parsed.get("overflow_capped", False)),
                            }
                        )
                    result = json.dumps(
                        {key: value for key, value in parsed.items() if key != "sql"},
                        ensure_ascii=False,
                        cls=_SqlJsonEncoder,
                    )
                except (json.JSONDecodeError, TypeError):
                    pass

            elif tool_name == "rag_search":
                try:
                    parsed = json.loads(result)
                    if parsed.get("sources"):
                        new_references.extend(parsed["sources"])
                    new_rag_results.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    pass

            elif tool_name == "metadata_query":
                new_metadata_results.append({"result": result})

            elif tool_name == "get_current_time":
                try:
                    new_time_results.append(json.loads(result))
                except (json.JSONDecodeError, TypeError):
                    new_time_results.append({"result": result})

            elif tool_name == "calculator":
                try:
                    new_calculator_results.append(json.loads(result))
                except (json.JSONDecodeError, TypeError):
                    new_calculator_results.append({"result": result})

            elif tool_name == "generate_chart":
                try:
                    new_chart_configs.append(json.loads(result))
                except (json.JSONDecodeError, TypeError):
                    new_chart_configs.append({"result": result})

            elif tool_name == "export_data":
                try:
                    new_export_results.append(json.loads(result))
                except (json.JSONDecodeError, TypeError):
                    new_export_results.append({"result": result})

            elif tool_name == "web_search":
                try:
                    new_web_search_results.append(json.loads(result))
                except (json.JSONDecodeError, TypeError):
                    new_web_search_results.append({"result": result})

        except Exception as exc:
            logger.error(f"[tool_result_node] 工具执行异常: {tool_name}: {exc}")
            result = json.dumps(
                {"error": f"工具执行失败: {type(exc).__name__}: {exc}"},
                ensure_ascii=False,
            )

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
        "force_finalize_after_sql": force_finalize_after_sql,
        "force_finalize_reason": force_finalize_reason,
        "pre_sql_context": None if pre_sql_context_consumed else pre_sql_context,
    }


def should_continue(state: AgentState) -> str:
    """根据最近一次消息和工具调用次数，决定图继续走 tools 还是 respond。"""
    last_message = state["messages"][-1]
    tool_call_count = state.get("tool_call_count", 0)
    max_tool_calls = state.get("max_tool_calls", 10)

    if tool_call_count >= max_tool_calls:
        logger.info(f"\n[should_continue] 达到最大工具调用次数 {max_tool_calls}，进入 respond")
        return "respond"

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"

    final_messages = state.get("last_llm_input_messages") or state["messages"]
    _log_final_llm_messages("agent_final", final_messages)
    return "respond"


def respond_node(state: AgentState) -> dict[str, Any]:
    """
    在达到工具调用上限且最后一条仍是 tool_calls 时，生成兜底总结回答。

    正常情况下最终回答已经在流式阶段输出，这里只处理“工具迭代被强制截断”的收尾场景。
    """
    last_message = state["messages"][-1]
    tool_call_count = state.get("tool_call_count", 0)
    max_tool_calls = state.get("max_tool_calls", 10)

    if tool_call_count >= max_tool_calls and isinstance(last_message, AIMessage) and last_message.tool_calls:
        logger.info("\n[respond_node] 达到 max_tool_calls，强制生成最终总结回答")
        llm = get_llm()
        summary_prompt = SystemMessage(content=get_summary_prompt())
        system_messages = [message for message in state["messages"] if isinstance(message, SystemMessage)]
        non_system_messages = [
            message for message in state["messages"] if not isinstance(message, SystemMessage)
        ]
        messages = system_messages + [summary_prompt] + non_system_messages
        _log_final_llm_messages("respond_node", messages)
        try:
            response = llm.invoke(messages)
            if not _has_meaningful_content(response):
                logger.warning("\n[respond_node] 强制总结为空，改为返回固定兜底文案")
                response = AIMessage(content=MAX_TOOL_CALLS_FALLBACK_MESSAGE)
            logger.info("\n[respond_node] 强制总结回答生成完成")
            return {"messages": [response]}
        except Exception as exc:
            logger.error(f"\n[respond_node] 强制总结回答生成失败: {exc}")
            return {"messages": [AIMessage(content=MAX_TOOL_CALLS_FALLBACK_MESSAGE)]}

    return {}
