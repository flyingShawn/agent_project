"""
SSE 流式输出适配模块

文件功能：
    把 LangGraph 的 astream_events 事件流转换成前端可消费的 SSE 事件流。
    同时在流式过程中补发工具状态、图表数据、导出链接和参考来源。

在系统架构中的定位：
    位于 Agent 编排层与 API 层之间，是 Graph 输出对接前端聊天流的适配层。
    chat.py 调用本模块，把 Graph 事件统一转成前端约定的 SSE 格式。

主要使用场景：
    - 捕获 LLM 的 token 流并实时推送到前端
    - 在工具调用前后展示状态文案
    - 在流式结束后补发参考来源、图表和导出结果

关联文件：
    - agent_backend/api/v1/chat.py: 调用 stream_graph_response
    - agent_backend/core/sse.py: 提供 sse_event 事件格式化函数
    - agent_backend/agent/state.py: 定义 AgentState 结构
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from agent_backend.agent.state import AgentState
from agent_backend.core.sse import sse_event

logger = logging.getLogger(__name__)

AGENT_TIMEOUT_SECONDS = 300

_TOOL_STATUS_MESSAGES = {
    "sql_query": "🔍 正在查询数据...",
    "rag_search": "🔍 正在检索知识库...",
    "generate_chart": "📊 正在生成图表...",
    "export_data": "📥 正在导出数据...",
    "metadata_query": "📋 正在查询表结构...",
    "get_current_time": "🕐 正在获取时间...",
    "calculator": "🧮 正在计算...",
    "web_search": "🌐 正在搜索...",
}

_TOOL_COMPLETE_MESSAGES = {
    "sql_query": "✅ 数据查询完成，正在整理结果...",
    "rag_search": "✅ 知识检索完成，正在整理结果...",
    "generate_chart": "✅ 图表生成完成...",
    "export_data": "✅ 数据导出完成...",
    "metadata_query": "✅ 表结构查询完成...",
    "get_current_time": "✅ 时间获取完成...",
    "calculator": "✅ 计算完成...",
    "web_search": "✅ 搜索完成...",
}


async def _aiter_with_timeout(aiter: AsyncIterator, timeout: float) -> AsyncIterator:
    """为异步事件流增加总超时限制，避免单次请求无限挂起。"""
    deadline = asyncio.get_event_loop().time() + timeout
    async for item in aiter:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError()
        yield item


async def stream_graph_response(
    graph: Any,
    initial_state: dict,
) -> AsyncIterator[str]:
    """把 Graph 事件流转换成 SSE 输出，并在结束时补发附加结果。"""
    logger.info(f"\n[stream] 开始流式输出 (astream_events v2), 超时: {AGENT_TIMEOUT_SECONDS}秒")

    references: list[str] = []
    chart_configs: list[dict] = []
    export_results: list[dict] = []
    first_token = True
    has_status_shown = False

    timed_stream = _aiter_with_timeout(
        graph.astream_events(initial_state, version="v2"),
        AGENT_TIMEOUT_SECONDS,
    )

    try:
        async for event in timed_stream:
            kind = event["event"]
            name = event.get("name", "")

            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    metadata = event.get("metadata", {})
                    node = metadata.get("langgraph_node", "")
                    if node not in ("agent", "respond"):
                        continue

                    if first_token:
                        if has_status_shown:
                            yield sse_event("replace", "")
                            has_status_shown = False
                        logger.info("\n[stream] 收到首个 token，流式输出已生效")
                        first_token = False
                    yield sse_event("delta", chunk.content)

            elif kind == "on_chat_model_end":
                metadata = event.get("metadata", {})
                node = metadata.get("langgraph_node", "")
                if node not in ("agent", "respond"):
                    continue

                output = event["data"].get("output")
                has_tool_calls = hasattr(output, "tool_calls") and output.tool_calls
                if has_tool_calls:
                    yield sse_event("replace", "")
                    tool_names = [tool_call.get("name", "") for tool_call in output.tool_calls]
                    status_msg = _TOOL_STATUS_MESSAGES.get(
                        tool_names[0] if tool_names else "",
                        "⏳ 正在处理...",
                    )
                    yield sse_event("status", status_msg)
                    has_status_shown = True
                    first_token = True
                    logger.info(f"\n[stream] LLM调用完成(工具调用): {name}, tools={tool_names}")
                else:
                    logger.info(f"\n[stream] LLM调用完成(直接回答): {name}")

            elif kind == "on_tool_start":
                logger.info(f"\n[stream] 开始执行工具: {name}")
                if has_status_shown:
                    yield sse_event("status", _TOOL_STATUS_MESSAGES.get(name, "⏳ 正在处理..."))

            elif kind == "on_tool_end":
                logger.info(f"\n[stream] 工具执行完成: {name}")
                if has_status_shown:
                    yield sse_event("status", _TOOL_COMPLETE_MESSAGES.get(name, "✅ 处理完成..."))

                output = event["data"].get("output")
                if isinstance(output, str):
                    output_str = output
                elif hasattr(output, "content"):
                    output_str = str(output.content)
                else:
                    output_str = ""

                if name == "sql_query" and output_str:
                    try:
                        parsed = json.loads(output_str)
                        if "download_url" in parsed:
                            export_results.append(
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
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif name == "rag_search" and output_str:
                    try:
                        parsed = json.loads(output_str)
                        if parsed.get("sources"):
                            references.extend(parsed["sources"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif name == "generate_chart" and output_str:
                    try:
                        parsed = json.loads(output_str)
                        if "echarts_option" in parsed:
                            chart_configs.append(parsed)
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif name == "export_data" and output_str:
                    try:
                        parsed = json.loads(output_str)
                        if "download_url" in parsed:
                            export_results.append(parsed)
                    except (json.JSONDecodeError, TypeError):
                        pass

    except asyncio.TimeoutError:
        logger.warning(f"\n[stream] Agent执行超时({AGENT_TIMEOUT_SECONDS}秒)，强制结束")
        yield sse_event(
            "error",
            {
                "error": "抱歉，处理时间有点长，我已经尽力了但还是没能完成。请尝试简化您的问题，或者稍后再试试吧~",
            },
        )
        return
    except Exception as exc:
        logger.error(f"[stream] 流式输出异常: {type(exc).__name__}: {exc}")
        import traceback

        logger.error(traceback.format_exc())
        yield sse_event("error", {"error": "非常抱歉，查询失败，请稍后再试"})
        return

    if references:
        yield sse_event("delta", "\n\n---\n\n**📚 参考来源：**\n")
        yield sse_event("delta", "\n".join(references))

    for chart in chart_configs:
        yield sse_event("chart", chart)

    seen_urls: set[str] = set()
    for export_item in export_results:
        url = export_item.get("download_url", "")
        if url and url in seen_urls:
            logger.info(f"\n[stream] 跳过重复导出链接: {url}")
            continue
        if url:
            seen_urls.add(url)
        yield sse_event("export", export_item)

    logger.info("\n[stream] 流式输出完成")
