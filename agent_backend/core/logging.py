from __future__ import annotations

import logging
import sys

from agent_backend.core.request_id import get_request_id

class ColoredFormatter(logging.Formatter):
    """
    彩色日志格式化器
    """
    
    COLORS = {
        'RESET': '\033[0m',
        'MAGENTA': '\033[35m',
        'RED': '\033[31m',
    }
    
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        reset = self.COLORS['RESET']
        
        # 在真正的日志内容前添加换行符，确保日志内容显示在新的一行
        # 检查消息中是否包含实际的日志内容（通常以中文括号或其他标记开始）
        # 查找第一个中文括号或其他常见的日志标记
        markers = ['【', '✅', '❌', '🔄', '-', '🔻']
        for marker in markers:
            idx = message.find(marker)
            if idx > 0:
                # 在标记前添加换行符
                message = message[:idx] + '\n' + message[idx:]
                break
        
        # 只高亮最终的SQL语句
        if '【执行的SQL】' in message:
            return f"{self.COLORS['MAGENTA']}{message}{reset}"
        
        # 错误日志高亮
        if record.levelname in ('ERROR', 'CRITICAL') or '❌' in message:
            return f"{self.COLORS['RED']}{message}{reset}"
        
        # 其他日志不染色
        return message


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        """
        将 request_id 注入到日志记录中，供 formatter 使用。

        说明：
            - 当没有请求上下文时，request_id 可能为 None
            - 该方法为 logging.Filter 的框架回调专用入口
        """
        record.request_id = get_request_id()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """
    配置应用的统一日志格式与 handler。

    行为：
        - 若 root logger 已存在 handler，则不重复配置（避免重复输出）
        - 输出到 stdout，便于容器/进程托管采集
        - 注入 request_id 字段：request_id=<id>
        - 使用彩色输出，特殊高亮SQL相关日志

    参数：
        level: 日志级别，默认 INFO。
    """
    root = logging.getLogger()
    
    # 清除已有的 handlers，确保我们的配置生效
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    formatter = ColoredFormatter(
        fmt="%(asctime)s request_id=%(request_id)s %(levelname)s %(name)s %(message)s"
    )
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())

    root.setLevel(level)
    root.addHandler(handler)

    # 设置其他日志器的级别
    for noisy_logger in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
    
    # 确保我们的应用日志器使用正确的级别
    logging.getLogger("agent_backend").setLevel(level)

