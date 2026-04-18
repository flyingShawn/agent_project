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

from agent_backend.scheduler import get_scheduler_manager

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    scheduler = get_scheduler_manager()
    scheduler_info = scheduler.get_scheduler_info()
    return {"status": "ok", "scheduler": scheduler_info}
