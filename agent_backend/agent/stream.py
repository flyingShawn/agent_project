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
    - event: delta    → data: "文本片段"（逐token流式）
    - event: start    → data: {"intent":"agent","session_id":"..."}
    - event: done     → data: {"route":"agent","session_id":"...","meta":{}}
    - event: error    → data: {"error":"..."}
    - event: tool_start → data: {"tool":"sql_query"}（可选，前端可忽略）
    - event: tool_end   → data: {"tool":"sql_query"}（可选，前端可忽略）

专有技术说明：
    - 使用graph.astream_events(version="v2")捕获细粒度事件
    - 仅处理langgraph_node="agent"的LLM流式事件，过滤工具内部LLM调用
    - 缓冲agent节点的LLM输出，在on_chat_model_end时判断是否为tool_call：
      tool_call内容丢弃（不输出到前端），普通文本才流式推送
    - on_tool_end事件中提取data_tables和references用于末尾追加
    - 异步生成器配合FastAPI的StreamingResponse实现真正的流式推送

关联文件：
    - agent_backend/agent/graph.py: 提供Graph实例
    - agent_backend/api/v1/chat.py: 调用stream_graph_response并包装为StreamingResponse
    - agent_backend/agent/state.py: AgentState状态定义
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from agent_backend.agent.state import AgentState

logger = logging.getLogger(__name__)


def _sse_event(event: str, data: str | dict) -> str:
    """
    格式化SSE事件字符串。

    将事件名和数据格式化为标准SSE协议格式：
    event: <event_name>\ndata: <data_line>\n\n

    参数：
        event: SSE事件名称（如delta/done/error）
        data: 事件数据，字符串或字典（字典自动转JSON）

    返回：
        str: 格式化后的SSE事件字符串
    """
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False)
    lines = data.split("\n")
    return f"event: {event}\n" + "".join(f"data: {line}\n" for line in lines) + "\n"


async def stream_graph_response(
    graph: Any,
    initial_state: dict,
) -> AsyncIterator[str]:
    """
    将LangGraph事件流转换为SSE事件流。

    通过graph.astream_events捕获LLM token流和工具执行事件，
    逐事件转换为SSE格式yield给前端。同时在工具执行完成时
    收集data_tables和references，在流式输出末尾追加。

    参数：
        graph: 编译后的LangGraph StateGraph实例
        initial_state: 初始AgentState字典

    返回：
        AsyncIterator[str]: SSE事件字符串的异步迭代器

    性能注意事项：
        - 首个token到达时间取决于LLM推理速度和Tool执行耗时
        - on_chat_model_stream事件实现真正的逐token流式推送
    """
    logger.info("\n[stream] 开始流式输出 (astream_events v2)")

    data_tables: list[str] = []
    references: list[str] = []
    chart_configs: list[dict] = []
    export_results: list[dict] = []
    first_token = True
    pending_chunks: list[str] = []
    pending_run_id: str | None = None

    try:
        async for event in graph.astream_events(initial_state, version="v2"):
            kind = event["event"]
            name = event.get("name", "")
            run_id = event.get("run_id", "")

            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    metadata = event.get("metadata", {})
                    if metadata.get("langgraph_node") != "agent":
                        continue
                    if pending_run_id and pending_run_id != run_id:
                        for c in pending_chunks:
                            yield _sse_event("delta", c)
                        pending_chunks = []
                    pending_run_id = run_id
                    pending_chunks.append(chunk.content)

            elif kind == "on_chat_model_end":
                metadata = event.get("metadata", {})
                if metadata.get("langgraph_node") != "agent":
                    continue
                output = event["data"].get("output")
                has_tool_calls = hasattr(output, "tool_calls") and output.tool_calls
                if has_tool_calls:
                    pending_chunks = []
                    pending_run_id = None
                else:
                    if pending_chunks:
                        if first_token:
                            logger.info("\n[stream] 收到首个token，流式输出已生效")
                            first_token = False
                        for c in pending_chunks:
                            yield _sse_event("delta", c)
                        pending_chunks = []
                        pending_run_id = None
                logger.info(f"\n[stream] LLM调用完成: {name}, has_tool_calls={has_tool_calls}")

            elif kind == "on_tool_start":
                logger.info(f"\n[stream] 开始执行工具: {name}")

            elif kind == "on_tool_end":
                logger.info(f"\n[stream] 工具执行完成: {name}")
                output = event["data"].get("output")
                output_str = ""
                if isinstance(output, str):
                    output_str = output
                elif hasattr(output, "content"):
                    output_str = str(output.content)

                if name == "sql_query" and output_str:
                    try:
                        parsed = json.loads(output_str)
                        if parsed.get("data_table"):
                            data_tables.append(parsed["data_table"])
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

    except Exception as e:
        logger.error(f"[stream] 流式输出异常: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        yield _sse_event("error", {"error": "非常抱歉，查询失败，请稍后再试"})
        return

    if data_tables:
        for table in data_tables:
            yield _sse_event("delta", f"\n\n{table}")

    if references:
        yield _sse_event("delta", "\n\n---\n\n**📚 参考来源：**\n")
        yield _sse_event("delta", "\n".join(references))

    for chart in chart_configs:
        yield _sse_event("chart", chart)

    for export_item in export_results:
        yield _sse_event("export", export_item)

    logger.info("\n[stream] 流式输出完成")
