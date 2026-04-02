"""
RAG (检索增强生成) API 端点

文件目的：
    - 提供文档同步和任务状态查询接口
    - 支持全量和增量两种同步模式
    - 使用后台任务异步处理文档导入

API端点：
    POST /api/v1/rag/sync
    请求体: {
        "docs_dir": "文档目录路径",  # 可选
        "mode": "full|incremental"   # 同步模式
    }
    返回: {
        "job_id": "任务ID",
        "mode": "同步模式",
        "started_at": "开始时间"
    }

    GET /api/v1/rag/sync/{job_id}
    返回: {
        "job_id": "任务ID",
        "status": "running|succeeded|failed",
        "files_scanned": int,
        "chunks_upserted": int,
        "files_skipped": int,
        ...
    }

调用流程：
    客户端 -> POST /rag/sync -> 创建后台任务 -> 返回job_id
    客户端 -> GET /rag/sync/{job_id} -> 查询任务状态

相关文件：
    - agent_backend/rag_engine/ingest.py: 文档导入核心逻辑
    - agent_backend/rag_engine/settings.py: RAG配置
    - agent_backend/rag_engine/state.py: 状态存储
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from agent_backend.core.errors import AppError
from agent_backend.rag_engine.ingest import ingest_directory
from agent_backend.rag_engine.settings import RagIngestSettings
from agent_backend.rag_engine.state import IngestStateStore


router = APIRouter(tags=["rag"])


class SyncRequest(BaseModel):
    docs_dir: str | None = Field(default=None)
    mode: Literal["full", "incremental"] = Field(default="incremental")


class SyncResponse(BaseModel):
    job_id: str
    mode: Literal["full", "incremental"]
    started_at: str


class JobStatus(BaseModel):
    job_id: str
    mode: Literal["full", "incremental"]
    status: Literal["running", "succeeded", "failed"]
    started_at: str
    finished_at: str | None = None
    error: str | None = None
    files_scanned: int = 0
    chunks_upserted: int = 0
    files_skipped: int = 0


_jobs: dict[str, JobStatus] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_job(job_id: str, mode: Literal["full", "incremental"], docs_dir: str | None) -> None:
    settings = RagIngestSettings()
    state = IngestStateStore(settings.state_path)
    try:
        result = ingest_directory(
            docs_dir=docs_dir or settings.docs_dir,
            settings=settings,
            state_store=state,
            mode=mode,
        )
        _jobs[job_id].status = "succeeded"
        _jobs[job_id].finished_at = _utc_now_iso()
        _jobs[job_id].files_scanned = result.files_scanned
        _jobs[job_id].files_skipped = result.files_skipped
        _jobs[job_id].chunks_upserted = result.chunks_upserted
    except Exception as e:
        _jobs[job_id].status = "failed"
        _jobs[job_id].finished_at = _utc_now_iso()
        _jobs[job_id].error = f"{type(e).__name__}: {e}"


@router.post("/rag/sync", response_model=SyncResponse, status_code=202)
def sync_docs(payload: SyncRequest, background_tasks: BackgroundTasks) -> SyncResponse:
    job_id = str(uuid.uuid4())
    started_at = _utc_now_iso()
    _jobs[job_id] = JobStatus(
        job_id=job_id,
        mode=payload.mode,
        status="running",
        started_at=started_at,
    )
    background_tasks.add_task(_run_job, job_id, payload.mode, payload.docs_dir)
    return SyncResponse(job_id=job_id, mode=payload.mode, started_at=started_at)


@router.get("/rag/sync/{job_id}", response_model=JobStatus)
def get_sync_job(job_id: str) -> JobStatus:
    job = _jobs.get(job_id)
    if not job:
        raise AppError(code="job_not_found", message="job not found", http_status=404)
    return job
