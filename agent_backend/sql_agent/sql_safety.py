"""
SQL安全校验模块

文件目的：
    - 验证SQL语句的安全性
    - 防止危险操作（INSERT/UPDATE/DELETE等）
    - 检查受限表和敏感列

核心功能：
    1. 基础SQL验证（只允许SELECT）
    2. 危险关键字检测
    3. 表名提取和验证
    4. 受限表检查
    5. 敏感列检查

主要函数：
    - validate_sql_basic(): 基础SQL验证
    - extract_tables(): 提取SQL中的表名
    - enforce_restricted_tables(): 检查受限表
    - enforce_deny_select_columns(): 检查敏感列
    - normalize_sql(): SQL规范化

安全规则：
    - 只允许SELECT语句
    - 禁止INSERT/UPDATE/DELETE/DROP等
    - 禁止访问受限表
    - 禁止查询敏感列
    - 只允许单条SQL语句

使用场景：
    - SQL生成后的安全检查
    - SQL执行前的验证

相关文件：
    - agent_backend/sql_agent/service.py: SQL生成服务
    - agent_backend/core/schema_models.py: 安全配置
"""
from __future__ import annotations

import re

from agent_backend.core.errors import AppError


_DANGEROUS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|MERGE|CALL)\b",
    flags=re.I,
)


def normalize_sql(sql: str) -> str:
    s = sql.strip()
    if s.endswith(";"):
        s = s[:-1].strip()
    return s


def _strip_string_literals(sql: str) -> str:
    s = re.sub(r"'([^'\\]|\\.)*'", "''", sql)
    s = re.sub(r'"([^"\\]|\\.)*"', '""', s)
    return s


def extract_tables(sql: str) -> dict[str, str | None]:
    """
    从简单 SELECT SQL 中提取出现的表与别名映射。

    说明：
        - 这是一个轻量级抽取器，只覆盖常见的 FROM/JOIN 结构；
        - 不支持复杂子查询/CTE 的完全精确解析（后续可用更强解析器替换）。
    """
    s = _strip_string_literals(sql)
    s = s.replace("`", " ")

    tables: dict[str, str | None] = {}
    stop = {
        "on",
        "where",
        "join",
        "left",
        "right",
        "inner",
        "outer",
        "full",
        "cross",
        "group",
        "order",
        "limit",
        "having",
        "union",
    }

    def _add(table: str, alias: str | None) -> None:
        table = table.strip()
        if not table:
            return
        if table not in tables:
            tables[table] = alias

    for m in re.finditer(r"\b(from|join)\s+([A-Za-z_][A-Za-z0-9_]*)\s*([A-Za-z_][A-Za-z0-9_]*)?", s, flags=re.I):
        table = m.group(2)
        alias = m.group(3)
        if alias and alias.lower() in stop:
            alias = None
        _add(table, alias)
    return tables


def validate_sql_basic(sql: str) -> str:
    s = normalize_sql(sql)
    if not s:
        raise AppError(code="sql_empty", message="SQL 为空")

    if ";" in s:
        raise AppError(code="sql_multiple_statements", message="只允许单条 SQL 语句")

    if not re.match(r"^\s*select\b", s, flags=re.I):
        raise AppError(code="sql_not_select", message="仅允许 SELECT 查询")

    if _DANGEROUS.search(s):
        raise AppError(code="sql_forbidden_keyword", message="SQL 包含危险关键字")

    return s


def enforce_restricted_tables(sql: str, restricted_tables: list[str]) -> None:
    if not restricted_tables:
        return
    tables = set(t.lower() for t in extract_tables(sql).keys())
    for t in restricted_tables:
        if t.lower() in tables:
            raise AppError(
                code="sql_restricted_table",
                message=f"禁止查询受限表: {t}",
                http_status=403,
            )


def enforce_deny_select_columns(sql: str, deny_select_columns: list[str]) -> None:
    if not deny_select_columns:
        return
    s = _strip_string_literals(sql).replace("`", "")
    for col in deny_select_columns:
        if col.replace("`", "") in s:
            raise AppError(
                code="sql_denied_column",
                message=f"禁止返回敏感列: {col}",
                http_status=403,
            )
