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
    5. 自动重试机制（支持连接异常重连）

主要函数：
    - execute_sql(): 执行SQL并返回结果

执行流程：
    1. 检查DATABASE_URL配置
    2. 确保SQL有LIMIT子句
    3. 获取或创建数据库连接
    4. 执行SQL（失败时自动重试，连接异常时会重建连接）
    5. 转换结果为字典列表
    6. 返回结果

安全措施：
    - 强制添加LIMIT（默认200行）
    - 使用参数化查询（防止SQL注入）
    - 异常处理和错误包装
    - 数据库查询失败自动重试（最多2次）
    - 连接异常时自动重建连接

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
import time
from typing import Any

from agent_backend.core.config_helper import get_database_url, get_max_rows
from agent_backend.core.errors import AppError
from agent_backend.sql_agent.connection_manager import get_connection_manager

logger = logging.getLogger(__name__)


def _ensure_limit(sql: str, params: dict[str, Any], max_rows: int) -> tuple[str, dict[str, Any]]:
    if re.search(r"\blimit\b", sql, flags=re.I):
        return sql, params
    p = dict(params)
    p["__max_rows"] = max_rows
    return f"{sql}\nLIMIT :__max_rows", p


def _is_connection_error(exception: Exception) -> bool:
    """
    判断异常是否为连接相关错误
    
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
        'operationalerror',
        'disconnected',
        'server has gone away'
    ]
    return any(keyword in error_str for keyword in connection_keywords)


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

    说明：
        - 该方法仅在配置了 DATABASE_URL 时可用；
        - 为避免误操作，默认强制追加 LIMIT（若 SQL 未显式包含 LIMIT）；
        - 数据库查询失败时会自动重试（最多 max_retries 次）；
        - 检测到连接异常时会自动重建连接后重试。

    参数：
        sql: SQL语句
        params: 查询参数
        database_url: 数据库连接URL（可选）
        max_rows: 最大返回行数（可选）
        max_retries: 最大重试次数，默认2次
        retry_delay: 重试延迟时间（秒），默认1秒
        session_id: 会话ID（可选，用于连接复用）
    """
  
    logger.info("=" * 20 +"\n【SQL执行流程开始】" + "=" * 20)
    
    if max_rows is None:
        max_rows = get_max_rows()
    
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
    
    logger.info(f"\n【执行的SQL】:{sql2}")
 
    conn_manager = get_connection_manager()
    connection_recreated = False
    
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                logger.info(f"🔄 第 {attempt} 次重试...")
                time.sleep(retry_delay)
            
            logger.info("正在获取数据库连接...")
            
            if session_id:
                if connection_recreated:
                    logger.info("🔄 强制重新创建连接...")
                    conn_manager.mark_connection_invalid(session_id)
                
                conn = conn_manager.get_or_create_connection(session_id, url)
                logger.info("✅ 数据库连接获取成功 正在执行SQL...")
                result = conn.execute(text(sql2), params2)
                rows = result.fetchall()
                keys = list(result.keys())
            else:
                logger.info("⚠️ 未提供会话ID，使用临时连接")
                engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
                with engine.connect() as conn:
                    logger.info("✅ 数据库连接成功 正在执行SQL...")
                    result = conn.execute(text(sql2), params2)
                    rows = result.fetchall()
                    keys = list(result.keys())
            
            logger.info(f"✅ SQL执行成功，返回 {len(rows)} 行数据")
            
            out: list[dict[str, Any]] = []
            for r in rows:
                out.append({k: r[i] for i, k in enumerate(keys)})
            
            logger.info(f"返回数据示例（前3行）:")
            for i, row in enumerate(out[:3]):
                logger.info(f"  行{i+1}: {row}")
            
            logger.info("=" * 20 +"\n【SQL执行流程结束】" + "=" * 20)
            
            return out
                
        except Exception as e:
            last_exception = e
            logger.warning(f"⚠️ 第 {attempt} 次查询失败: {e}")
            
            if session_id and _is_connection_error(e):
                logger.warning("🔧 检测到连接异常，标记连接为无效，下次重试将重建连接")
                connection_recreated = True
                conn_manager.mark_connection_invalid(session_id)
            
            if attempt < max_retries:
                logger.info(f"💡 将在 {retry_delay} 秒后重试...")
            else:
                logger.error(f"❌ 已达到最大重试次数 {max_retries}，放弃重试")
    
    # 所有重试都失败了
    logger.error(f"❌ 数据库查询失败: {last_exception}")
    raise AppError(
        code="db_query_failed",
        message="数据库查询失败",
        http_status=502,
        details={"reason": str(last_exception)},
    ) from last_exception
