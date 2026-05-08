"""
RAG文档同步API接口模块

文件功能：
    提供RAG文档知识库和SQL样本库的同步触发端点。
    同步操作在后台线程中执行，避免阻塞API响应。

核心端点：
    - POST /api/v1/rag/sync: 触发文档知识库同步
    - POST /api/v1/rag/sync-sql: 触发SQL样本库同步
    - GET /api/v1/rag/sync/{job_id}: 查询同步任务状态

关联文件：
    - agent_backend/rag_engine/ingest.py: 导入主流程
    - agent_backend/rag_engine/settings.py: 配置定义
    - agent_backend/rag_engine/state.py: 增量状态管理
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/{agent_type}/rag", tags=["rag"])

_jobs: dict[str, dict[str, Any]] = {}


class SyncRequest(BaseModel):
    mode: str = "incremental"


class SyncResponse(BaseModel):
    job_id: str
    status: str
    message: str


def _run_ingest(job_id: str, kb_type: str, mode: str, agent_type: str | None = None) -> None:
    job = _jobs[job_id]
    try:
        from agent_backend.rag_engine.ingest import ingest_directory
        from agent_backend.rag_engine.settings import RagIngestSettings
        from agent_backend.rag_engine.state import IngestStateStore

        settings = RagIngestSettings.from_global_settings()

        if agent_type:
            try:
                from agent_backend.agent.registry import get_registry
                registry = get_registry()
                if registry.has_agent(agent_type):
                    rag_config = registry.get_rag_config(agent_type)
                    if kb_type == "sql":
                        if rag_config.sql_dir:
                            settings.sql_dir = rag_config.sql_dir
                        if rag_config.sql_collection:
                            settings.qdrant_sql_collection = rag_config.sql_collection
                    else:
                        if rag_config.docs_dir:
                            settings.docs_dir = rag_config.docs_dir
                        if rag_config.docs_collection:
                            settings.qdrant_collection = rag_config.docs_collection
            except Exception:
                pass

        if kb_type == "sql":
            docs_dir = settings.resolve_path(settings.sql_dir)
            state_path = settings.resolve_path(settings.sql_state_path)
        else:
            docs_dir = settings.resolve_path(settings.docs_dir)
            state_path = settings.resolve_path(settings.docs_state_path)

        state = IngestStateStore(state_path)
        result = ingest_directory(
            docs_dir=docs_dir,
            settings=settings,
            state_store=state,
            mode=mode,
            kb_type=kb_type,
        )

        job["status"] = "completed"
        job["result"] = {
            "files_scanned": result.files_scanned,
            "files_skipped": result.files_skipped,
            "files_processed": result.files_processed,
            "chunks_upserted": result.chunks_upserted,
            "errors": result.errors,
        }
        logger.info(
            f"\n同步任务完成 [{job_id}]: "
            f"扫描={result.files_scanned}, 跳过={result.files_skipped}, "
            f"处理={result.files_processed}, 写入={result.chunks_upserted}"
        )
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        logger.error(f"\n同步任务失败 [{job_id}]: {e}")


@router.post("/sync", response_model=SyncResponse)
def sync_docs(agent_type: str, req: SyncRequest) -> SyncResponse:
    mode = req.mode if req.mode in ("full", "incremental") else "incremental"
    job_id = str(uuid.uuid4())[:8]

    _jobs[job_id] = {"status": "running", "kb_type": "docs", "mode": mode}

    t = threading.Thread(target=_run_ingest, args=(job_id, "docs", mode, agent_type), daemon=True)
    t.start()

    logger.info(f"\n文档同步任务已启动 [{job_id}], 智能体: {agent_type}, 模式: {mode}")
    return SyncResponse(
        job_id=job_id,
        status="running",
        message=f"文档同步任务已启动, 模式: {mode}",
    )


@router.post("/sync-sql", response_model=SyncResponse)
def sync_sql_samples(agent_type: str, req: SyncRequest) -> SyncResponse:
    mode = req.mode if req.mode in ("full", "incremental") else "incremental"
    job_id = str(uuid.uuid4())[:8]

    _jobs[job_id] = {"status": "running", "kb_type": "sql", "mode": mode}

    t = threading.Thread(target=_run_ingest, args=(job_id, "sql", mode, agent_type), daemon=True)
    t.start()

    logger.info(f"\nSQL样本同步任务已启动 [{job_id}], 智能体: {agent_type}, 模式: {mode}")
    return SyncResponse(
        job_id=job_id,
        status="running",
        message=f"SQL样本同步任务已启动, 模式: {mode}",
    )


@router.get("/sync/{job_id}")
def get_sync_status(agent_type: str, job_id: str) -> dict:
    job = _jobs.get(job_id)
    if not job:
        return {"job_id": job_id, "status": "not_found"}
    return {"job_id": job_id, **job}
