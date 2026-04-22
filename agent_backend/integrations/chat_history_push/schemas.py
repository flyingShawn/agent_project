from __future__ import annotations

from pydantic import BaseModel


class ChatHistoryPushPayload(BaseModel):
    """第三方会话记录上报负载。"""

    userMessage: str
    aiResponse: str
    userName: str
    sessionId: str
    createdTime: str
