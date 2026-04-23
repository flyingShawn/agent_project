"""
日志配置模块

文件功能：
    配置统一的日志格式和彩色输出，注入request_id到每条日志，
    实现SQL日志紫色高亮、错误日志红色高亮的可视化效果。

在系统架构中的定位：
    位于核心基础层，在应用启动时由create_app()首先调用。
    所有模块的日志输出均经过此模块配置的格式化器和过滤器。

主要使用场景：
    - 应用启动时调用configure_logging()初始化日志系统
    - 日志输出自动携带request_id用于链路追踪
    - SQL相关日志紫色显示，错误日志红色显示

核心类与函数：
    - ColorFormatter: 彩色日志格式化器，按日志级别着色
    - RequestIdFilter: 请求ID过滤器，从ContextVar注入request_id到日志记录
    - configure_logging: 日志系统初始化函数，配置格式化器、过滤器和处理器

专有技术说明：
    - 使用ANSI转义码实现终端彩色输出
    - RequestIdFilter通过ContextVar获取当前请求ID，无需显式传参
    - 日志格式：时间 | 级别 | request_id | 模块名 | 消息
    - 噪音日志器（httpx/httpcore/urllib3等）自动降级为WARNING级别

关联文件：
    - agent_backend/main.py: 调用configure_logging()初始化日志
    - agent_backend/core/request_id.py: 提供request_id ContextVar
"""
from __future__ import annotations

from datetime import datetime
import logging
import sys


def _shorten_request_id(request_id: str) -> str:
    """返回用于日志展示的短 request_id，避免日志列过长。"""
    if not request_id or request_id == "-":
        return "-"
    if "-" in request_id:
        return request_id.split("-", 1)[0]
    return request_id[:8]


class ColorFormatter(logging.Formatter):
    """
    彩色日志格式化器，按日志级别和内容类型着色。

    着色规则：
        - DEBUG: 青色
        - INFO: 绿色
        - WARNING: 黄色
        - ERROR: 红色
        - CRITICAL: 紫色
        - SQL相关INFO日志: 紫色（便于区分数据库操作）
        - ERROR级别消息: 红色（突出错误内容）
    """

    _COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    _RESET = "\033[0m"

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        """显式使用进程本地时区格式化日志时间，避免被外部 UTC 配置影响。"""
        dt = datetime.fromtimestamp(record.created).astimezone()
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(timespec="seconds")

    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录，为级别名称和特殊内容添加颜色。

        参数：
            record: 日志记录对象

        返回：
            str: 着色后的格式化日志字符串
        """
        color = self._COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname}{self._RESET}"
        if "SQL" in record.getMessage() and record.levelno >= logging.INFO:
            record.msg = f"\033[35m{record.msg}\033[0m"
        elif record.levelno >= logging.ERROR:
            record.msg = f"\033[31m{record.msg}\033[0m"
        return super().format(record)


class RequestIdFilter(logging.Filter):
    """
    请求ID日志过滤器，从ContextVar注入request_id到日志记录。

    每条日志记录自动添加request_id属性，无需在业务代码中显式传递。
    与RequestIdMiddleware配合，request_id贯穿整个请求生命周期。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        为日志记录注入request_id属性。

        参数：
            record: 日志记录对象

        返回：
            bool: 始终返回True（不过滤任何记录）
        """
        from agent_backend.core.request_id import _request_id_ctx
        record.request_id = _request_id_ctx.get("-")
        record.request_id_short = _shorten_request_id(record.request_id)
        return True


def configure_logging() -> None:
    """
    初始化日志系统，配置格式化器、过滤器和处理器。

    配置内容：
        1. 根日志器级别设为INFO
        2. 输出到stdout，格式：时间 | 级别 | request_id | 模块名 | 消息
        3. 使用ColorFormatter实现彩色输出
        4. 使用RequestIdFilter注入request_id
        5. 噪音日志器降级为WARNING

    幂等设计：
        - 若根日志器已有处理器则跳过配置，避免重复添加
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if root_logger.handlers:
        return

    handler = logging.StreamHandler(
        open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace', closefd=False)
    )
    handler.setLevel(logging.INFO)
    fmt = "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(request_id_short)s | %(name)s | %(message)s"
    formatter = ColorFormatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())
    root_logger.addHandler(handler)

    noisy_loggers = [
        "httpx",
        "httpcore",
        "urllib3",
        "asyncio",
        "multipart",
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)
