"""
SQL安全校验模块

文件功能：
    提供SQL语句的安全校验功能，确保仅允许SELECT查询，
    禁止危险关键字、多语句执行和敏感列查询。

在系统架构中的定位：
    位于SQL Agent模块，是SQL生成和执行流程中的安全防线。
    在LLM生成SQL后、执行前进行校验，阻止不安全的SQL到达数据库。

主要使用场景：
    - sql_query工具在LLM生成SQL后调用validate_sql_basic进行基础校验
    - sql_query工具调用enforce_deny_select_columns检查敏感列
    - sql_agent/service.py的generate_secure_sql流程中调用

核心函数：
    - validate_sql_basic: SQL基础校验，检查SELECT-only/危险关键字/多语句
    - enforce_deny_select_columns: 敏感列校验，禁止查询密码等敏感字段

专有技术说明：
    - 使用正则表达式匹配危险关键字（INSERT/UPDATE/DELETE/DROP等13种）
    - 多语句检测通过分号后跟非空白字符的模式识别
    - 敏感列校验使用大小写不敏感匹配

安全注意事项：
    - 所有校验失败抛出AppError而非返回错误字符串，确保异常被全局处理器捕获
    - 校验规则为白名单模式：仅允许SELECT，其他一律拒绝
    - 敏感列列表由schema_metadata.yaml的security.deny_select_columns配置

关联文件：
    - agent_backend/core/errors.py: AppError异常类
    - agent_backend/agent/tools/sql_tool.py: 调用validate_sql_basic和enforce_deny_select_columns
    - agent_backend/sql_agent/service.py: 调用validate_sql_basic和enforce_deny_select_columns
    - agent_backend/configs/schema_metadata.yaml: 敏感列配置
"""
from __future__ import annotations

import re

from agent_backend.core.errors import AppError

_DANGEROUS_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|GRANT|REVOKE|EXEC|EXECUTE|CALL|LOAD|COPY|BULK)\b",
    re.IGNORECASE,
)

_MULTI_STATEMENT = re.compile(r";\s*\S")


def validate_sql_basic(sql: str) -> str:
    """
    SQL基础安全校验，确保SQL语句符合安全规则。

    校验规则（按顺序执行，任一失败即抛出AppError）：
        1. SQL不能为空
        2. 必须以SELECT开头（仅允许SELECT查询）
        3. 不能包含危险关键字（INSERT/UPDATE/DELETE/DROP等13种）
        4. 不能包含多语句（分号后跟非空白字符）

    参数：
        sql: 待校验的SQL字符串

    返回：
        str: 校验通过后的SQL字符串（已去除首尾空白）

    异常：
        AppError: 校验失败时抛出，包含具体错误代码和消息
            - sql_empty: SQL为空
            - sql_not_select: 非SELECT语句
            - sql_dangerous_keyword: 包含危险关键字
            - sql_multi_statement: 包含多语句
    """
    sql = sql.strip()
    if not sql:
        raise AppError(code="sql_empty", message="SQL语句为空", http_status=400)

    if not re.match(r"^(\s*SELECT\s)", sql, re.IGNORECASE):
        raise AppError(
            code="sql_not_select",
            message="仅允许SELECT查询，禁止INSERT/UPDATE/DELETE/DROP等操作",
            http_status=400,
        )

    if _DANGEROUS_KEYWORDS.search(sql):
        raise AppError(
            code="sql_dangerous_keyword",
            message="SQL包含危险关键字，仅允许SELECT语句",
            http_status=400,
        )

    if _MULTI_STATEMENT.search(sql):
        raise AppError(
            code="sql_multi_statement",
            message="禁止多语句执行",
            http_status=400,
        )

    return sql


def enforce_deny_select_columns(sql: str, deny_columns: list[str]) -> None:
    """
    敏感列校验，禁止SQL查询中包含配置的敏感列。

    对SQL进行大小写不敏感匹配，检查是否包含deny_columns中的任何列名。
    敏感列列表由schema_metadata.yaml的security.deny_select_columns配置，
    如admininfo.PassWord1、s_user.UserPwd等。

    参数：
        sql: 待校验的SQL字符串
        deny_columns: 禁止查询的列名列表，格式为"表名.列名"

    返回：
        None: 校验通过无返回值

    异常：
        AppError: 包含敏感列时抛出，code为sql_deny_column

    安全注意事项：
        - 使用大小写不敏感匹配，防止通过大小写绕过
        - deny_columns为空列表时直接返回，不做校验
    """
    if not deny_columns:
        return
    sql_upper = sql.upper()
    for col in deny_columns:
        if col.upper() in sql_upper:
            raise AppError(
                code="sql_deny_column",
                message=f"SQL包含敏感列: {col}，禁止查询",
                http_status=400,
            )
