"""
智能体列表 API 路由模块

文件功能：
    提供已启用智能体列表查询接口。

核心端点：
    GET /api/v1/agents: 获取已启用智能体列表

关联文件：
    - agent_backend/agent/registry.py: AgentRegistry 智能体注册表
"""
from __future__ import annotations

from fastapi import APIRouter

from agent_backend.agent.registry import get_registry

router = APIRouter(tags=["agents"])


@router.get("/agents")
async def list_agents() -> dict:
    registry = get_registry()
    agents = registry.get_enabled_agents()
    return {
        "agents": [
            {
                "agent_type": a.agent_type,
                "display_name": a.display_name,
                "reports_enabled": a.reports.enabled,
            }
            for a in agents
        ],
        "default_agent_type": registry.get_default_agent_type(),
    }
