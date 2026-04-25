"""
FastAPI 应用入口文件

文件功能：
    作为整个后端服务的启动点，采用应用工厂模式创建和配置 FastAPI 应用实例，
    完成日志初始化、中间件注册、异常处理和路由挂载。

核心作用与设计目的：
    - 应用工厂模式（create_app）便于测试和多种部署配置
    - 统一初始化日志、CORS、请求ID、异常处理等横切关注点
    - 应用关闭时自动清理数据库连接池资源
    - 启动时预加载LLM、Schema、Embedding、Qdrant等组件，消除首次请求冷启动

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
    4. 应用启动完成，开始监听 HTTP 请求

包含的主要函数：
    - create_app(): 应用工厂，创建并配置 FastAPI 实例
    - _preload_components(): 启动时预加载组件

相关联的调用文件：
    - agent_backend/api/routes.py: API 路由配置
    - agent_backend/core/logging.py: 日志配置
    - agent_backend/core/errors.py: 异常处理
    - agent_backend/core/request_id.py: 请求 ID 中间件
    - agent_backend/sql_agent/connection_manager.py: 数据库连接管理（关闭时清理）
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_backend.api.routes import router as api_router
from agent_backend.core.config import load_env_file, get_settings
from agent_backend.core.errors import register_exception_handlers
from agent_backend.core.logging import configure_logging
from agent_backend.core.request_id import RequestIdMiddleware
from agent_backend.db.chat_history import init_db
from agent_backend.ops_reports import get_ops_report_manager
from agent_backend.sql_agent.connection_manager import get_connection_manager

load_env_file()

logger = logging.getLogger(__name__)


def _preload_components() -> None:
    log = logging.getLogger(__name__)
    log.info("\n[Preload] 开始预加载组件...")

    try:
        get_settings()
        log.info("\n[Preload] ✅ Settings 已加载")
    except Exception as e:
        log.warning(f"\n[Preload] ⚠️ Settings 加载失败: {e}")

    try:
        from agent_backend.core.config import get_schema_runtime
        get_schema_runtime()
        log.info("\n[Preload] ✅ Schema 元数据已加载")
    except Exception as e:
        log.warning(f"\n[Preload] ⚠️ Schema 元数据加载失败: {e}")

    try:
        from agent_backend.agent.graph import get_agent_graph
        get_agent_graph()
        log.info("\n[Preload] ✅ Agent Graph 已构建")
    except Exception as e:
        log.warning(f"\n[Preload] ⚠️ Agent Graph 构建失败: {e}")

    try:
        from agent_backend.rag_engine.retrieval import get_or_create_embedding, get_or_create_store, get_sql_rag_settings
        qdrant_url, qdrant_path, qdrant_api_key, collection, embedding_model_name, top_k, candidate_k, alpha = get_sql_rag_settings()
        embedding_model = get_or_create_embedding(embedding_model_name)
        dim = embedding_model.dimension
        get_or_create_store(
            url=qdrant_url, path=qdrant_path, api_key=qdrant_api_key,
            collection=collection, dim=dim,
        )
        log.info("\n[Preload] ✅ Embedding 模型 + Qdrant 连接已就绪")
    except Exception as e:
        log.warning(f"\n[Preload] ⚠️ Embedding/Qdrant 预加载失败: {e}")

    try:
        from agent_backend.llm.factory import get_llm, get_sql_llm
        get_llm()
        get_sql_llm()
        log.info("\n[Preload] ✅ LLM 实例已缓存")
    except Exception as e:
        log.warning(f"\n[Preload] ⚠️ LLM 实例预加载失败: {e}")

    log.info("\n[Preload] 预加载完成")


def create_app() -> FastAPI:
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db()
        _preload_components()
        ops_report_manager = get_ops_report_manager()
        await ops_report_manager.start()
        logger.info("\n[Startup] 应用启动完成，运维简报调度器已启动")
        yield
        logger.info("\n[Shutdown] 应用正在关闭，清理资源...")
        await ops_report_manager.shutdown()
        conn_manager = get_connection_manager()
        conn_manager.shutdown()
        from agent_backend.llm.factory import reset_llm_cache
        reset_llm_cache()
        logger.info("\n[Shutdown] 应用关闭完成")

    app = FastAPI(title="desk-agent-backend", lifespan=lifespan)

    cors_origins = [o.strip() for o in get_settings().misc.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)
    
    return app


app = create_app()
