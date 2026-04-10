"""
SQL Agent 类型定义模块

文件功能：
    定义 SQL Agent 模块的核心数据类型，包括请求和响应的冻结数据类。

核心作用与设计目的：
    - SqlGenRequest: 封装 SQL 生成请求参数
    - SqlGenResult: 封装 SQL 生成结果
    - 使用 frozen=True 确保数据不可变，避免意外修改

包含的主要类型：
    - SqlGenRequest: SQL 生成请求
        - question: 用户自然语言问题
        - lognum: 用户工号（用于权限过滤）
        - permission_name: 权限模板名称（可选）
        - params: SQL 参数字典
    - SqlGenResult: SQL 生成结果
        - sql: 生成的 SQL 语句
        - params: SQL 参数字典
        - used_template: 使用的查询模板名称（可选）
        - warnings: 警告信息列表

相关联的调用文件：
    - agent_backend/sql_agent/service.py: 使用 SqlGenRequest 和 SqlGenResult
    - agent_backend/api/v1/sql_agent.py: API 端点使用类型定义
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SqlGenRequest:
    question: str
    lognum: str
    permission_name: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SqlGenResult:
    sql: str
    params: dict[str, Any]
    used_template: str | None = None
    warnings: list[str] = field(default_factory=list)
