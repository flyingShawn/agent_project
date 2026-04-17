"""
SSE流式输出适配模块

文件功能：
    将LangGraph的astream_events事件流转换为SSE（Server-Sent Events）格式，
    实现逐token流式输出到前端。同时收集工具执行结果中的数据表格和参考来源，
    在流式输出末尾追加。

在系统架构中的定位：
    位于Agent编排层与API层之间，是Graph输出到SSE响应的桥梁。
    替代旧架构中handlers.py手动拼接SSE事件的逻辑。

主要使用场景：
    - api/v1/chat.py的generate()生成器调用stream_graph_response
    - 捕获LLM的token流、工具执行事件，转为SSE事件

核心函数：
    - stream_graph_response: 异步生成器，将Graph事件流转为SSE事件流
    - _sse_event: SSE事件格式化工具函数

SSE事件格式（与前端兼容）：
    - event: delta    → data: "文本片段"（逐token流式追加）
    - event: status   → data: "状态文字"（替换消息内容，如"正在查询..."）
    - event: replace  → data: ""（清空消息内容，准备接收新的流式文本）
    - event: start    → data: {"intent":"agent","session_id":"..."}
    - event: done     → data: {"route":"agent","session_id":"...","meta":{}}
    - event: error    → data: {"error":"..."}

专有技术说明：
    - 使用graph.astream_events(version="v2")捕获细粒度事件
    - 仅处理langgraph_node="agent"的LLM流式事件，过滤工具内部LLM调用
    - agent LLM的chunk立即流式推送（delta事件），实现逐token打字机效果
    - on_chat_model_end检测到tool_call时，发送replace事件清空已推送的SQL内容，
      再发送status事件显示"正在查询..."
    - on_tool_end事件中提取data_tables和references用于末尾追加
    - 异步生成器配合FastAPI的StreamingResponse实现真正的流式推送

关联文件：
    - agent_backend/agent/graph.py: 提供Graph实例
    - agent_backend/api/v1/chat.py: 调用stream_graph_response并包装为StreamingResponse
    - agent_backend/agent/state.py: AgentState状态定义
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from agent_backend.agent.state import AgentState

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


def _sse_event(event: str, data: str | dict) -> str:
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False)
    lines = data.split("\n")
    return f"event: {event}\n" + "".join(f"data: {line}\n" for line in lines) + "\n"


async def _aiter_with_timeout(aiter: AsyncIterator, timeout: float) -> AsyncIterator:
    """为异步迭代器添加总超时限制，超时后抛出asyncio.TimeoutError"""
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
    logger.info("\n[stream] 开始流式输出 (astream_events v2), 超时: {0}秒".format(AGENT_TIMEOUT_SECONDS))

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
            run_id = event.get("run_id", "")

            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    metadata = event.get("metadata", {})
                    node = metadata.get("langgraph_node", "")
                    if node not in ("agent", "respond"):
                        continue
                    if first_token:
                        if has_status_shown:
                            yield _sse_event("replace", "")
                            has_status_shown = False
                        logger.info("\n[stream] 收到首个token，流式输出已生效")
                        first_token = False
                    yield _sse_event("delta", chunk.content)

            elif kind == "on_chat_model_end":
                metadata = event.get("metadata", {})
                node = metadata.get("langgraph_node", "")
                if node not in ("agent", "respond"):
                    continue
                output = event["data"].get("output")
                has_tool_calls = hasattr(output, "tool_calls") and output.tool_calls
                if has_tool_calls:
                    yield _sse_event("replace", "")
                    tool_names = [tc.get("name", "") for tc in output.tool_calls]
                    status_msg = _TOOL_STATUS_MESSAGES.get(
                        tool_names[0] if tool_names else "",
                        "⏳ 正在处理...",
                    )
                    yield _sse_event("status", status_msg)
                    has_status_shown = True
                    first_token = True
                    logger.info(f"\n[stream] LLM调用完成(工具调用): {name}, tools={tool_names}")
                else:
                    logger.info(f"\n[stream] LLM调用完成(直接回答): {name}")

            elif kind == "on_tool_start":
                logger.info(f"\n[stream] 开始执行工具: {name}")
                if has_status_shown:
                    tool_status = _TOOL_STATUS_MESSAGES.get(name, "⏳ 正在处理...")
                    yield _sse_event("status", tool_status)

            elif kind == "on_tool_end":
                logger.info(f"\n[stream] 工具执行完成: {name}")
                if has_status_shown:
                    complete_msg = _TOOL_COMPLETE_MESSAGES.get(name, "✅ 处理完成...")
                    yield _sse_event("status", complete_msg)
                output = event["data"].get("output")
                output_str = ""
                if isinstance(output, str):
                    output_str = output
                elif hasattr(output, "content"):
                    output_str = str(output.content)

                if name == "sql_query" and output_str:
                    try:
                        parsed = json.loads(output_str)
                        if "download_url" in parsed:
                            export_results.append({
                                "download_url": parsed["download_url"],
                                "filename": parsed.get("download_filename", ""),
                            })
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
        yield _sse_event("error", {"error": "抱歉，处理时间有点长，我已经尽力了但还是没能完成。请尝试简化您的问题，或者稍后再试试吧~"})
        return
    except Exception as e:
        logger.error(f"[stream] 流式输出异常: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        yield _sse_event("error", {"error": "非常抱歉，查询失败，请稍后再试"})
        return

    if references:
        yield _sse_event("delta", "\n\n---\n\n**📚 参考来源：**\n")
        yield _sse_event("delta", "\n".join(references))

    for chart in chart_configs:
        yield _sse_event("chart", chart)

    seen_urls = set()
    for export_item in export_results:
        url = export_item.get("download_url", "")
        if url and url in seen_urls:
            logger.info(f"\n[stream] 跳过重复导出链接: {url}")
            continue
        if url:
            seen_urls.add(url)
        yield _sse_event("export", export_item)

    logger.info("\n[stream] 流式输出完成")
