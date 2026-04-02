"""
请求ID中间件

文件目的：
    - 为每个HTTP请求分配唯一ID
    - 支持请求链路追踪
    - 将request_id注入日志和响应头

核心功能：
    1. 从请求头获取或生成request_id
    2. 使用contextvars存储request_id（线程安全）
    3. 在响应头中返回request_id
    4. 提供get_request_id()函数供其他模块使用

主要组件：
    - request_id_var: ContextVar存储request_id
    - RequestIdMiddleware: Starlette中间件
    - get_request_id(): 获取当前请求ID

调用流程：
    HTTP请求 -> RequestIdMiddleware.dispatch()
    -> 设置request_id到contextvar
    -> 执行后续处理
    -> 日志/错误处理中使用get_request_id()获取ID
    -> 响应头添加x-request-id

使用场景：
    - 日志追踪：每条日志自动带上request_id
    - 错误排查：通过request_id关联请求链路
    - 分布式追踪：透传上游服务的request_id

相关文件：
    - agent_backend/core/logging.py: 日志配置（使用request_id）
    - agent_backend/core/errors.py: 错误处理（使用request_id）
"""
from __future__ import annotations

import contextvars
import uuid
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def get_request_id() -> str | None:
    """
    获取当前请求上下文的 request_id。

    说明：
        - request_id 由 RequestIdMiddleware 在每个 HTTP 请求开始时写入 contextvar。
        - 当代码运行在无请求上下文（例如 CLI/单元测试的纯函数调用）时，可能返回 None。

    返回：
        str | None: 当前请求的 request_id（十六进制字符串），或 None。
    """
    return request_id_var.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        为每个请求分配/透传 request_id，并写入响应头。

        规则：
            - 若请求头包含 x-request-id，则优先使用（便于链路追踪透传）
            - 否则生成新的 UUID（hex）
            - 响应头始终返回 x-request-id

        该方法为框架回调的专用入口（Starlette 中间件约定），业务代码不应直接调用。
        """
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = rid
        return response

