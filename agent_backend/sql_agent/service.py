"""
SQL生成服务模块

文件功能：
    提供SQL生成的完整业务流程，从自然语言问题到安全校验通过的SQL语句。
    封装RAG样本检索、Prompt构建、LLM调用和安全校验的串联逻辑。

在系统架构中的定位：
    位于SQL Agent模块的服务层，是旧架构SQL生成流程的保留入口。
    当前主要被 api/v1/sql_agent.py 的REST API直接调用。
    新架构中 sql_tool.py 已自行实现相同流程，不依赖此模块。

主要使用场景：
    - REST API /api/v1/sql/generate 直接调用生成SQL
    - 需要独立于Agent流程的SQL生成能力

核心函数：
    - generate_secure_sql: SQL生成主函数，串联检索→构建→生成→校验流程

专有技术说明：
    - 与 sql_tool.py 的 sql_query 工具实现逻辑一致，但使用不同的LLM客户端
    - 本模块使用 OpenAICompatibleClient（自研HTTP客户端），sql_tool 使用 LangChain ChatOpenAI
    - 安全校验执行两次（validate_sql_basic + enforce_deny_select_columns），
      第二次为冗余保障，确保SQL未被篡改

关联文件：
    - agent_backend/agent/tools/sql_tool.py: 新架构SQL生成工具（LangChain Tool）
    - agent_backend/sql_agent/prompt_builder.py: build_sql_prompt 构建提示词
    - agent_backend/sql_agent/sql_safety.py: SQL安全校验
    - agent_backend/sql_agent/types.py: SqlGenRequest/SqlGenResult 数据类型
    - agent_backend/api/v1/sql_agent.py: REST API 调用入口
"""
from __future__ import annotations

import logging
import re
from typing import Any

from agent_backend.core.config import get_schema_runtime
from agent_backend.llm.clients import OpenAICompatibleClient
from agent_backend.rag_engine.retrieval import RetrievedChunk, search_sql_samples
from agent_backend.sql_agent.prompt_builder import build_sql_prompt, SQL_SYSTEM_PROMPT
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
) -> SqlGenResult:
    """
    SQL生成主函数，从自然语言问题生成安全校验通过的SQL。

    执行流程：
        1. 加载Schema运行时配置
        2. RAG检索SQL样本（可选，检索失败时降级为纯Schema生成）
        3. 构建SQL生成Prompt（含Schema、同义词、样本）
        4. 调用LLM生成SQL
        5. 清理Markdown格式标记
        6. SQL基础安全校验（validate_sql_basic）
        7. 敏感列校验（enforce_deny_select_columns）
        8. 二次校验（冗余保障）

    参数：
        req: SQL生成请求，包含question（自然语言问题）、lognum（用户工号）、params（查询参数）
        llm: LLM客户端实例，为None时自动创建OpenAICompatibleClient

    返回：
        SqlGenResult: 生成结果，包含sql（校验通过的SQL）、params（查询参数）、
                      used_template（使用的模板，当前始终为None）

    异常：
        AppError: SQL安全校验失败时抛出（非SELECT语句、危险关键字、敏感列等）
    """
    logger.info(f"\n{'=' * 20}【SQL生成流程开始】{'=' * 20}\n用户问题: {req.question} | 用户ID: {req.lognum}\n{'=' * 80}")

    runtime = get_schema_runtime()
    security = runtime.raw.security

    params: dict[str, Any] = dict(req.params)

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
        {"role": "system", "content": SQL_SYSTEM_PROMPT},
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

    return SqlGenResult(sql=sql, params=params, used_template=None)
