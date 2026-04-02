"""
SQL执行器模块

文件目的：
    - 执行生成的SQL语句
    - 返回JSON友好的结果
    - 提供安全限制（强制LIMIT）

核心功能：
    1. 连接数据库（使用SQLAlchemy）
    2. 执行SQL查询
    3. 强制添加LIMIT（防止返回过多数据）
    4. 将结果转换为字典列表

主要函数：
    - execute_sql(): 执行SQL并返回结果

执行流程：
    1. 检查DATABASE_URL配置
    2. 确保SQL有LIMIT子句
    3. 创建数据库连接
    4. 执行SQL
    5. 转换结果为字典列表
    6. 返回结果

安全措施：
    - 强制添加LIMIT（默认200行）
    - 使用参数化查询（防止SQL注入）
    - 异常处理和错误包装

使用场景：
    - SQL代理执行查询
    - 数据查询API

相关文件：
    - agent_backend/sql_agent/service.py: SQL生成服务
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from agent_backend.core.config_helper import get_database_url
from agent_backend.core.errors import AppError

logger = logging.getLogger(__name__)


def _ensure_limit(sql: str, params: dict[str, Any], max_rows: int) -> tuple[str, dict[str, Any]]:
    if re.search(r"\blimit\b", sql, flags=re.I):
        return sql, params
    p = dict(params)
    p["__max_rows"] = max_rows
    return f"{sql}\nLIMIT :__max_rows", p


def execute_sql(
    *,
    sql: str,
    params: dict[str, Any],
    database_url: str | None = None,
    max_rows: int = 200,
) -> list[dict[str, Any]]:
    """
    执行 SQL 并返回 JSON 友好的结果数组。

    说明：
        - 该方法仅在配置了 DATABASE_URL 时可用；
        - 为避免误操作，默认强制追加 LIMIT（若 SQL 未显式包含 LIMIT）。
    """
    logger.info("=" * 80)
    logger.info("【SQL执行流程开始】")
    logger.info("=" * 80)
    
    url = database_url or get_database_url()
    if not url:
        logger.error("❌ 未配置 DATABASE_URL")
        raise AppError(code="db_not_configured", message="未配置 DATABASE_URL", http_status=500)

    logger.info(f"数据库URL: {url[:30]}...")

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
    
    logger.info("【执行的SQL】:")
    logger.info(f"\n{sql2}")
    logger.info(f"参数: {params2}")

    try:
        logger.info("正在连接数据库...")
        engine = create_engine(url)
        with engine.connect() as conn:
            logger.info("✅ 数据库连接成功")
            logger.info("正在执行SQL...")
            result = conn.execute(text(sql2), params2)
            rows = result.fetchall()
            keys = list(result.keys())
            logger.info(f"✅ SQL执行成功，返回 {len(rows)} 行数据")
    except Exception as e:
        logger.error(f"❌ 数据库查询失败: {e}")
        raise AppError(
            code="db_query_failed",
            message="数据库查询失败",
            http_status=502,
            details={"reason": str(e)},
        ) from e

    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({k: r[i] for i, k in enumerate(keys)})
    
    logger.info(f"返回数据示例（前3行）:")
    for i, row in enumerate(out[:3]):
        logger.info(f"  行{i+1}: {row}")
    
    logger.info("=" * 80)
    logger.info("【SQL执行流程结束】")
    logger.info("=" * 80)
    
    return out
