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

from agent_backend.core.config_helper import get_max_rows
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
    max_rows: int | None = Field(default=None, ge=1, le=2000)
    use_template: bool = Field(default=False, description="是否优先使用查询模板，默认直接使用LLM生成")


class SqlGenerateResponse(BaseModel):
    sql: str
    params: dict[str, Any]
    used_template: str | None = None
    rows: list[dict[str, Any]] | None = None


@router.post("/sql/generate", response_model=SqlGenerateResponse)
def generate_sql(req: SqlGenerateRequest) -> SqlGenerateResponse:
    """
    自然语言转 SQL 接口，支持仅生成或生成并执行两种模式。

    处理流程：
        1. 调用 generate_secure_sql() 将自然语言问题转为安全的 SQL
        2. 若 execute=True，调用 execute_sql() 执行生成的 SQL 并返回查询结果
        3. 返回 SQL 语句、参数、使用的模板名及查询结果（如有）

    参数：
        req: SQL 生成请求体
            - question (str): 自然语言问题，必填
            - lognum (str): 用户工号，必填
            - permission_name (str | None): 权限模板名称
            - params (dict): SQL 参数，默认空字典
            - execute (bool): 是否执行生成的 SQL，默认 False
            - max_rows (int | None): 最大返回行数，1-2000，默认使用配置值
            - use_template (bool): 是否优先使用查询模板，默认 False

    返回：
        SqlGenerateResponse: 包含 sql、params、used_template 和 rows（执行时）

    安全注意事项：
        - 生成的 SQL 经过安全校验（仅允许 SELECT，禁止危险关键字和受限表/列）
        - 执行时强制添加 LIMIT 限制返回行数
    """
    result = generate_secure_sql(
        SqlGenRequest(
            question=req.question,
            lognum=req.lognum,
            permission_name=req.permission_name,
            params=req.params,
        ),
        use_template=req.use_template,
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
