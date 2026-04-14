"""
FastAPI 应用入口文件

文件功能：
    作为整个后端服务的启动点，采用应用工厂模式创建和配置 FastAPI 应用实例，
    完成日志初始化、中间件注册、异常处理和路由挂载。

核心作用与设计目的：
    - 应用工厂模式（create_app）便于测试和多种部署配置
    - 统一初始化日志、CORS、请求ID、异常处理等横切关注点
    - 应用关闭时自动清理数据库连接池资源

启动流程：
    1. 启动命令: uvicorn agent_backend.main:app --reload
    2. 加载此文件，执行 create_app() 函数
    3. create_app() 依次执行：
       - configure_logging() → 配置日志系统
       - FastAPI() → 创建应用实例
       - add_middleware(CORSMiddleware) → 添加跨域中间件
       - add_middleware(RequestIdMiddleware) → 添加请求ID中间件
       - register_exception_handlers() → 注册异常处理器
       - include_router() → 挂载 API 路由
       - on_event("shutdown") → 注册关闭事件处理
    4. 应用启动完成，开始监听 HTTP 请求

包含的主要函数：
    - create_app(): 应用工厂，创建并配置 FastAPI 实例

相关联的调用文件：
    - agent_backend/api/routes.py: API 路由配置
    - agent_backend/core/logging.py: 日志配置
    - agent_backend/core/errors.py: 异常处理
    - agent_backend/core/request_id.py: 请求 ID 中间件
    - agent_backend/sql_agent/connection_manager.py: 数据库连接管理（关闭时清理）
"""
from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_backend.api.routes import router as api_router
from agent_backend.core.errors import register_exception_handlers
from agent_backend.core.logging import configure_logging
from agent_backend.core.request_id import RequestIdMiddleware
from agent_backend.sql_agent.connection_manager import get_connection_manager

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


def create_app() -> FastAPI:
    """
    创建并配置 FastAPI 应用实例（应用工厂模式）。

    初始化步骤：
        1. configure_logging() → 配置统一日志格式和 request_id 注入
        2. FastAPI() → 创建应用实例
        3. CORSMiddleware → 添加跨域中间件（允许所有来源）
        4. RequestIdMiddleware → 添加请求 ID 中间件（链路追踪）
        5. register_exception_handlers() → 注册 AppError 和兜底异常处理器
        6. include_router() → 挂载 /api/v1 下所有路由
        7. on_event("shutdown") → 注册关闭事件，清理数据库连接

    返回：
        FastAPI: 可直接交给 Uvicorn 启动的应用对象

    安全注意事项：
        - CORS 配置允许所有来源（allow_origins=["*"]），生产环境应限制为前端域名
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
    
    @app.on_event("shutdown")
    async def shutdown_event():
        logger = __import__('logging').getLogger(__name__)
        logger.info("\n🔻 应用正在关闭，清理数据库连接...")
        conn_manager = get_connection_manager()
        conn_manager.shutdown()
        logger.info("\n✅ 应用关闭完成")
    
    return app


app = create_app()

