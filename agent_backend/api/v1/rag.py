"""
RAG 知识库同步 API 端点

文件功能：
    提供文档知识库和 SQL 样本库的异步同步接口，支持全量和增量两种同步模式。
    同步任务在后台执行，通过 job_id 查询任务状态。

核心作用与设计目的：
    - 将文档/SQL 样本解析、分块、向量化并写入 Qdrant 向量数据库
    - 采用异步后台任务模式，避免长时间同步阻塞 HTTP 请求
    - 支持增量同步（基于文件指纹跳过未变更文件）和全量同步

主要使用场景：
    - 运维人员通过 API 触发知识库更新
    - 前端管理界面提供同步操作按钮
    - CI/CD 流程中自动同步知识库

API 端点：
    POST /api/v1/rag/sync       - 同步文档知识库
    POST /api/v1/rag/sync-sql   - 同步 SQL 样本库
    GET  /api/v1/rag/sync/{job_id} - 查询同步任务状态

包含的主要函数：
    - sync_docs(): 触发文档知识库同步（后台任务）
    - sync_sql(): 触发 SQL 样本库同步（后台任务）
    - get_sync_job(): 查询同步任务状态
    - _run_job(): 文档同步后台执行逻辑（内部方法）
    - _run_sql_job(): SQL 样本同步后台执行逻辑（内部方法）

性能考量：
    - 同步任务在 FastAPI BackgroundTasks 中执行，不占用工作线程池
    - _jobs 字典为进程内内存存储，服务重启后任务状态丢失

相关联的调用文件：
    - agent_backend/rag_engine/ingest.py: 实际执行文档导入的 ingest_directory()
    - agent_backend/rag_engine/settings.py: 同步配置参数
    - agent_backend/rag_engine/state.py: 增量同步状态管理
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
    """获取当前 UTC 时间的 ISO 8601 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _run_job(job_id: str, mode: Literal["full", "incremental"], docs_dir: str | None) -> None:
    """
    文档知识库同步后台任务。

    执行流程：
        1. 初始化 RagIngestSettings 和 IngestStateStore
        2. 调用 ingest_directory() 执行文档解析、分块、向量化与入库
        3. 成功时更新 job 状态为 succeeded，记录扫描/跳过/入库数量
        4. 失败时更新 job 状态为 failed，记录异常信息

    参数：
        job_id: 任务唯一标识
        mode: 同步模式，"full" 全量或 "incremental" 增量
        docs_dir: 文档目录路径，为 None 时使用配置默认值

    注意事项：
        - 该方法在 FastAPI BackgroundTasks 线程中执行，不应抛出未捕获异常
    """
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
    """
    SQL 样本库同步后台任务。

    执行流程：
        1. 初始化 RagIngestSettings 和 IngestStateStore（使用 sql_state_path）
        2. 调用 ingest_directory() 执行 SQL 样本解析、分块、向量化与入库（kb_type="sql"）
        3. 成功时更新 job 状态为 succeeded
        4. 失败时更新 job 状态为 failed

    参数：
        job_id: 任务唯一标识
        mode: 同步模式，"full" 全量或 "incremental" 增量
        sql_dir: SQL 样本目录路径，为 None 时使用配置默认值
    """
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
    """
    触发文档知识库同步任务（异步后台执行）。

    参数：
        payload: 同步请求参数
            - docs_dir (str | None): 自定义文档目录，为 None 时使用配置默认值
            - mode ("full" | "incremental"): 同步模式，默认增量

    返回：
        SyncResponse: 包含 job_id、同步模式和启动时间的响应，HTTP 状态码 202

    说明：
        - 实际同步在后台线程中执行，通过 GET /rag/sync/{job_id} 查询进度
    """
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
    """
    触发 SQL 样本库同步任务（异步后台执行）。

    参数：
        payload: SQL 同步请求参数
            - sql_dir (str | None): 自定义 SQL 样本目录，为 None 时使用配置默认值
            - mode ("full" | "incremental"): 同步模式，默认增量

    返回：
        SyncResponse: 包含 job_id、同步模式和启动时间的响应，HTTP 状态码 202
    """
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
    """
    查询同步任务状态。

    参数：
        job_id: 任务唯一标识（由 sync_docs/sync_sql 返回）

    返回：
        JobStatus: 任务状态详情，包含 status/started_at/finished_at/files_scanned 等

    异常：
        AppError(404): job_id 不存在时抛出
    """
    job = _jobs.get(job_id)
    if not job:
        raise AppError(code="job_not_found", message="job not found", http_status=404)
    return job
