"""
SQL Agent REST API路由

文件功能：
    提供SQL生成和执行相关的REST API端点。
    对外暴露独立的SQL生成能力，不依赖Agent编排流程。

在系统架构中的定位：
    位于API层v1版本路由组，注册到主路由 /api/v1/sql。
    直接调用 sql_agent 模块的 service 和 executor 完成业务逻辑。

API端点：
    POST /api/v1/sql/generate: 从自然语言生成SQL并可选执行

请求/响应模型：
    - SqlGenerateRequest: SQL生成请求（question, lognum, params, execute, max_rows）
    - SqlGenerateResponse: SQL生成响应（sql, params, used_template, rows）

关联文件：
    - agent_backend/sql_agent/service.py: generate_secure_sql SQL生成服务
    - agent_backend/sql_agent/executor.py: execute_sql SQL执行器
    - agent_backend/api/routes.py: 路由注册
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent_backend.core.config import get_max_rows
from agent_backend.sql_agent.executor import execute_sql
from agent_backend.sql_agent.service import generate_secure_sql
from agent_backend.sql_agent.types import SqlGenRequest

router = APIRouter(tags=["sql"])


class SqlGenerateRequest(BaseModel):
    """SQL生成API请求模型

    参数：
        question: 用户自然语言问题
        lognum: 用户工号，用于审计
        params: 查询参数字典
        execute: 是否同时执行生成的SQL，默认False
        max_rows: 执行时返回的最大行数（1-2000），None使用全局默认值
    """
    question: str = Field(min_length=1)
    lognum: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    execute: bool = False
    max_rows: int | None = Field(default=None, ge=1, le=2000)


class SqlGenerateResponse(BaseModel):
    """SQL生成API响应模型

    参数：
        sql: 生成的SQL语句
        params: SQL参数字典
        used_template: 使用的模板标识（当前始终为None）
        rows: SQL执行结果行列表（execute=True时返回）
    """
    sql: str
    params: dict[str, Any]
    used_template: str | None = None
    rows: list[dict[str, Any]] | None = None


@router.post("/sql/generate", response_model=SqlGenerateResponse)
def generate_sql(req: SqlGenerateRequest) -> SqlGenerateResponse:
    """
    SQL生成并可选执行的API端点。

    流程：自然语言→安全校验SQL→（可选）执行SQL返回结果
    """
    result = generate_secure_sql(
        SqlGenRequest(
            question=req.question,
            lognum=req.lognum,
            params=req.params,
        ),
    )
    rows = None
    if req.execute:
        max_rows = req.max_rows if req.max_rows is not None else get_max_rows()
        rows = execute_sql(sql=result.sql, params=result.params, max_rows=max_rows)
    return SqlGenerateResponse(
        sql=result.sql,
        params=result.params,
        used_template=result.used_template,
        rows=rows,
    )
