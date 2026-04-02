"""
SQL代理 API 端点

文件目的：
    - 提供自然语言转SQL的接口
    - 支持SQL生成和执行两种模式
    - 基于权限模板生成安全的SQL语句

API端点：
    POST /api/v1/sql/generate
    请求体: {
        "question": "自然语言问题",
        "lognum": "用户工号",
        "permission_name": "权限名称",  # 可选
        "params": {},                  # 参数
        "execute": false,              # 是否执行
        "max_rows": 200                # 最大返回行数
    }
    返回: {
        "sql": "生成的SQL",
        "params": {},
        "used_template": "使用的模板",
        "rows": [...]  # 如果execute=true
    }

调用流程：
    客户端 -> POST /sql/generate 
    -> generate_secure_sql() -> 生成SQL
    -> execute_sql() (可选) -> 执行SQL
    -> 返回结果

相关文件：
    - agent_backend/sql_agent/service.py: SQL生成服务
    - agent_backend/sql_agent/executor.py: SQL执行器
    - agent_backend/sql_agent/types.py: 类型定义
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent_backend.sql_agent.executor import execute_sql
from agent_backend.sql_agent.service import generate_secure_sql
from agent_backend.sql_agent.types import SqlGenRequest


router = APIRouter(tags=["sql"])


class SqlGenerateRequest(BaseModel):
    question: str = Field(min_length=1)
    lognum: str = Field(min_length=1)
    permission_name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    execute: bool = False
    max_rows: int = Field(default=200, ge=1, le=2000)


class SqlGenerateResponse(BaseModel):
    sql: str
    params: dict[str, Any]
    used_template: str | None = None
    rows: list[dict[str, Any]] | None = None


@router.post("/sql/generate", response_model=SqlGenerateResponse)
def generate_sql(req: SqlGenerateRequest) -> SqlGenerateResponse:
    result = generate_secure_sql(
        SqlGenRequest(
            question=req.question,
            lognum=req.lognum,
            permission_name=req.permission_name,
            params=req.params,
        )
    )
    rows = None
    if req.execute:
        rows = execute_sql(sql=result.sql, params=result.params, max_rows=req.max_rows)
    return SqlGenerateResponse(
        sql=result.sql,
        params=result.params,
        used_template=result.used_template,
        rows=rows,
    )
