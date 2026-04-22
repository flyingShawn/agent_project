"""第三方会话记录上报入口。"""

from .reporter import dispatch_chat_history_report

__all__ = ["dispatch_chat_history_report"]
