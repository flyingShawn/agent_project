import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from agent_backend.scheduler import get_scheduler_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/tasks")
async def get_tasks() -> dict[str, Any]:
    scheduler = get_scheduler_manager()
    tasks = await scheduler.get_tasks()
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/tasks/{task_id}/results")
async def get_task_results(
    task_id: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    scheduler = get_scheduler_manager()
    task = await scheduler.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    results = await scheduler.get_task_results(task_id, limit=limit)
    return {"task_id": task_id, "results": results, "total": len(results)}


@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: str) -> dict[str, Any]:
    scheduler = get_scheduler_manager()
    result = await scheduler.run_task_now(task_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.put("/tasks/{task_id}/pause")
async def pause_task(task_id: str) -> dict[str, Any]:
    scheduler = get_scheduler_manager()
    result = await scheduler.pause_task(task_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.put("/tasks/{task_id}/resume")
async def resume_task(task_id: str) -> dict[str, Any]:
    scheduler = get_scheduler_manager()
    result = await scheduler.resume_task(task_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str) -> dict[str, Any]:
    scheduler = get_scheduler_manager()
    result = await scheduler.delete_task(task_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
