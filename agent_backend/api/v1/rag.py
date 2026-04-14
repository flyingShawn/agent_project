"""
RAG文档同步API接口模块

文件功能：
    提供RAG文档知识库和SQL样本库的同步触发端点。
    当前为占位实现，建议使用CLI命令执行同步操作。

在系统架构中的定位：
    位于API层，是RAG引擎同步功能的HTTP入口。
    完整同步功能需通过CLI命令执行（依赖Docling解析等重量级操作）。

主要使用场景：
    - 前端触发文档知识库同步（当前返回提示使用CLI）
    - 前端触发SQL样本库同步（当前返回提示使用CLI）
    - 查询同步任务状态（当前返回not_implemented）

核心端点：
    - POST /api/v1/rag/sync: 触发文档知识库同步
    - POST /api/v1/rag/sync-sql: 触发SQL样本库同步
    - GET /api/v1/rag/sync/{job_id}: 查询同步任务状态

关联文件：
    - agent_backend/rag_engine/cli.py: CLI同步命令的实际实现
    - agent_backend/api/routes.py: 路由注册
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rag"])


class SyncRequest(BaseModel):
    """同步请求模型（当前无参数）"""
    pass


class SyncResponse(BaseModel):
    """同步响应模型"""
    job_id: str
    status: str
    message: str


@router.post("/rag/sync", response_model=SyncResponse)
def sync_docs(req: SyncRequest) -> SyncResponse:
    """
    触发文档知识库同步。

    当前为占位实现，建议使用CLI命令执行：
    python -m agent_backend.rag_engine.cli sync

    参数：
        req: SyncRequest（当前无参数）

    返回：
        SyncResponse: 包含job_id/status/message的响应
    """
    logger.info("RAG文档同步请求")
    return SyncResponse(
        job_id="manual",
        status="not_implemented",
        message="请使用CLI命令执行文档同步: python -m agent_backend.rag_engine.cli sync",
    )


@router.post("/rag/sync-sql", response_model=SyncResponse)
def sync_sql_samples(req: SyncRequest) -> SyncResponse:
    """
    触发SQL样本库同步。

    当前为占位实现，建议使用CLI命令执行：
    python -m agent_backend.rag_engine.cli sync-sql

    参数：
        req: SyncRequest（当前无参数）

    返回：
        SyncResponse: 包含job_id/status/message的响应
    """
    logger.info("SQL样本同步请求")
    return SyncResponse(
        job_id="manual",
        status="not_implemented",
        message="请使用CLI命令执行SQL样本同步: python -m agent_backend.rag_engine.cli sync-sql",
    )


@router.get("/rag/sync/{job_id}")
def get_sync_status(job_id: str) -> dict:
    """
    查询同步任务状态。

    参数：
        job_id: 同步任务ID

    返回：
        dict: 包含job_id和status的状态信息
    """
    return {"job_id": job_id, "status": "not_implemented"}
