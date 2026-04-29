"""
API 路由总入口

文件目的：
    - 集中管理所有API路由
    - 将各个子模块的路由统一挂载到主路由上
    - 为所有API添加统一的前缀 /api/v1

路由结构：
    /api/v1/
    ├── /agents                       -> 获取已启用智能体列表（全局）
    ├── /health                       -> 健康检查接口（全局）
    ├── /metadata                     -> 元数据查询接口（全局）
    ├── /{agent_type}/chat            -> 聊天接口
    ├── /{agent_type}/conversations   -> 对话管理接口
    ├── /{agent_type}/ops             -> 运维简报接口
    ├── /{agent_type}/rag             -> RAG检索增强生成接口
    ├── /sql-agent                    -> SQL代理接口（全局）
    └── /export                       -> 导出接口（全局）

调用流程：
    main.py -> include_router(api_router) -> 本文件 -> 各个v1子模块

相关文件：
    - agent_backend/api/v1/health.py: 健康检查
    - agent_backend/api/v1/metadata.py: 元数据管理
    - agent_backend/api/v1/rag.py: RAG功能
    - agent_backend/api/v1/sql_agent.py: SQL代理
    - agent_backend/api/v1/chat.py: 聊天功能
    - agent_backend/api/v1/agents.py: 智能体列表
"""
from __future__ import annotations

from fastapi import APIRouter

from agent_backend.api.v1.agents import router as agents_router
from agent_backend.api.v1.chat import router as chat_router
from agent_backend.api.v1.conversations import router as conversations_router
from agent_backend.api.v1.health import router as health_router
from agent_backend.api.v1.metadata import router as metadata_router
from agent_backend.api.v1.ops import router as ops_router
from agent_backend.api.v1.rag import router as rag_router
from agent_backend.api.v1.sql_agent import router as sql_agent_router
from agent_backend.api.v1.export import router as export_router

router = APIRouter()
router.include_router(agents_router, prefix="/api/v1")
router.include_router(health_router, prefix="/api/v1")
router.include_router(metadata_router, prefix="/api/v1")
router.include_router(sql_agent_router, prefix="/api/v1")
router.include_router(export_router, prefix="/api/v1")
router.include_router(chat_router, prefix="/api/v1")
router.include_router(conversations_router, prefix="/api/v1")
router.include_router(ops_router, prefix="/api/v1")
router.include_router(rag_router, prefix="/api/v1")
