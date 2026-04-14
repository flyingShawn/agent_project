"""
统一异常处理模块

文件功能：
    定义应用级异常类AppError和全局异常处理器，实现统一的JSON错误响应格式。
    所有业务异常通过AppError抛出，由FastAPI全局处理器捕获并返回标准化错误响应。

在系统架构中的定位：
    位于核心基础层，是整个后端异常处理的统一出口。
    main.py中通过register_exception_handlers()注册到FastAPI应用。

主要使用场景：
    - SQL安全校验失败时抛出AppError（如非SELECT语句、敏感列查询）
    - 数据库连接/查询失败时抛出AppError
    - LLM调用失败时抛出AppError
    - 全局兜底捕获所有未处理异常，返回500错误

核心类与函数：
    - AppError: 应用级异常类，包含code/message/http_status/details字段
    - register_exception_handlers: 注册AppError处理器和兜底Exception处理器

专有技术说明：
    - AppError使用keyword-only参数（*前缀），强制调用时指定参数名
    - 错误响应自动注入request_id，与RequestIdMiddleware配合实现链路追踪
    - 兜底处理器捕获所有未处理Exception，避免敏感信息泄露（返回通用错误消息）

安全注意事项：
    - 兜底处理器不暴露内部异常详情，仅返回"服务内部错误"
    - AppError的details字段可携带调试信息，但不应包含敏感数据
    - request_id贯穿日志和错误响应，便于问题定位

关联文件：
    - agent_backend/main.py: 调用register_exception_handlers()注册处理器
    - agent_backend/core/request_id.py: 提供request_id
    - agent_backend/sql_agent/sql_safety.py: 抛出AppError
    - agent_backend/sql_agent/executor.py: 抛出AppError
    - agent_backend/llm/clients.py: 抛出AppError
"""
from __future__ import annotations

import logging
import traceback
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """
    应用级异常类，携带结构化错误信息。

    所有业务异常应通过此类抛出，由全局异常处理器统一捕获并返回JSON响应。

    参数：
        code: 错误代码，如"sql_not_select"、"db_not_configured"等
        message: 人类可读的错误描述
        http_status: HTTP状态码，默认500
        details: 附加调试信息字典，可选

    返回：
        AppError实例，可被FastAPI全局异常处理器捕获

    异常处理机制：
        - register_exception_handlers注册的app_error_handler自动捕获
        - 响应格式：{"error": code, "message": message, "request_id": id}
    """

    def __init__(
        self,
        *,
        code: str = "internal_error",
        message: str = "",
        http_status: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    """
    注册全局异常处理器到FastAPI应用。

    注册两个处理器：
        1. AppError处理器：捕获业务异常，返回结构化JSON响应
        2. Exception兜底处理器：捕获所有未处理异常，返回通用500错误

    参数：
        app: FastAPI应用实例

    安全注意事项：
        - AppError处理器记录完整错误信息到日志
        - 兜底处理器不暴露异常详情，仅返回"服务内部错误"
        - 所有错误响应自动注入request_id用于链路追踪
    """

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.error(
            f"\n[{request_id}] AppError: code={exc.code}, message={exc.message}, "
            f"http_status={exc.http_status}, details={exc.details}"
        )
        body: dict[str, Any] = {
            "error": exc.code,
            "message": exc.message,
            "request_id": request_id,
        }
        if exc.details:
            body["details"] = exc.details
        return JSONResponse(status_code=exc.http_status, content=body)

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.error(
            f"\n[{request_id}] Unhandled exception: {type(exc).__name__}: {exc}\n"
            f"{traceback.format_exc()}"
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "服务内部错误，请稍后重试",
                "request_id": request_id,
            },
        )
