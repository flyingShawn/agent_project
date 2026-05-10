"""
运维简报 REST API路由

文件功能：
    提供运维智能简报的查询、生成、标记已读、定义管理等REST API端点。

API端点：
    GET  /api/v1/{agent_type}/ops/reports              : 列出简报（支持分页和未读筛选）
    GET  /api/v1/{agent_type}/ops/reports/latest       : 获取最新一期简报
    GET  /api/v1/{agent_type}/ops/reports/{report_id}   : 获取指定简报详情
    POST /api/v1/{agent_type}/ops/reports/run          : 手动触发生成新一期简报
    PUT  /api/v1/{agent_type}/ops/reports/{id}/read     : 标记简报为已读
    GET  /api/v1/{agent_type}/ops/definitions           : 获取简报定义列表
    PUT  /api/v1/{agent_type}/ops/definitions/{report_key} : 更新简报定义

关联文件：
    - agent_backend/ops_reports/manager.py: OpsReportManager 业务管理器
    - agent_backend/ops_reports/executor.py: OpsReportExecutor 报告生成器
    - agent_backend/api/routes.py: 路由注册
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent_backend.ops_reports import get_ops_report_manager

router = APIRouter(prefix="/{agent_type}/ops", tags=["ops"])


class OpsModuleUpdate(BaseModel):
    key: str = Field(min_length=1)
    enabled: bool = True
    type: str | None = None
    range: str | None = None


class OpsScheduleUpdate(BaseModel):
    type: str = Field(default="daily", pattern="^(daily|weekly|interval)$")
    time: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    weekday: int | None = Field(default=None, ge=1, le=7)


class OpsDefinitionUpdate(BaseModel):
    enabled: bool | None = None
    schedule: OpsScheduleUpdate | None = None
    modules: list[OpsModuleUpdate] | None = None


@router.get("/reports")
async def list_ops_reports(
    agent_type: str,
    limit: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
) -> dict[str, Any]:
    manager = get_ops_report_manager()
    return await manager.list_reports(limit=limit, unread_only=unread_only, agent_type=agent_type)


@router.get("/reports/latest")
async def get_latest_ops_report(agent_type: str) -> dict[str, Any]:
    manager = get_ops_report_manager()
    return await manager.get_latest_report(agent_type=agent_type)


@router.get("/reports/{report_id}")
async def get_ops_report(
    agent_type: str,
    report_id: str,
) -> dict[str, Any]:
    manager = get_ops_report_manager()
    report = await manager.get_report(report_id, agent_type=agent_type)
    if not report:
        raise HTTPException(status_code=404, detail=f"运维简报不存在: {report_id}")
    return report


@router.post("/reports/run")
async def run_ops_report_now(
    agent_type: str,
    report_key: str | None = None,
) -> dict[str, Any]:
    manager = get_ops_report_manager()
    try:
        return await manager.run_report_now(report_key=report_key, agent_type=agent_type)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"生成运维简报失败: {exc}") from exc


@router.put("/reports/{report_id}/read")
async def mark_ops_report_read(
    agent_type: str,
    report_id: str,
) -> dict[str, Any]:
    manager = get_ops_report_manager()
    result = await manager.mark_report_read(report_id, agent_type=agent_type)
    if not result:
        raise HTTPException(status_code=404, detail=f"运维简报不存在: {report_id}")
    return result


@router.get("/definitions")
async def list_ops_definitions(agent_type: str) -> dict[str, Any]:
    manager = get_ops_report_manager()
    return manager.list_definitions(agent_type=agent_type)


@router.put("/definitions/{report_key}")
async def update_ops_definition(
    agent_type: str,
    report_key: str,
    body: OpsDefinitionUpdate,
) -> dict[str, Any]:
    manager = get_ops_report_manager()
    try:
        return manager.update_definition(
            report_key,
            body.model_dump(exclude_unset=True),
            agent_type=agent_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/online-trend")
async def get_online_trend(
    agent_type: str,
    hours: int = Query(default=24, ge=1, le=168),
) -> dict[str, Any]:
    manager = get_ops_report_manager()
    return await manager.get_online_trend(hours=hours, agent_type=agent_type)
