"""
API 路由总入口

文件目的：
    - 集中管理所有API路由
    - 将各个子模块的路由统一挂载到主路由上
    - 为所有API添加统一的前缀 /api/v1

路由结构：
    /api/v1/
    ├── /health          -> 健康检查接口
    ├── /metadata        -> 元数据查询接口
    ├── /rag             -> RAG检索增强生成接口
    ├── /sql-agent       -> SQL代理接口
    └── /chat            -> 聊天接口

调用流程：
    main.py -> include_router(api_router) -> 本文件 -> 各个v1子模块

相关文件：
    - agent_backend/api/v1/health.py: 健康检查
    - agent_backend/api/v1/metadata.py: 元数据管理
    - agent_backend/api/v1/rag.py: RAG功能
    - agent_backend/api/v1/sql_agent.py: SQL代理
    - agent_backend/api/v1/chat.py: 聊天功能
"""
from __future__ import annotations

from fastapi import APIRouter

from agent_backend.api.v1.chat import router as chat_router
from agent_backend.api.v1.health import router as health_router
from agent_backend.api.v1.metadata import router as metadata_router
from agent_backend.api.v1.rag import router as rag_router
from agent_backend.api.v1.sql_agent import router as sql_agent_router
from agent_backend.api.v1.export import router as export_router

router = APIRouter()
router.include_router(health_router, prefix="/api/v1")
router.include_router(metadata_router, prefix="/api/v1")
router.include_router(rag_router, prefix="/api/v1")
router.include_router(sql_agent_router, prefix="/api/v1")
router.include_router(export_router, prefix="/api/v1")
router.include_router(chat_router, prefix="/api/v1")

