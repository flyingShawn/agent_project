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

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel, Field

from agent_backend.agent.graph import get_agent_graph
from agent_backend.agent.stream import stream_graph_response
from agent_backend.core.sse import sse_event
from agent_backend.db.chat_history import async_session
from agent_backend.db.models import Conversation, Message
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
    conversation_id: str | None = None


class EndChatRequest(BaseModel):
    """结束对话请求模型"""
    session_id: str = Field(..., min_length=1)


class EndChatResponse(BaseModel):
    """结束对话响应模型"""
    success: bool
    message: str
    session_id: str


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    t_start = time.time()
    conn_manager = get_connection_manager()
    session_id = req.session_id or conn_manager.generate_session_id()
    conversation_id = req.conversation_id

    logger.info(
        f"{'=' * 20}【聊天API入口】收到请求{'=' * 20}\n"
        f"  会话ID: {session_id[:8]}... | 会话记录ID: {conversation_id[:8] if conversation_id else 'None'} | "
        f"问题: {req.question} | 用户: {req.lognum} | "
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
        "scheduler_results": [],
    }

    if conversation_id:
        db_history = await _load_conversation_messages(conversation_id)
        for msg in db_history:
            if msg["role"] == "user":
                initial_state["messages"].append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                initial_state["messages"].append(AIMessage(content=msg["content"]))
    else:
        for msg in req.history:
            if msg.get("role") == "user":
                initial_state["messages"].append(HumanMessage(content=msg["content"]))
            elif msg.get("role") == "assistant":
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

    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        now = time.time()
        async with async_session() as db:
            conv = Conversation(
                id=conversation_id,
                title=_generate_title(req.question),
                user_id=req.lognum,
                created_at=now,
                updated_at=now,
                is_deleted=0,
            )
            db.add(conv)
            await db.commit()
        logger.info(f"\n[Chat] 自动创建会话记录: {conversation_id[:8]}... 标题: {_generate_title(req.question)}")

    await _save_message(conversation_id, "user", req.question)

    async def generate():
        logger.info(f"\n[SSE] start generate, session: {session_id[:8]}..., conv: {conversation_id[:8]}...")
        yield sse_event("start", {"intent": "agent", "session_id": session_id, "conversation_id": conversation_id})

        assistant_content = ""
        content_before_replace = ""
        charts_list = []
        message_saved = False

        try:
            graph = get_agent_graph()
            async for sse_chunk in stream_graph_response(graph, initial_state):
                event_type, event_data = _parse_sse_event(sse_chunk)
                if event_type == "delta":
                    assistant_content += str(event_data) if not isinstance(event_data, str) else event_data
                elif event_type == "replace":
                    if assistant_content:
                        content_before_replace = assistant_content
                    assistant_content = ""
                elif event_type == "chart" and isinstance(event_data, dict):
                    charts_list.append(event_data)
                yield sse_chunk

            if assistant_content:
                charts_json = json.dumps(charts_list, ensure_ascii=False) if charts_list else None
                await _save_message(conversation_id, "assistant", assistant_content, charts=charts_json)
                message_saved = True
                logger.info(f"\n[Chat] saved assistant msg before done: {len(assistant_content)}chars")

            yield sse_event(
                "done",
                {
                    "route": "agent",
                    "session_id": session_id,
                    "conversation_id": conversation_id,
                    "meta": {},
                },
            )
            logger.info(f"\n[Chat] request done, session: {session_id[:8]}..., elapsed: {time.time() - t_start:.2f}s")

        except asyncio.CancelledError:
            logger.warning(f"\n[Chat] SSE cancelled (client disconnect), conv: {conversation_id[:8]}...")
            if not message_saved:
                save_content = assistant_content or content_before_replace
                if save_content:
                    try:
                        await asyncio.shield(_save_message(conversation_id, "assistant", save_content))
                        message_saved = True
                        logger.info(f"\n[Chat] cancelled-saved assistant msg: {len(save_content)}chars")
                    except Exception as e:
                        logger.error(f"\n[Chat] cancelled-save failed: {e}")
                        _background_save(conversation_id, save_content)
                        message_saved = True
            try:
                await asyncio.shield(_update_conversation_timestamp(conversation_id))
            except Exception:
                _background_update_timestamp(conversation_id)
            raise

        except Exception as e:
            logger.error(f"\n[Chat] error: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            yield sse_event("error", {"error": "非常抱歉，查询失败，请稍后再试"})

        finally:
            if not message_saved:
                save_content = assistant_content or content_before_replace
                if save_content:
                    try:
                        await asyncio.shield(_save_message(conversation_id, "assistant", save_content))
                        logger.info(f"\n[Chat] finally saved assistant msg: {len(save_content)}chars")
                    except asyncio.CancelledError:
                        _background_save(conversation_id, save_content)
                        logger.info(f"\n[Chat] finally save delegated to background (cancelled)")
                    except Exception as e:
                        logger.error(f"\n[Chat] finally save failed: {e}")
                        _background_save(conversation_id, save_content)
            try:
                await asyncio.shield(_update_conversation_timestamp(conversation_id))
            except asyncio.CancelledError:
                _background_update_timestamp(conversation_id)
            except Exception:
                pass

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


def _generate_title(question: str) -> str:
    cleaned = re.sub(r"^(资讯[：:]|查询[：:]|搜索[：:]|问[：:])", "", question).strip()
    if len(cleaned) > 30:
        return cleaned[:30] + "..."
    return cleaned or "新对话"


def _parse_sse_event(sse_str: str) -> tuple[str, Any]:
    event_type = ""
    data_parts = []
    for line in sse_str.strip().split("\n"):
        if line.startswith("event: "):
            event_type = line[7:].strip()
        elif line.startswith("data: "):
            data_parts.append(line[6:])
    data_str = "\n".join(data_parts)
    if data_str:
        try:
            return event_type, json.loads(data_str)
        except (json.JSONDecodeError, TypeError):
            return event_type, data_str
    return event_type, None


def _background_save(conversation_id: str, content: str):
    async def _do_save():
        try:
            await _save_message(conversation_id, "assistant", content)
            logger.info(f"\n[Chat] background saved assistant msg: {len(content)}chars")
        except Exception as e:
            logger.error(f"\n[Chat] background save failed: {e}")
    asyncio.create_task(_do_save())


def _background_update_timestamp(conversation_id: str):
    async def _do_update():
        try:
            await _update_conversation_timestamp(conversation_id)
        except Exception as e:
            logger.error(f"\n[Chat] background update timestamp failed: {e}")
    asyncio.create_task(_do_update())


async def _save_message(conversation_id: str, role: str, content: str, intent: str | None = None, charts: str | None = None):
    try:
        async with async_session() as db:
            if role == "assistant":
                from sqlalchemy import select, func
                dup_stmt = select(func.count()).select_from(Message).where(
                    Message.conversation_id == conversation_id,
                    Message.role == "assistant",
                    Message.content == content,
                )
                dup_count = (await db.execute(dup_stmt)).scalar() or 0
                if dup_count > 0:
                    logger.info(f"\n[Chat] skip duplicate assistant msg: conv={conversation_id[:8]}..., {len(content)}chars")
                    return
            msg = Message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                intent=intent,
                charts=charts,
                created_at=time.time(),
            )
            db.add(msg)
            await db.commit()
    except Exception as e:
        logger.error(f"\n保存消息失败: {e}")


async def _update_conversation_timestamp(conversation_id: str):
    try:
        async with async_session() as db:
            from sqlalchemy import select, update
            stmt = select(Conversation).where(Conversation.id == conversation_id)
            result = await db.execute(stmt)
            conv = result.scalar_one_or_none()
            if conv:
                conv.updated_at = time.time()
                await db.commit()
    except Exception as e:
        logger.error(f"\n更新会话时间戳失败: {e}")


async def _load_conversation_messages(conversation_id: str) -> list[dict[str, str]]:
    try:
        async with async_session() as db:
            from sqlalchemy import select
            stmt = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
            result = await db.execute(stmt)
            messages = result.scalars().all()
            return [{"role": m.role, "content": m.content} for m in messages]
    except Exception as e:
        logger.error(f"\n加载历史消息失败: {e}")
        return []
