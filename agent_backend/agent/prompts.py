"""
Agent系统Prompt定义模块

文件功能：
    定义Agent的系统级Prompt获取接口，指导LLM如何使用工具、决策和回答用户问题。
    Prompt内容从 AgentRegistry 按 agent_type 动态加载，支持配置文件热更新。

在系统架构中的定位：
    位于Agent编排层，作为init_node注入到对话消息列表的SystemMessage中，
    贯穿整个Agent决策循环，约束LLM的工具选择和回答行为。

关联文件：
    - agent_backend/agent/nodes.py: init_node中注入系统提示词
    - agent_backend/agent/registry.py: AgentRegistry 按智能体类型获取提示词
    - agent_backend/core/config.py: get_system_prompt() 从YAML加载提示词
"""
from __future__ import annotations

from agent_backend.core.config import get_system_prompt


def get_system_prompt_for_agent(agent_type: str) -> str:
    from agent_backend.agent.registry import get_registry
    registry = get_registry()
    if registry.has_agent(agent_type):
        return registry.get_system_prompt(agent_type)
    return get_system_prompt()
