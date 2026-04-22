"""
运维简报 REST API路由

文件功能：
    提供运维智能简报的查询、生成、标记已读等REST API端点。

在系统架构中的定位：
    位于API层v1版本路由组，前缀为 /ops。
    通过 OpsReportManager 单例管理运维简报的生命周期。

API端点：
    GET  /api/v1/ops/reports              : 列出简报（支持分页和未读筛选）
    GET  /api/v1/ops/reports/latest       : 获取最新一期简报
    GET  /api/v1/ops/reports/{report_id}   : 获取指定简报详情
    POST /api/v1/ops/reports/run          : 手动触发生成新一期简报
    PUT  /api/v1/ops/reports/{id}/read     : 标记简报为已读

关联文件：
    - agent_backend/ops_reports/manager.py: OpsReportManager 业务管理器
    - agent_backend/ops_reports/executor.py: OpsReportExecutor 报告生成器
    - agent_backend/api/routes.py: 路由注册
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agent_backend.api.external_identity import ExternalIdentity, require_external_identity
from agent_backend.ops_reports import get_ops_report_manager

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/reports")
async def list_ops_reports(
    limit: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
    current_user: ExternalIdentity = Depends(require_external_identity),
) -> dict[str, Any]:
    """列出运维简报，支持分页和未读筛选"""
    manager = get_ops_report_manager()
    return await manager.list_reports(limit=limit, unread_only=unread_only)


@router.get("/reports/latest")
async def get_latest_ops_report(
    current_user: ExternalIdentity = Depends(require_external_identity),
) -> dict[str, Any]:
    """获取最新一期运维简报"""
    manager = get_ops_report_manager()
    return await manager.get_latest_report()


@router.get("/reports/{report_id}")
async def get_ops_report(
    report_id: str,
    current_user: ExternalIdentity = Depends(require_external_identity),
) -> dict[str, Any]:
    """获取指定ID的运维简报详情"""
    manager = get_ops_report_manager()
    report = await manager.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"运维简报不存在: {report_id}")
    return report


@router.post("/reports/run")
async def run_ops_report_now(
    current_user: ExternalIdentity = Depends(require_external_identity),
) -> dict[str, Any]:
    """手动触发生成新一期运维简报"""
    manager = get_ops_report_manager()
    try:
        return await manager.run_report_now()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"生成运维简报失败: {exc}") from exc


@router.put("/reports/{report_id}/read")
async def mark_ops_report_read(
    report_id: str,
    current_user: ExternalIdentity = Depends(require_external_identity),
) -> dict[str, Any]:
    """标记指定运维简报为已读"""
    manager = get_ops_report_manager()
    result = await manager.mark_report_read(report_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"运维简报不存在: {report_id}")
    return result
