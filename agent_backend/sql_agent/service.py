from __future__ import annotations

import logging
import re
from typing import Any

from agent_backend.core.config import get_schema_runtime
from agent_backend.llm.clients import OpenAICompatibleClient
from agent_backend.rag_engine.retrieval import RetrievedChunk, search_sql_samples
from agent_backend.sql_agent.patterns import select_query_pattern
from agent_backend.sql_agent.prompt_builder import build_sql_prompt
from agent_backend.sql_agent.sql_safety import (
    enforce_deny_select_columns,
    validate_sql_basic,
)
from agent_backend.sql_agent.types import SqlGenRequest, SqlGenResult
from agent_backend.sql_agent.utils import clean_sql_markdown

logger = logging.getLogger(__name__)


def generate_secure_sql(
    req: SqlGenRequest,
    *,
    llm: OpenAICompatibleClient | None = None,
    use_template: bool = False,
) -> SqlGenResult:
    logger.info(f"\n{'=' * 20}【SQL生成流程开始】{'=' * 20}\n用户问题: {req.question} | 用户ID: {req.lognum} | 使用模板: {use_template}\n{'=' * 80}")

    runtime = get_schema_runtime()
    security = runtime.raw.security

    match = select_query_pattern(runtime, req.question) if use_template else None
    params: dict[str, Any] = dict(req.params)

    used_template: str | None = None

    if match is not None:
        used_template = match.name
        sql = match.sql
        params.update(match.params)
        logger.info(f"\n【步骤1】匹配到查询模板: {match.name}")
    else:
        logger.info("\n【步骤1】调用LLM生成SQL")

        logger.info("\n【步骤1.1】RAG检索SQL样本...")
        sql_samples: list[RetrievedChunk] | None = None
        try:
            sql_samples = search_sql_samples(req.question)
            if sql_samples:
                logger.info(f"\n  检索到 {len(sql_samples)} 个SQL样本")
            else:
                logger.info("\n  未检索到SQL样本，将使用schema信息直接生成")
        except Exception as e:
            logger.warning(f"\n  SQL样本检索失败: {e}，将使用schema信息直接生成")
            sql_samples = None

        if llm is None:
            llm = OpenAICompatibleClient()

        prompt = build_sql_prompt(runtime, req.question, sql_samples=sql_samples)

        messages = [
            {"role": "system", "content": "你是一个专业的数据库查询助手，只返回 SQL 语句，不要包含任何解释或其他内容。"},
            {"role": "user", "content": prompt}
        ]

        sql = llm.chat_complete(messages)
        logger.info(f"\nLLM返回SQL: {sql}")

    sql = clean_sql_markdown(sql)
    sql = validate_sql_basic(sql)
    logger.info(f"\n【步骤3】安全校验后的SQL:\n{sql}")

    deny_select_columns = (security.deny_select_columns if security else []) if security else []
    enforce_deny_select_columns(sql, deny_select_columns)

    sql = validate_sql_basic(sql)
    enforce_deny_select_columns(sql, deny_select_columns)

    logger.info(f"\n{'=' * 80}\n【最终执行的SQL】:\n{sql}\n参数: {params}\n{'=' * 80}")

    return SqlGenResult(sql=sql, params=params, used_template=used_template)
