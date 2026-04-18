"""
定时任务管理 REST API 路由模块

文件功能：
    定义定时任务管理的 REST API 端点，提供任务的查询、手动执行、
    暂停、恢复、删除等 HTTP 接口。

在系统架构中的定位：
    位于 API 路由层，是前端与调度器之间的桥梁。
    - 对上：前端通过 HTTP 请求调用这些接口
    - 对下：调用 SchedulerManager 的对应方法执行业务逻辑

主要使用场景：
    - 前端定时任务管理页面查询和操作任务
    - 第三方系统集成定时任务管理能力

核心端点：
    - GET /scheduler/tasks: 获取所有活跃任务列表
    - GET /scheduler/tasks/{task_id}/results: 获取任务执行结果
    - POST /scheduler/tasks/{task_id}/run: 手动触发任务执行
    - PUT /scheduler/tasks/{task_id}/pause: 暂停任务
    - PUT /scheduler/tasks/{task_id}/resume: 恢复任务
    - DELETE /scheduler/tasks/{task_id}: 删除任务

路由前缀：
    /api/v1/scheduler（由 routes.py 挂载到 /api/v1 下）

关联文件：
    - agent_backend/scheduler/manager.py: SchedulerManager 业务逻辑实现
    - agent_backend/api/routes.py: 路由注册入口
"""
import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from agent_backend.scheduler import get_scheduler_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/tasks")
async def get_tasks() -> dict[str, Any]:
    """
    获取所有活跃定时任务列表。

    返回：
        dict: {"tasks": [...], "total": N}
        tasks 列表中每个元素包含任务的完整信息。
        排除已软删除（status=completed）的任务。
    """
    scheduler = get_scheduler_manager()
    tasks = await scheduler.get_tasks()
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/tasks/{task_id}/results")
async def get_task_results(
    task_id: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """
    获取指定任务的执行结果列表。

    参数：
        task_id: 任务唯一标识（路径参数）
        limit: 返回结果数量上限，默认20，范围1-100（查询参数）

    返回：
        dict: {"task_id": ..., "results": [...], "total": N}

    异常：
        404: 任务不存在
    """
    scheduler = get_scheduler_manager()
    task = await scheduler.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    results = await scheduler.get_task_results(task_id, limit=limit)
    return {"task_id": task_id, "results": results, "total": len(results)}


@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: str) -> dict[str, Any]:
    """
    手动触发任务立即执行。

    参数：
        task_id: 要执行的任务唯一标识（路径参数）

    返回：
        dict: 执行结果，包含 task_id, status, row_count, duration_ms

    异常：
        400: 任务不存在、状态不允许执行、或执行出错
    """
    scheduler = get_scheduler_manager()
    result = await scheduler.run_task_now(task_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.put("/tasks/{task_id}/pause")
async def pause_task(task_id: str) -> dict[str, Any]:
    """
    暂停指定的活跃任务。

    参数：
        task_id: 要暂停的任务唯一标识（路径参数）

    返回：
        dict: {"task_id": ..., "status": "paused"}

    异常：
        400: 任务不存在、状态不允许暂停
    """
    scheduler = get_scheduler_manager()
    result = await scheduler.pause_task(task_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.put("/tasks/{task_id}/resume")
async def resume_task(task_id: str) -> dict[str, Any]:
    """
    恢复已暂停的任务。

    参数：
        task_id: 要恢复的任务唯一标识（路径参数）

    返回：
        dict: {"task_id": ..., "status": "active"}

    异常：
        400: 任务不存在、状态不允许恢复
    """
    scheduler = get_scheduler_manager()
    result = await scheduler.resume_task(task_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str) -> dict[str, Any]:
    """
    软删除指定任务（标记为completed）。

    参数：
        task_id: 要删除的任务唯一标识（路径参数）

    返回：
        dict: {"task_id": ..., "status": "completed"}

    异常：
        400: 任务不存在

    注意：
        采用软删除策略，任务定义和执行历史保留在数据库中。
    """
    scheduler = get_scheduler_manager()
    result = await scheduler.delete_task(task_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
