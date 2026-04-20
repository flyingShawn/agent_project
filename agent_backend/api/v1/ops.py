from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from agent_backend.ops_reports import get_ops_report_manager

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/reports")
async def list_ops_reports(
    limit: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
) -> dict[str, Any]:
    manager = get_ops_report_manager()
    return await manager.list_reports(limit=limit, unread_only=unread_only)


@router.get("/reports/latest")
async def get_latest_ops_report() -> dict[str, Any]:
    manager = get_ops_report_manager()
    return await manager.get_latest_report()


@router.get("/reports/{report_id}")
async def get_ops_report(report_id: str) -> dict[str, Any]:
    manager = get_ops_report_manager()
    report = await manager.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"运维简报不存在: {report_id}")
    return report


@router.post("/reports/run")
async def run_ops_report_now() -> dict[str, Any]:
    manager = get_ops_report_manager()
    try:
        return await manager.run_report_now()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"生成运维简报失败: {exc}") from exc


@router.put("/reports/{report_id}/read")
async def mark_ops_report_read(report_id: str) -> dict[str, Any]:
    manager = get_ops_report_manager()
    result = await manager.mark_report_read(report_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"运维简报不存在: {report_id}")
    return result
