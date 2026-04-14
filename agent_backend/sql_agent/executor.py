"""
SQL执行器模块

文件功能：
    执行生成的SQL语句，返回JSON友好的结果，提供安全限制（强制LIMIT）。
    实现区分连接错误和SQL执行错误的差异化重试策略。

在系统架构中的定位：
    位于SQL Agent模块，是SQL语句实际执行的唯一入口。
    由sql_tool.py和sql_agent/service.py调用。

主要使用场景：
    - sql_query工具调用execute_sql执行LLM生成的SQL
    - SQL Agent服务调用execute_sql执行模板匹配SQL

核心函数：
    - execute_sql: 执行SQL并返回结果，区分连接错误和SQL执行错误
    - _ensure_limit: 强制添加LIMIT子句
    - _is_connection_error: 判断是否为连接错误
    - _is_sql_execution_error: 判断是否为SQL执行错误

专有技术说明：
    - 差异化重试策略：
      · 连接错误（网络断开、连接超时等）→ 自动重试，重建连接后重新执行
      · SQL执行错误（语法错误、字段不存在等）→ 不重试，直接抛出SqlExecutionError
        让调用方（sql_tool.py）将错误信息反馈给LLM自检重新生成SQL
    - 使用自定义SqlExecutionError区分SQL执行错误，便于调用方精确捕获

安全注意事项：
    - 强制添加LIMIT（默认500行），防止返回过多数据
    - 使用参数化查询防止SQL注入
    - 连接异常时自动标记无效并重建

关联文件：
    - agent_backend/agent/tools/sql_tool.py: 调用execute_sql，捕获SqlExecutionError反馈LLM
    - agent_backend/sql_agent/service.py: 调用execute_sql
    - agent_backend/core/config_helper.py: get_database_url/get_max_rows
    - agent_backend/core/errors.py: AppError异常类
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from agent_backend.core.config_helper import get_database_url, get_max_rows
from agent_backend.core.errors import AppError
from agent_backend.sql_agent.connection_manager import get_connection_manager

logger = logging.getLogger(__name__)


class SqlExecutionError(Exception):
    """
    SQL执行错误异常，表示SQL语句本身存在问题（语法错误、字段不存在等）。

    与连接错误不同，此类错误不应通过重试解决，
    而应将错误信息反馈给LLM，让LLM自检并重新生成正确的SQL。

    属性：
        original_sql: 原始SQL语句
        db_error: 数据库返回的原始错误信息
    """

    def __init__(self, original_sql: str, db_error: str) -> None:
        self.original_sql = original_sql
        self.db_error = db_error
        super().__init__(f"SQL执行错误: {db_error}")


def _ensure_limit(sql: str, params: dict[str, Any], max_rows: int) -> tuple[str, dict[str, Any]]:
    if re.search(r"\blimit\b", sql, flags=re.I):
        return sql, params
    p = dict(params)
    p["__max_rows"] = max_rows
    return f"{sql}\nLIMIT :__max_rows", p


def _is_connection_error(exception: Exception) -> bool:
    """
    判断异常是否为连接相关错误。

    连接错误特征：网络不可达、连接超时、连接被重置等，
    此类错误可通过重建连接后重试解决。

    参数：
        exception: 异常对象

    返回：
        bool: 是否为连接错误
    """
    error_str = str(exception).lower()
    connection_keywords = [
        'lost connection',
        'connection lost',
        'connection reset',
        'connection refused',
        'broken pipe',
        'errno 10060',
        'errno 10054',
        'disconnected',
        'server has gone away',
        'timed out',
        'timeout',
        'network is unreachable',
        'no route to host',
        'name or service not known',
        'getaddrinfo failed',
    ]
    return any(keyword in error_str for keyword in connection_keywords)


def _is_sql_execution_error(exception: Exception) -> bool:
    """
    判断异常是否为SQL执行错误（语法错误、字段不存在等）。

    SQL执行错误特征：SQL语法不正确、引用了不存在的表或列、
    函数使用错误等，此类错误无法通过重试解决，
    需要LLM根据错误信息自检并重新生成SQL。

    参数：
        exception: 异常对象

    返回：
        bool: 是否为SQL执行错误
    """
    error_str = str(exception).lower()
    sql_error_keywords = [
        'syntax error',
        'unknown column',
        'unknown table',
        "doesn't exist",
        'does not exist',
        'no such column',
        'no such table',
        'invalid column',
        'invalid table',
        'column ambiguity',
        'ambiguous column',
        'duplicate column',
        'wrong number of arguments',
        'invalid use of',
        'operand',
        'truncated incorrect',
        'check the manual',
        'you have an error in your sql',
        'programmingerror',
    ]
    return any(keyword in error_str for keyword in sql_error_keywords)


def execute_sql(
    *,
    sql: str,
    params: dict[str, Any],
    database_url: str | None = None,
    max_rows: int | None = None,
    max_retries: int = 2,
    retry_delay: float = 1.0,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    执行 SQL 并返回 JSON 友好的结果数组。

    差异化重试策略：
        - 连接错误（网络断开、超时等）→ 自动重试，重建连接后重新执行
        - SQL执行错误（语法错误、字段不存在等）→ 不重试，抛出SqlExecutionError，
          由调用方将错误信息反馈给LLM自检重新生成SQL

    参数：
        sql: SQL语句
        params: 查询参数
        database_url: 数据库连接URL（可选）
        max_rows: 最大返回行数（可选）
        max_retries: 连接错误最大重试次数，默认2次
        retry_delay: 重试延迟时间（秒），默认1秒
        session_id: 会话ID（可选，用于连接复用）

    返回：
        list[dict[str, Any]]: 查询结果字典列表

    异常：
        AppError: 数据库未配置或依赖缺失
        SqlExecutionError: SQL执行错误（语法/字段/表不存在等），不重试
        AppError: 连接错误重试耗尽后抛出
    """
    logger.info("\n" + "=" * 20 + "\n【SQL执行流程开始】" + "=" * 20)

    if max_rows is None:
        max_rows = get_max_rows()

    url = database_url or get_database_url()
    if not url:
        logger.error("❌ 未配置 DATABASE_URL")
        raise AppError(code="db_not_configured", message="未配置 DATABASE_URL", http_status=500)

    logger.info(f"\n数据库URL: {url[:30]}...")

    try:
        from sqlalchemy import create_engine, text
    except Exception as e:
        logger.error(f"❌ 缺少依赖：SQLAlchemy - {e}")
        raise AppError(
            code="dependency_missing",
            message="缺少依赖：SQLAlchemy",
            http_status=500,
            details={"reason": str(e)},
        ) from e

    sql2, params2 = _ensure_limit(sql, params, max_rows)

    logger.info(f"\n【执行的SQL】:{sql2}")

    conn_manager = get_connection_manager()
    connection_recreated = False

    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                logger.info(f"\n🔄 第 {attempt} 次重试（连接错误）...")
                time.sleep(retry_delay)

            logger.info("\n正在获取数据库连接...")

            if session_id:
                if connection_recreated:
                    logger.info("\n🔄 强制重新创建连接...")
                    conn_manager.mark_connection_invalid(session_id)

                conn = conn_manager.get_or_create_connection(session_id, url)
                logger.info("\n✅ 数据库连接获取成功 正在执行SQL...")
                result = conn.execute(text(sql2), params2)
                rows = result.fetchall()
                keys = list(result.keys())
            else:
                logger.info("\n⚠️ 未提供会话ID，使用临时连接")
                engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
                with engine.connect() as conn:
                    logger.info("\n✅ 数据库连接成功 正在执行SQL...")
                    result = conn.execute(text(sql2), params2)
                    rows = result.fetchall()
                    keys = list(result.keys())

            logger.info(f"\n✅ SQL执行成功，返回 {len(rows)} 行数据")

            out: list[dict[str, Any]] = []
            for r in rows:
                out.append({k: r[i] for i, k in enumerate(keys)})

            logger.info(f"\n返回数据示例（前3行）:")
            for i, row in enumerate(out[:3]):
                logger.info(f"\n  行{i+1}: {row}")

            logger.info("\n" + "=" * 20 + "\n【SQL执行流程结束】" + "=" * 20)

            return out

        except Exception as e:
            last_exception = e
            logger.warning(f"\n⚠️ 第 {attempt} 次查询失败: {e}")

            if _is_sql_execution_error(e):
                logger.warning("\n🚫 检测到SQL执行错误（语法/字段/表不存在），不重试，反馈给LLM自检")
                raise SqlExecutionError(
                    original_sql=sql2,
                    db_error=str(e),
                ) from e

            if _is_connection_error(e):
                logger.warning("\n🔧 检测到连接异常，标记连接为无效，下次重试将重建连接")
                connection_recreated = True
                if session_id:
                    conn_manager.mark_connection_invalid(session_id)

                if attempt < max_retries:
                    logger.info(f"\n💡 连接错误，将在 {retry_delay} 秒后重试...")
                    continue
                else:
                    logger.error(f"❌ 连接错误已达到最大重试次数 {max_retries}，放弃重试")
            else:
                logger.error(f"❌ 非连接非SQL执行错误，不重试: {type(e).__name__}")
                raise AppError(
                    code="db_query_failed",
                    message=f"数据库查询失败: {type(e).__name__}",
                    http_status=502,
                    details={"reason": str(e), "sql": sql2},
                ) from e

    logger.error(f"❌ 数据库连接失败（重试耗尽）: {last_exception}")
    raise AppError(
        code="db_connection_failed",
        message="数据库连接失败，请检查网络和数据库配置",
        http_status=502,
        details={"reason": str(last_exception)},
    ) from last_exception
