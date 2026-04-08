"""
聊天 API 端点 (支持SSE流式响应)

文件目的：
    - 提供统一的聊天接口，自动路由到SQL或RAG模式
    - 支持Server-Sent Events (SSE)流式响应
    - 支持多轮对话和图片输入

API端点：
    POST /api/v1/chat
    请求体: {
        "question": "用户问题",
        "history": [{"role": "user/assistant", "content": "..."}],
        "images_base64": ["base64编码图片"],  # 可选
        "lognum": "用户工号",
        "mode": "auto|sql|rag",  # 路由模式
        "token": "认证token"     # 可选
    }
    
    返回: SSE流式事件
    event: start   data: {"intent": "sql|rag"}
    event: delta   data: "文本片段"
    event: done    data: {"route": "...", "meta": {}}
    event: error   data: {"error": "错误信息"}

调用流程：
    客户端 -> POST /chat 
    -> classify_intent() -> 意图识别
    -> handle_sql_chat() 或 handle_rag_chat() 
    -> 流式返回结果

相关文件：
    - agent_backend/chat/router.py: 意图识别路由
    - agent_backend/chat/handlers.py: 聊天处理器
    - agent_backend/chat/types.py: 类型定义
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_backend.chat.handlers import handle_rag_chat, handle_sql_chat
from agent_backend.chat.router import classify_intent
from agent_backend.chat.types import Intent
from agent_backend.sql_agent.connection_manager import get_connection_manager

logger = logging.getLogger(__name__)


router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)
    images_base64: list[str] | None = None
    lognum: str = Field(default="admin")
    mode: str = Field(default="auto")
    token: str | None = None
    session_id: str | None = None


class ChatMetadata(BaseModel):
    route: str
    intent: str


class EndChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1)


class EndChatResponse(BaseModel):
    success: bool
    message: str
    session_id: str


def _sse_event(event: str, data: str | dict) -> str:
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False)
    lines = data.split('\n')  # "连接符".join(列表) 用"连接符"把列表中的元素连接成一个字符串
    return f"event: {event}\n" + "".join(f"data: {line}\n" for line in lines) + "\n"

#StreamingResponse是 FastAPI 的响应类，用于 流式响应
@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    conn_manager = get_connection_manager()
    session_id = req.session_id or conn_manager.generate_session_id()
    
    logger.info(f"{'=' * 20 + '【聊天API入口】===== 收到请求 =====' + '=' * 20}\n  - 会话ID: {session_id[:8]}... | 用户问题: {req.question} | 用户ID: {req.lognum} | 路由模式: {req.mode} | 历史消息数: {len(req.history)} | 历史消息: {req.history} | 图片数量: {len(req.images_base64) if req.images_base64 else 0}\n{'=' * 80}")
    
    if req.mode == "auto":
        intent = classify_intent(req.question)
        logger.info(f"【意图识别】自动识别结果: {intent.value}")
    elif req.mode == "sql":
        intent = Intent.SQL
        logger.info(f"【意图识别】强制指定: SQL模式")
    elif req.mode == "rag":
        intent = Intent.RAG
        logger.info(f"【意图识别】强制指定: RAG模式")
    else:
        intent = classify_intent(req.question)
        logger.info(f"【意图识别】默认识别结果: {intent.value}")

    def generate() -> str:
        logger.info(f"【SSE流】开始生成，意图: {intent.value}" + " 发送start事件")
        yield _sse_event("start", {"intent": intent.value, "session_id": session_id})

        try:
            if intent == Intent.SQL:
                logger.info("【处理分支】===== 进入SQL处理流程 =====")
                chunk_count = 0
                for chunk in handle_sql_chat(
                    question=req.question,
                    lognum=req.lognum,
                    history=req.history,
                    images_base64=req.images_base64,
                    session_id=session_id,
                ):
                    chunk_count += 1
                    logger.debug(f"【SQL处理】生成第 {chunk_count} 个文本块，长度: {len(chunk)}")
                    yield _sse_event("delta", chunk)
                logger.info(f"【SQL处理】完成，共生成 {chunk_count} 个文本块")
            else:
                logger.info("【处理分支】===== 进入RAG处理流程 =====")
                chunk_count = 0
                for chunk in handle_rag_chat(
                    question=req.question,
                    history=req.history,
                    images_base64=req.images_base64,
                    session_id=session_id,
                ):
                    chunk_count += 1
                    logger.debug(f"【RAG处理】生成第 {chunk_count} 个文本块，长度: {len(chunk)}")
                    yield _sse_event("delta", chunk)
                logger.info(f"【RAG处理】完成，共生成 {chunk_count} 个文本块")

            logger.info("【SSE流】发送done事件")
            yield _sse_event(
                "done",
                {
                    "route": intent.value,
                    "session_id": session_id,
                    "meta": {},
                },
            )
            logger.info("=" * 80)
            logger.info("【聊天API】===== 请求处理完成 =====")

        except Exception as e:
            logger.error(f"【错误】处理过程中发生异常: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            yield _sse_event(
                "error",
                {
                    "error": f"{type(e).__name__}: {e}",
                },
            )

    logger.info("【聊天API】返回StreamingResponse")
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
    结束对话，关闭相关的数据库连接
    
    参数：
        session_id: 会话ID
    
    返回：
        操作结果
    """
    logger.info(f"{'=' * 20 + '【结束对话API】===== 收到请求 =====' + '=' * 20}\n  - 会话ID: {req.session_id[:8]}...\n{'=' * 80}")
    
    try:
        conn_manager = get_connection_manager()
        conn_manager.close_connection(req.session_id, reason="用户主动结束对话")
        
        logger.info("✅ 对话结束处理成功")
        return EndChatResponse(
            success=True,
            message="对话已结束，数据库连接已关闭",
            session_id=req.session_id
        )
    except Exception as e:
        logger.error(f"❌ 结束对话失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return EndChatResponse(
            success=False,
            message=f"结束对话失败: {str(e)}",
            session_id=req.session_id
        )
