"""
任务 API 路由模块

文件功能：
    提供任务模式相关的 REST API 端点，包括任务列表查询、
    参数 Schema 获取、步骤参数校验、任务执行、动态选项获取和文件浏览。

核心端点：
    GET  /{agent_type}/tasks: 获取智能体任务列表
    GET  /{agent_type}/tasks/{task_id}/schema: 获取任务参数 Schema
    POST /{agent_type}/tasks/{task_id}/validate: 校验步骤参数
    POST /{agent_type}/tasks/{task_id}/execute: 执行任务
    GET  /{agent_type}/tasks/options/{option_type}: 获取动态选项
    GET  /{agent_type}/tasks/browse: 浏览管理机文件系统

关联文件：
    - task_engine/registry.py: TaskRegistry
    - task_engine/executor.py: TaskExecutor
    - task_engine/schemas.py: 请求/响应模型
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/{agent_type}/tasks", tags=["tasks"])

_BROWSE_ROOTS: list[str] | None = None


def _get_browse_roots() -> list[str]:
    global _BROWSE_ROOTS
    if _BROWSE_ROOTS is not None:
        return _BROWSE_ROOTS
    roots_str = os.environ.get("FILE_BROWSE_ROOTS", "")
    if roots_str:
        _BROWSE_ROOTS = [r.strip() for r in roots_str.split(",") if r.strip()]
    else:
        if os.name == "nt":
            _BROWSE_ROOTS = [f"{d}:\\" for d in "CDEFGH" if os.path.isdir(f"{d}:\\")]
        else:
            _BROWSE_ROOTS = ["/"]
    return _BROWSE_ROOTS


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


_MOCK_CLIENTS = [
    {"label": "研发部-PC001", "value": "client-001", "detail": "192.168.1.101", "status": "online"},
    {"label": "研发部-PC002", "value": "client-002", "detail": "192.168.1.102", "status": "online"},
    {"label": "研发部-PC003", "value": "client-003", "detail": "192.168.1.103", "status": "offline"},
    {"label": "测试部-PC004", "value": "client-004", "detail": "192.168.1.104", "status": "online"},
    {"label": "测试部-PC005", "value": "client-005", "detail": "192.168.1.105", "status": "online"},
    {"label": "运维部-PC006", "value": "client-006", "detail": "192.168.1.106", "status": "offline"},
]

_MOCK_DEPARTMENTS = [
    {"label": "研发部", "value": "dept-rd", "count": 45},
    {"label": "测试部", "value": "dept-qa", "count": 20},
    {"label": "运维部", "value": "dept-ops", "count": 15},
    {"label": "产品部", "value": "dept-pm", "count": 12},
    {"label": "设计部", "value": "dept-design", "count": 8},
]


@router.get("/options/{option_type}")
async def get_task_options(
    agent_type: str,
    option_type: str,
    keyword: str | None = None,
):
    current_agent_type.set(agent_type)

    registry = get_registry()
    config = registry.get_agent_config(agent_type)
    if not config or not config.tasks.enabled:
        return {"options": _get_mock_options(option_type, keyword)}

    api_base = config.tasks.api_base_url
    if api_base:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                params = {}
                if keyword:
                    params["keyword"] = keyword
                resp = await client.get(
                    f"{api_base}/api/options/{option_type}", params=params
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("options"):
                        return data
        except Exception:
            pass

    return {"options": _get_mock_options(option_type, keyword)}


def _get_mock_options(option_type: str, keyword: str | None = None) -> list[dict]:
    if option_type == "client":
        items = _MOCK_CLIENTS
    elif option_type == "department":
        items = _MOCK_DEPARTMENTS
    else:
        return []

    if keyword:
        kw = keyword.lower()
        items = [i for i in items if kw in i["label"].lower() or kw in str(i.get("detail", "")).lower()]

    return items


@router.get("/browse")
async def browse_filesystem(
    agent_type: str,
    path: str = Query(default="", description="要浏览的目录路径，为空则返回根目录列表"),
    file_type: str = Query(default="all", description="筛选类型：all/file/dir"),
):
    current_agent_type.set(agent_type)

    registry = get_registry()
    if not registry.has_agent(agent_type):
        raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_type}")

    if not path:
        roots = _get_browse_roots()
        items = []
        for root in roots:
            items.append({
                "name": root,
                "path": root,
                "type": "dir",
                "size": None,
            })
        return {"path": "", "parent": None, "items": items}

    try:
        target = Path(path)
        if not target.exists():
            raise HTTPException(status_code=404, detail=f"路径不存在: {path}")
        if not target.is_dir():
            raise HTTPException(status_code=400, detail=f"路径不是目录: {path}")

        parent = str(target.parent) if str(target.parent) != str(target) else None

        items = []
        try:
            for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
                try:
                    if entry.is_dir():
                        if file_type == "file":
                            continue
                        items.append({
                            "name": entry.name,
                            "path": str(entry),
                            "type": "dir",
                            "size": None,
                        })
                    elif entry.is_file():
                        if file_type == "dir":
                            continue
                        stat = entry.stat()
                        items.append({
                            "name": entry.name,
                            "path": str(entry),
                            "type": "file",
                            "size": stat.st_size,
                        })
                except (PermissionError, OSError):
                    continue
        except PermissionError:
            raise HTTPException(status_code=403, detail=f"无权限访问: {path}")

        return {"path": str(target), "parent": parent, "items": items}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"\n文件浏览异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))
