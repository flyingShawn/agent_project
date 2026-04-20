"""
健康检查API接口模块

文件功能：
    提供服务健康检查端点，用于监控系统和负载均衡器探测服务状态。

在系统架构中的定位：
    位于API层，是最轻量的端点，不依赖任何业务模块。

主要使用场景：
    - 负载均衡器（Nginx/Docker）定期探测后端存活状态
    - 运维监控系统集成健康检查
    - 前端判断后端服务是否可用

核心端点：
    - GET /api/v1/health: 返回{"status": "ok"}表示服务正常

关联文件：
    - agent_backend/api/routes.py: 路由注册
"""
from __future__ import annotations

from fastapi import APIRouter

from agent_backend.core.config import reload_schema_runtime, reload_prompts
from agent_backend.ops_reports import get_ops_report_manager

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    ops_reports = get_ops_report_manager()
    ops_report_info = ops_reports.get_info()
    return {"status": "ok", "ops_reports": ops_report_info}


@router.post("/admin/reload_schema")
def admin_reload_schema() -> dict:
    runtime = reload_schema_runtime()
    return {
        "status": "ok",
        "message": "Schema元数据已重新加载",
        "tables": len(runtime.raw.tables),
        "synonyms": len(runtime.raw.synonyms or {}),
    }


@router.post("/admin/reload_prompts")
def admin_reload_prompts() -> dict:
    data = reload_prompts()
    return {
        "status": "ok",
        "message": "提示词配置已重新加载",
        "keys": list(data.keys()),
    }
