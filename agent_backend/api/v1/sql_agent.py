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
    question: str = Field(min_length=1)
    lognum: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    execute: bool = False
    max_rows: int | None = Field(default=None, ge=1, le=2000)


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
