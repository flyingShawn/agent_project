"""
SQL Agent 数据类型定义

文件功能：
    定义SQL生成模块的请求与响应数据结构，使用不可变dataclass确保数据安全。

在系统架构中的定位：
    位于SQL Agent模块的底层，被 service.py、sql_tool.py、api/v1/sql_agent.py 共同引用。

核心类：
    - SqlGenRequest: SQL生成请求，包含用户问题、工号和查询参数
    - SqlGenResult: SQL生成结果，包含生成的SQL、参数、模板和警告信息

关联文件：
    - agent_backend/sql_agent/service.py: 使用 SqlGenRequest/SqlGenResult
    - agent_backend/agent/tools/sql_tool.py: 使用 SqlGenRequest/SqlGenResult
    - agent_backend/api/v1/sql_agent.py: API层构造 SqlGenRequest
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SqlGenRequest:
    """SQL生成请求数据结构

    参数：
        question: 用户自然语言问题
        lognum: 用户工号，用于审计和权限控制
        params: 查询参数字典，用于参数化SQL中的占位符替换
    """
    question: str
    lognum: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SqlGenResult:
    """SQL生成结果数据结构

    参数：
        sql: 生成的SQL语句（已通过安全校验）
        params: SQL执行所需的参数字典
        used_template: 使用的SQL模板标识（当前始终为None，预留模板匹配扩展）
        warnings: 生成过程中的警告信息列表（如安全校验降级提示）
    """
    sql: str
    params: dict[str, Any]
    used_template: str | None = None
    warnings: list[str] = field(default_factory=list)
