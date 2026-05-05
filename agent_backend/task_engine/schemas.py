"""
任务引擎 API 数据模型

文件功能：
    定义任务相关 API 的请求和响应 Pydantic 模型。

核心模型：
    TaskValidateRequest: 步骤参数校验请求
    TaskExecuteRequest: 任务执行请求
    TaskOptionQueryParams: 动态选项查询参数

关联文件：
    - api/v1/tasks.py: 使用这些模型
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TaskValidateRequest(BaseModel):
    step_id: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class TaskExecuteRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class TaskOptionQueryParams(BaseModel):
    keyword: str | None = None
    parent_id: str | None = None
