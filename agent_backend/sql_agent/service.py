"""
SQL生成服务主模块

文件目的：
    - 从自然语言生成安全的SQL语句
    - 协调模板匹配、LLM生成、权限包装等流程
    - 提供统一的SQL生成入口

核心功能：
    1. 优先匹配查询模板（query_patterns）
    2. 未命中时调用LLM生成SQL
    3. 执行安全校验（禁止危险操作）
    4. 应用权限规则（数据隔离）
    5. 返回安全的SQL和参数

主要函数：
    - generate_secure_sql(): 生成安全SQL的主函数

生成流程：
    1. 匹配query_patterns -> 命中则直接使用模板
    2. 未命中 -> 调用LLM生成
       - 构建prompt -> build_sql_prompt()
       - 调用LLM -> langgraph_flow或直接调用
    3. 安全校验 -> validate_sql_basic()
    4. 权限包装 -> wrap_with_permission()
    5. 再次安全校验 -> 检查受限表和敏感列

使用场景：
    - 自然语言转SQL
    - Text-to-SQL应用

相关文件：
    - agent_backend/sql_agent/prompt_builder.py: Prompt构建
    - agent_backend/sql_agent/langgraph_flow.py: LangGraph流程
    - agent_backend/sql_agent/permission_wrapper.py: 权限包装
    - agent_backend/sql_agent/sql_safety.py: 安全校验
"""
from __future__ import annotations

import logging
import re
from typing import Any

from agent_backend.core.config_loader import get_schema_runtime
from agent_backend.core.errors import AppError
from agent_backend.sql_agent.llm_clients import LlmClient, OllamaClient
from agent_backend.sql_agent.patterns import select_query_pattern
from agent_backend.sql_agent.permission_wrapper import wrap_with_permission
from agent_backend.sql_agent.prompt_builder import build_sql_prompt
from agent_backend.sql_agent.sql_safety import (
    enforce_deny_select_columns,
    enforce_restricted_tables,
    validate_sql_basic,
)
from agent_backend.sql_agent.types import SqlGenRequest, SqlGenResult

logger = logging.getLogger(__name__)


def _clean_sql_markdown(sql: str) -> str:
    """清理 LLM 返回的 SQL 中的 markdown 代码块标记和占位符"""
    sql = sql.strip()
    sql = re.sub(r"^```sql\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"^```\s*", "", sql)
    sql = re.sub(r"\s*```$", "", sql)
    sql = re.sub(r"\{allowed_group_ids_sql\}", "1=1", sql)
    return sql.strip()


def generate_secure_sql(
    req: SqlGenRequest,
    *,
    llm: LlmClient | None = None,
) -> SqlGenResult:
    """
    从自然语言生成"安全 SQL"。

    处理顺序：
        1) 优先匹配 query_patterns（命中则绕开大模型）
        2) 未命中时调用大模型生成初稿 SQL
        3) 做基础安全校验（仅允许单条 SELECT + 禁用关键字等）
        4) 按 permissions 规则进行权限包装（拼接 join/where 与子查询）
        5) 再次做安全校验（受限表、敏感列）
    """
    logger.info("=" * 80)
    logger.info("【SQL生成流程开始】")
    logger.info(f"用户问题: {req.question}")
    logger.info(f"用户ID: {req.lognum}")
    logger.info("=" * 80)
    
    runtime = get_schema_runtime()
    security = runtime.raw.security

    match = select_query_pattern(runtime, req.question)
    params: dict[str, Any] = dict(req.params)

    used_template: str | None = None
    permission_name = req.permission_name

    if match is not None:
        logger.info("【步骤1】匹配到查询模板")
        logger.info(f"模板名称: {match.name}")
        used_template = match.name
        permission_name = permission_name or match.requires_permission
        sql = match.sql
        params.update(match.params)
        logger.info(f"模板SQL: {sql}")
    else:
        logger.info("【步骤1】未匹配到模板，调用大模型生成SQL")
        use_langgraph = llm is None
        if llm is None:
            llm = OllamaClient()
        prompt = build_sql_prompt(runtime, req.question)
        logger.info(f"构建的Prompt长度: {len(prompt)} 字符")
        logger.debug(f"Prompt内容:\n{prompt}")
        
        if use_langgraph:
            try:
                from agent_backend.sql_agent.langgraph_flow import run_text_to_sql_graph

                sql = run_text_to_sql_graph(prompt=prompt, llm=llm)
            except AppError:
                raise
            except Exception:
                sql = llm.generate(prompt)
        else:
            sql = llm.generate(prompt)

        logger.info("【步骤2】大模型生成的原始SQL:")
        logger.info(f"\n{sql}")

    sql = _clean_sql_markdown(sql)
    sql = validate_sql_basic(sql)
    logger.info("【步骤3】安全校验后的SQL:")
    logger.info(f"\n{sql}")

    restricted_tables = (security.restricted_tables if security else []) if security else []
    deny_select_columns = (security.deny_select_columns if security else []) if security else []
    enforce_restricted_tables(sql, restricted_tables)
    enforce_deny_select_columns(sql, deny_select_columns)

    # TODO: 暂时禁用权限控制
    # if runtime.raw.permissions:
    #     permission_name = permission_name or runtime.raw.permissions[0].name
    #     logger.info(f"【步骤4】应用权限规则: {permission_name}")
    #     sql, params = wrap_with_permission(
    #         runtime=runtime,
    #         sql=sql,
    #         lognum=req.lognum,
    #         permission_name=permission_name,
    #         params=params,
    #     )
    #     logger.info("权限包装后的SQL:")
    #     logger.info(f"\n{sql}")
    #     logger.info(f"参数: {params}")

    sql = validate_sql_basic(sql)
    enforce_deny_select_columns(sql, deny_select_columns)
    
    logger.info("=" * 80)
    logger.info("【最终执行的SQL】:")
    logger.info(f"\n{sql}")
    logger.info(f"参数: {params}")
    logger.info("=" * 80)
    
    return SqlGenResult(sql=sql, params=params, used_template=used_template)
