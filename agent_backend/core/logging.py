"""
统一日志配置模块

文件功能：
    配置应用全局日志格式、输出目标与彩色高亮规则，并注入 request_id 实现请求级链路追踪。

核心作用与设计目的：
    - 提供统一的日志格式（时间戳 + request_id + 级别 + 模块名 + 消息）
    - 通过 RequestIdFilter 将当前请求的 request_id 自动注入每条日志记录
    - 通过 ColoredFormatter 对 SQL 执行日志和错误日志进行彩色高亮，提升开发调试效率
    - 清除 root logger 已有 handler 后重新配置，避免重复输出

主要使用场景：
    - 应用启动时调用 configure_logging() 初始化日志系统
    - 所有模块通过 logging.getLogger(__name__) 获取的 logger 均自动继承此配置

包含的主要类与函数：
    - ColoredFormatter: 彩色日志格式化器，高亮 SQL 日志（紫色）和错误日志（红色）
    - RequestIdFilter: 日志过滤器，将 request_id 注入日志记录的额外字段
    - configure_logging(): 全局日志配置入口，设置格式、handler 和级别

相关联的调用文件：
    - agent_backend/main.py: 在 create_app() 中调用 configure_logging()
    - agent_backend/core/request_id.py: 提供 get_request_id() 用于日志注入
"""
from __future__ import annotations

import logging
import sys

from agent_backend.core.request_id import get_request_id

class ColoredFormatter(logging.Formatter):
    """
    彩色日志格式化器，基于日志内容与级别应用 ANSI 颜色高亮。

    高亮规则：
        - 包含「【执行的SQL】」的日志 → 紫色（MAGENTA），便于快速定位 SQL 执行
        - ERROR/CRITICAL 级别或包含 ❌ 的日志 → 红色（RED），突出错误信息
        - 其他日志 → 不染色，保持默认终端颜色

    说明：
        - ANSI 颜色码在 Windows 终端可能不被支持，建议在支持 ANSI 的终端中使用
    """
    
    COLORS = {
        'RESET': '\033[0m',
        'MAGENTA': '\033[35m',
        'RED': '\033[31m',
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录并应用颜色高亮。

        参数：
            record: Python 标准库的日志记录对象。

        返回：
            str: 经过格式化和颜色处理后的日志字符串。
        """
        message = super().format(record)
        reset = self.COLORS['RESET']
        
        # 在真正的日志内容前添加换行符，确保日志内容显示在新的一行
        # 检查消息中是否包含实际的日志内容（通常以中文括号或其他标记开始）
        # 查找第一个中文括号或其他常见的日志标记
        # markers = ['【', '✅', '❌', '🔄', '-', '🔻']
        # markers = ['【']
        # for marker in markers:
        #     idx = message.find(marker)
        #     if idx > 0:
        #         # 在标记前添加换行符
        #         message = message[:idx] + '\n' + message[idx:]
        #         break
        
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

