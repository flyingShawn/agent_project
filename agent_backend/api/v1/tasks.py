"""
任务 API 路由模块

文件功能：
    提供任务模式相关的 REST API 端点，包括任务列表查询、
    参数 Schema 获取、步骤参数校验、任务执行和动态选项获取。

核心端点：
    GET  /{agent_type}/tasks: 获取智能体任务列表
    GET  /{agent_type}/tasks/{task_id}/schema: 获取任务参数 Schema
    POST /{agent_type}/tasks/{task_id}/validate: 校验步骤参数
    POST /{agent_type}/tasks/{task_id}/execute: 执行任务
    GET  /{agent_type}/tasks/options/{option_type}: 获取动态选项

关联文件：
    - task_engine/registry.py: TaskRegistry
    - task_engine/executor.py: TaskExecutor
    - task_engine/schemas.py: 请求/响应模型
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException

from agent_backend.agent.registry import get_registry
from agent_backend.api.external_identity import require_external_identity
from agent_backend.core.context import current_agent_type
from agent_backend.task_engine.executor import (
    TaskNotFoundError,
    TaskParamValidationError,
    get_task_executor,
)
from agent_backend.task_engine.registry import get_task_registry
from agent_backend.task_engine.schemas import TaskExecuteRequest, TaskValidateRequest

router = APIRouter(prefix="/{agent_type}/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(agent_type: str):
    registry = get_registry()
    if not registry.has_agent(agent_type):
        raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_type}")

    config = registry.get_agent_config(agent_type)
    if not config or not config.tasks.enabled:
        return {"tasks": []}

    task_registry = get_task_registry()
    tasks = task_registry.get_tasks(agent_type)
    return {"tasks": [t.get_summary() for t in tasks]}


@router.get("/{task_id}/schema")
async def get_task_schema(agent_type: str, task_id: str):
    task_registry = get_task_registry()
    task = task_registry.get_task(agent_type, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {agent_type}/{task_id}")
    return task.get_schema()


@router.post("/{task_id}/validate")
async def validate_task_step(
    agent_type: str,
    task_id: str,
    req: TaskValidateRequest,
):
    task_registry = get_task_registry()
    task = task_registry.get_task(agent_type, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {agent_type}/{task_id}")

    result = await task.validate_step(req.step_id, req.params)
    return result


@router.post("/{task_id}/execute")
async def execute_task(
    agent_type: str,
    task_id: str,
    req: TaskExecuteRequest,
    identity=Depends(require_external_identity),
):
    current_agent_type.set(agent_type)

    registry = get_registry()
    if not registry.has_agent(agent_type):
        raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_type}")

    executor = get_task_executor()
    try:
        result = await executor.execute_task(
            agent_type=agent_type,
            task_id=task_id,
            params=req.params,
            user_id=identity.user_id,
        )
        return result.model_dump()
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TaskParamValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/options/{option_type}")
async def get_task_options(
    agent_type: str,
    option_type: str,
    keyword: str | None = None,
):
    current_agent_type.set(agent_type)

    registry = get_registry()
    config = registry.get_agent_config(agent_type)
    if not config or not config.tasks.enabled or not config.tasks.api_base_url:
        return {"options": []}

    api_base = config.tasks.api_base_url
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {}
            if keyword:
                params["keyword"] = keyword
            resp = await client.get(
                f"{api_base}/api/options/{option_type}", params=params
            )
            if resp.status_code == 200:
                return resp.json()
            return {"options": []}
    except Exception:
        return {"options": []}
