"""
统一异常处理模块

文件功能：
    定义应用级异常体系与全局异常处理器，确保所有 HTTP 错误以统一 JSON 结构返回。

核心作用与设计目的：
    - 提供可预期的业务异常类 AppError，携带错误码、HTTP 状态码和结构化详情
    - 注册 FastAPI 全局异常处理器，将 AppError 与未捕获异常统一转为 JSON 响应
    - 所有错误响应自动附带 request_id，便于链路追踪与问题排查

主要使用场景：
    - 业务逻辑中抛出可预期异常（如参数校验失败、权限不足、资源不存在）
    - 全局兜底捕获未处理异常，避免向调用方泄露内部堆栈信息

包含的主要类与函数：
    - AppError: 应用级可预期异常类，支持错误码、消息、HTTP状态码和结构化详情
    - _error_payload(): 构造统一错误响应结构（内部方法）
    - register_exception_handlers(): 注册 FastAPI 全局异常处理器

安全注意事项：
    - 未捕获异常的 handler 仅返回 "Internal Server Error"，不泄露堆栈信息
    - AppError 的 details 字段可携带调试信息，生产环境需注意不要包含敏感数据

相关联的调用文件：
    - agent_backend/main.py: 在 create_app() 中调用 register_exception_handlers()
    - agent_backend/core/request_id.py: 错误响应中注入 request_id
    - agent_backend/sql_agent/sql_safety.py: 安全校验失败时抛出 AppError
    - agent_backend/rag_engine/docling_parser.py: 文档解析失败时抛出 AppError
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_backend.core.request_id import get_request_id

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        应用级可预期异常，用于统一对外错误返回。

        参数：
            code: 稳定的错误码（供前端/调用方做分支处理）。
            message: 面向调用方的简明错误信息。
            http_status: HTTP 状态码，默认 400。
            details: 结构化补充信息（避免塞入 message），默认空字典。

        说明：
            - 该异常会被 register_exception_handlers 注册的 handler 捕获并转为 JSON 响应。
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}


def _error_payload(*, code: str, message: str, details: dict[str, Any] | None) -> dict:
    """
    构造统一的错误响应结构。

    该方法为内部专用方法（下划线前缀），用于保证所有错误响应格式一致，
    并附带 request_id 便于排查。
    """
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": get_request_id(),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    """
    注册统一异常处理器。

    - AppError：按业务定义返回指定 http_status 与结构化 details
    - Exception：兜底 500，避免泄露内部堆栈到调用方

    说明：
        - 该方法应在应用启动时调用一次（通常在 create_app 中）。
        - handler 内会记录日志，便于问题定位。
    """
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "app_error code=%s status=%s path=%s", exc.code, exc.http_status, request.url.path
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=_error_payload(code=exc.code, message=exc.message, details=exc.details),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error path=%s", request.url.path)
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                code="internal_error",
                message="Internal Server Error",
                details=None,
            ),
        )

