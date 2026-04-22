from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import httpx

from agent_backend.core.config import get_settings
from agent_backend.integrations.chat_history_push.schemas import ChatHistoryPushPayload

logger = logging.getLogger(__name__)

_CHAT_HISTORY_PATH_SUFFIX = "/ai/nl2sql/chat-history"


def dispatch_chat_history_report(
    user_message: str,
    ai_response: str,
    user_name: str,
    session_id: str,
) -> None:
    """在回答收尾时异步上报第三方会话记录，不阻塞主聊天流程。"""
    report_config = _build_report_config(
        user_message=user_message,
        ai_response=ai_response,
        user_name=user_name,
        session_id=session_id,
    )
    if report_config is None:
        return

    report_url, timeout_seconds, payload = report_config
    asyncio.create_task(
        _post_chat_history_report(
            report_url=report_url,
            timeout_seconds=timeout_seconds,
            payload=payload,
        )
    )


def _build_report_config(
    user_message: str,
    ai_response: str,
    user_name: str,
    session_id: str,
) -> tuple[str, float, ChatHistoryPushPayload] | None:
    settings = get_settings().misc
    base_url = settings.third_party_chat_history_base_url.strip()
    if not base_url or not ai_response.strip():
        return None

    report_url = f"{base_url.rstrip('/')}{_CHAT_HISTORY_PATH_SUFFIX}"
    payload = ChatHistoryPushPayload(
        userMessage=user_message,
        aiResponse=ai_response,
        userName=user_name,
        sessionId=session_id,
        createdTime=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    )
    return report_url, settings.third_party_chat_history_timeout_seconds, payload


async def _post_chat_history_report(
    report_url: str,
    timeout_seconds: float,
    payload: ChatHistoryPushPayload,
) -> None:
    timeout = httpx.Timeout(timeout_seconds)
    try:
        async with httpx.AsyncClient(proxy=None, timeout=timeout) as client:
            response = await client.post(report_url, json=payload.model_dump())
            response.raise_for_status()
        logger.info(
            "[chat_history_push] report success, session_id=%s, url=%s, status_code=%s",
            payload.sessionId,
            report_url,
            response.status_code,
        )
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "[chat_history_push] report failed, session_id=%s, url=%s, status_code=%s",
            payload.sessionId,
            report_url,
            exc.response.status_code,
        )
    except httpx.RequestError as exc:
        logger.warning(
            "[chat_history_push] report request error, session_id=%s, url=%s, error=%s",
            payload.sessionId,
            report_url,
            exc,
        )
    except Exception as exc:
        logger.warning(
            "[chat_history_push] report unexpected error, session_id=%s, url=%s, error=%s",
            payload.sessionId,
            report_url,
            exc,
        )
