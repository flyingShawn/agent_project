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

