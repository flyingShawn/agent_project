"""
请求ID中间件模块

文件功能：
    通过ContextVar实现请求级别的唯一ID追踪，贯穿日志和错误响应。
    每个HTTP请求自动分配或读取X-Request-ID，确保全链路可追踪。

在系统架构中的定位：
    位于核心基础层，作为Starlette中间件注册到FastAPI应用。
    与RequestIdFilter（日志）和register_exception_handlers（错误响应）配合，
    实现request_id从请求入口到日志输出和错误响应的完整链路追踪。

主要使用场景：
    - 每个HTTP请求自动注入request_id到日志
    - 错误响应中返回request_id，便于用户反馈问题时定位
    - 分布式环境下通过X-Request-ID头传递追踪ID

核心组件：
    - _request_id_ctx: ContextVar，存储当前请求的request_id
    - RequestIdMiddleware: Starlette中间件，自动设置request_id

专有技术说明：
    - 使用ContextVar实现协程安全的请求级变量，无需显式传参
    - 支持上游传入X-Request-ID头（如Nginx/网关），未传入时自动生成UUID
    - request_id同时写入request.state和响应头，双向可追踪

关联文件：
    - agent_backend/main.py: 注册RequestIdMiddleware到FastAPI应用
    - agent_backend/core/logging.py: RequestIdFilter从_request_id_ctx读取
    - agent_backend/core/errors.py: 异常处理器从request.state读取
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    请求ID中间件，为每个HTTP请求分配唯一ID并注入到ContextVar。

    处理流程：
        1. 读取请求头X-Request-ID，不存在则生成UUID
        2. 将request_id设置到ContextVar（供日志过滤器读取）
        3. 将request_id写入request.state（供异常处理器读取）
        4. 将request_id写入响应头X-Request-ID（供客户端追踪）

    参数：
        request: HTTP请求对象
        call_next: 下一个中间件/路由处理函数

    返回：
        Response: 包含X-Request-ID响应头的HTTP响应
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        _request_id_ctx.set(request_id)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
