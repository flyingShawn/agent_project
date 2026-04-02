"""
健康检查 API 端点

文件目的：
    - 提供服务健康状态检查接口
    - 用于Kubernetes/负载均衡器的健康探测
    - 验证服务是否正常运行

API端点：
    GET /api/v1/health
    返回: {"status": "ok"}

调用流程：
    客户端 -> GET /api/v1/health -> health() -> 返回状态

使用场景：
    - K8s liveness/readiness probe
    - 负载均衡器健康检查
    - 监控系统服务状态检测
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}

