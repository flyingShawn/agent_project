from __future__ import annotations

import logging
import re
from typing import Any

from agent_backend.core.config_loader import get_schema_runtime
from agent_backend.llm.clients import OllamaChatClient
from agent_backend.rag_engine.retrieval import RetrievedChunk, search_sql_samples
from agent_backend.sql_agent.patterns import select_query_pattern
from agent_backend.sql_agent.prompt_builder import build_sql_prompt
from agent_backend.sql_agent.sql_safety import (
    enforce_deny_select_columns,
    enforce_restricted_tables,
    validate_sql_basic,
)
from agent_backend.sql_agent.types import SqlGenRequest, SqlGenResult

logger = logging.getLogger(__name__)


def _clean_sql_markdown(sql: str) -> str:
    sql = sql.strip()
    sql = re.sub(r"^```sql\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"^```\s*", "", sql)
    sql = re.sub(r"\s*```$", "", sql)
    sql = re.sub(r"`([^`]+)`", r"\1", sql)
    sql = re.sub(r"\s+IN\s*\(\s*\{allowed_group_ids_sql\}\s*\)", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\{allowed_group_ids_sql\}", "1=1", sql)
    return sql.strip()


def generate_secure_sql(
    req: SqlGenRequest,
    *,
    llm: OllamaChatClient | None = None,
    use_template: bool = False,
) -> SqlGenResult:
    logger.info(f"{'=' * 20 + '【SQL生成流程开始】' + '=' * 20}\n用户问题: {req.question} | 用户ID: {req.lognum} | 使用模板: {use_template}\n{'=' * 80}")
    
    runtime = get_schema_runtime()
    security = runtime.raw.security

    match = select_query_pattern(runtime, req.question) if use_template else None
    params: dict[str, Any] = dict(req.params)

    used_template: str | None = None
    permission_name = req.permission_name

    if match is not None:
        used_template = match.name
        permission_name = permission_name or match.requires_permission
        sql = match.sql
        params.update(match.params)
        logger.info(f"\n【步骤1】匹配到查询模板\n模板名称: {match.name}\n模板SQL: {sql}")
    else:
        logger.info("\n【步骤1】调用LLM生成SQL")

        logger.info("\n【步骤1.1】RAG检索SQL样本...")
        sql_samples: list[RetrievedChunk] | None = None
        try:
            sql_samples = search_sql_samples(req.question)
            if sql_samples:
                logger.info(f"\n  检索到 {len(sql_samples)} 个SQL样本")
                for i, s in enumerate(sql_samples, 1):
                    logger.info(f"  样本{i}: {s.heading} (原始向量分: {s.raw_vector_score:.4f}, 混合分: {s.score:.4f})")
                    # logger.info(f"  样本{i}内容:\n{s.text[:500]}")
            else:
                logger.info("\n  未检索到SQL样本，将使用schema信息直接生成")
        except Exception as e:
            logger.warning(f"\n  SQL样本检索失败: {e}，将使用schema信息直接生成")
            sql_samples = None

        if llm is None:
            llm = OllamaChatClient()
        
        prompt = build_sql_prompt(runtime, req.question, sql_samples=sql_samples)
        logger.info(f"\n【步骤1.2】构建的完整Prompt:\n{prompt}")
        
        messages = [
            {"role": "system", "content": "你是一个专业的数据库查询助手，只返回 SQL 语句，不要包含任何解释或其他内容。"},
            {"role": "user", "content": prompt}
        ]
        
        sql = llm.chat_complete(messages)
        logger.info(f"LLM返回SQL: {sql}")

    sql = _clean_sql_markdown(sql)
    sql = validate_sql_basic(sql)
    logger.info(f"\n【步骤3】安全校验后的SQL:\n{sql}")

    restricted_tables = (security.restricted_tables if security else []) if security else []
    deny_select_columns = (security.deny_select_columns if security else []) if security else []
    enforce_restricted_tables(sql, restricted_tables)
    enforce_deny_select_columns(sql, deny_select_columns)

    sql = validate_sql_basic(sql)
    enforce_deny_select_columns(sql, deny_select_columns)
    
    logger.info(f"{'=' * 80}\n【最终执行的SQL】:\n{sql}\n参数: {params}\n{'=' * 80}")
    
    return SqlGenResult(sql=sql, params=params, used_template=used_template)
