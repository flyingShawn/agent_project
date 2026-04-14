"""
聊天API接口模块

文件功能：
    定义聊天相关的HTTP API端点，作为前端与Agent编排层的桥梁。
    接收用户请求，构建AgentState，调用LangGraph Graph，以SSE流式返回结果。

在系统架构中的定位：
    位于API层，是前端与Agent系统的唯一交互入口。
    替代旧架构中chat/handlers.py的硬编码分支路由逻辑。

主要使用场景：
    - 前端发送聊天请求（POST /api/v1/chat）
    - 前端结束对话关闭数据库连接（POST /api/v1/chat/end）

核心端点：
    - chat: 接收ChatRequest，构建初始State，调用Graph，返回SSE流式响应
    - end_chat: 接收EndChatRequest，关闭数据库连接

SSE事件流顺序：
    start → [delta(多次)] → done
    异常时：start → [delta(多次)] → error

专有技术说明：
    - 使用async生成器配合FastAPI StreamingResponse实现真正的流式推送
    - 图片多模态使用LangChain的HumanMessage content数组格式
    - 前端发送的mode字段被Pydantic静默忽略（不再需要auto/sql/rag模式）

关联文件：
    - agent_backend/agent/graph.py: get_agent_graph获取Graph实例
    - agent_backend/agent/stream.py: stream_graph_response实现SSE流式适配
    - agent_backend/sql_agent/connection_manager.py: 数据库连接管理
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from agent_backend.agent.graph import get_agent_graph
from agent_backend.agent.stream import stream_graph_response
from agent_backend.sql_agent.connection_manager import get_connection_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    """聊天请求模型，与前端API契约保持兼容"""
    question: str = Field(min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)
    images_base64: list[str] | None = None
    lognum: str = Field(default="admin")
    token: str | None = None
    session_id: str | None = None


class EndChatRequest(BaseModel):
    """结束对话请求模型"""
    session_id: str = Field(..., min_length=1)


class EndChatResponse(BaseModel):
    """结束对话响应模型"""
    success: bool
    message: str
    session_id: str


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    """
    聊天API端点，接收用户问题并以SSE流式返回Agent回答。

    处理流程：
    1. 构建初始AgentState（含系统Prompt、历史消息、用户问题）
    2. 调用LangGraph Graph执行Agent循环
    3. 通过astream_events捕获LLM token流和工具执行事件
    4. 以SSE格式逐事件推送到前端

    参数：
        req: ChatRequest，包含question/history/images_base64/lognum等

    返回：
        StreamingResponse: SSE流式响应，事件格式为start/delta/done/error
    """
    t_start = time.time()
    conn_manager = get_connection_manager()
    session_id = req.session_id or conn_manager.generate_session_id()

    logger.info(
        f"{'=' * 20}【聊天API入口】收到请求{'=' * 20}\n"
        f"  会话ID: {session_id[:8]}... | 问题: {req.question} | 用户: {req.lognum} | "
        f"历史: {len(req.history)} | 图片: {len(req.images_base64) if req.images_base64 else 0}"
    )

    initial_state = {
        "messages": [],
        "question": req.question,
        "session_id": session_id,
        "lognum": req.lognum,
        "images_base64": req.images_base64,
        "sql_results": [],
        "rag_results": [],
        "metadata_results": [],
        "tool_call_count": 0,
        "max_tool_calls": 5,
        "data_tables": [],
        "references": [],
    }

    for msg in req.history:
        if msg.get("role") == "user":
            initial_state["messages"].append(HumanMessage(content=msg["content"]))
        elif msg.get("role") == "assistant":
            from langchain_core.messages import AIMessage
            initial_state["messages"].append(AIMessage(content=msg["content"]))

    if req.images_base64:
        content = [{"type": "text", "text": req.question}]
        content.extend([
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img}"},
            }
            for img in req.images_base64
        ])
        initial_state["messages"].append(HumanMessage(content=content))
    else:
        initial_state["messages"].append(HumanMessage(content=req.question))

    async def generate():
        """SSE事件生成器，将Graph事件流转为SSE格式推送到前端"""
        logger.info(f"\n【SSE流】开始生成，会话: {session_id[:8]}...")
        yield _sse_event("start", {"intent": "agent", "session_id": session_id})

        try:
            graph = get_agent_graph()
            async for sse_event in stream_graph_response(graph, initial_state):
                yield sse_event

            yield _sse_event(
                "done",
                {
                    "route": "agent",
                    "session_id": session_id,
                    "meta": {},
                },
            )
            logger.info(f"\n【聊天API】请求处理完成，会话: {session_id[:8]}...，总耗时: {time.time() - t_start:.2f}秒")

        except Exception as e:
            logger.error(f"【错误】处理异常: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            yield _sse_event(
                "error",
                {"error": "非常抱歉，查询失败，请稍后再试"},
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/end")
async def end_chat(req: EndChatRequest) -> EndChatResponse:
    """
    结束对话API端点，关闭对应的数据库连接。

    参数：
        req: EndChatRequest，包含session_id

    返回：
        EndChatResponse: 包含success/message/session_id
    """
    logger.info(f"\n【结束对话API】会话ID: {req.session_id[:8]}...")

    try:
        conn_manager = get_connection_manager()
        conn_manager.close_connection(req.session_id, reason="用户主动结束对话")

        return EndChatResponse(
            success=True,
            message="对话已结束，数据库连接已关闭",
            session_id=req.session_id,
        )
    except Exception as e:
        logger.error(f"结束对话失败: {e}")
        return EndChatResponse(
            success=False,
            message=f"结束对话失败: {str(e)}",
            session_id=req.session_id,
        )


def _sse_event(event: str, data: str | dict) -> str:
    """
    格式化SSE事件字符串。

    参数：
        event: SSE事件名称（start/delta/done/error）
        data: 事件数据，字符串或字典（字典自动转JSON）

    返回：
        str: 格式化后的SSE事件字符串
    """
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False)
    lines = data.split("\n")
    return f"event: {event}\n" + "".join(f"data: {line}\n" for line in lines) + "\n"
