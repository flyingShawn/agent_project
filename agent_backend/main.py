"""
FastAPI 应用入口文件

文件目的：
    - 作为整个后端服务的启动点
    - 创建和配置 FastAPI 应用实例
    - 初始化日志、中间件、异常处理和路由

调用流程：
    1. 启动命令: uvicorn agent_backend.main:app --reload
    2. 加载此文件，执行 create_app() 函数
    3. create_app() 依次执行：
       - configure_logging() -> 配置日志系统
       - FastAPI() -> 创建应用实例
       - add_middleware() -> 添加请求ID中间件
       - register_exception_handlers() -> 注册异常处理器
       - include_router() -> 挂载API路由
    4. 应用启动完成，开始监听HTTP请求

相关文件：
    - agent_backend/api/routes.py: API路由配置
    - agent_backend/core/logging.py: 日志配置
    - agent_backend/core/errors.py: 异常处理
    - agent_backend/core/request_id.py: 请求ID中间件
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_backend.api.routes import router as api_router
from agent_backend.core.errors import register_exception_handlers
from agent_backend.core.logging import configure_logging
from agent_backend.core.request_id import RequestIdMiddleware


def create_app() -> FastAPI:
    """
    创建并配置 FastAPI 应用实例。

    该方法是后端服务的统一入口（应用工厂）。它会完成：
    - 初始化日志（统一格式 + request_id 注入）  
    - 注册中间件（RequestIdMiddleware）
    - 注册统一异常处理（AppError 与兜底异常）
    - 挂载 API 路由

    返回：
        FastAPI: 可直接交给 Uvicorn 启动的应用对象。
    """
    configure_logging()

    app = FastAPI(title="desk-agent-backend")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()

