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


class SqlSyncRequest(BaseModel):
    sql_dir: str | None = Field(default=None)
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
            kb_type="docs",
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


def _run_sql_job(job_id: str, mode: Literal["full", "incremental"], sql_dir: str | None) -> None:
    settings = RagIngestSettings()
    state = IngestStateStore(settings.sql_state_path)
    try:
        result = ingest_directory(
            docs_dir=sql_dir or settings.sql_dir,
            settings=settings,
            state_store=state,
            mode=mode,
            kb_type="sql",
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


@router.post("/rag/sync-sql", response_model=SyncResponse, status_code=202)
def sync_sql(payload: SqlSyncRequest, background_tasks: BackgroundTasks) -> SyncResponse:
    job_id = str(uuid.uuid4())
    started_at = _utc_now_iso()
    _jobs[job_id] = JobStatus(
        job_id=job_id,
        mode=payload.mode,
        status="running",
        started_at=started_at,
    )
    background_tasks.add_task(_run_sql_job, job_id, payload.mode, payload.sql_dir)
    return SyncResponse(job_id=job_id, mode=payload.mode, started_at=started_at)


@router.get("/rag/sync/{job_id}", response_model=JobStatus)
def get_sync_job(job_id: str) -> JobStatus:
    job = _jobs.get(job_id)
    if not job:
        raise AppError(code="job_not_found", message="job not found", http_status=404)
    return job
