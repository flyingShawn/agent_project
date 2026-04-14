"""
SQL查询工具模块

文件功能：
    定义sql_query Tool，封装SQL生成、安全校验和执行的完整流程。
    作为LangGraph Tool注册，由LLM通过Tool Calling自主调用。

在系统架构中的定位：
    位于Agent工具层，是Agent与数据库交互的唯一入口。
    替代旧架构中sql_agent/service.py的generate_secure_sql + handlers.py的调用逻辑。

主要使用场景：
    - LLM判断用户问题需要数据库查询时，通过Tool Calling调用
    - tool_result_node解析tool_calls后执行

核心函数：
    - sql_query: LangGraph Tool，接收自然语言问题，返回JSON格式查询结果
    - _clean_sql_markdown: 清理LLM生成的SQL中的Markdown格式标记
    - _build_markdown_table: 将查询结果构建为Markdown表格

专有技术说明：
    - SQL生成使用独立的get_sql_llm()（同步、温度0），与Agent LLM分离
    - 安全校验失败返回错误JSON而非抛异常，让LLM有机会修正SQL
    - 强化SQL样本模仿：在prompt末尾追加"必须严格模仿参考SQL样本"指令
    - 单行单列结果（如COUNT）使用简洁格式而非Markdown表格

安全注意事项：
    - validate_sql_basic: 仅允许SELECT，禁止多语句和危险关键字
    - enforce_deny_select_columns: 禁止返回敏感列
    - 已移除enforce_restricted_tables和wrap_with_permission（按需求不再需要）

关联文件：
    - agent_backend/agent/llm.py: get_sql_llm提供SQL生成LLM
    - agent_backend/sql_agent/prompt_builder.py: build_sql_prompt构建SQL生成Prompt
    - agent_backend/sql_agent/sql_safety.py: SQL安全校验函数
    - agent_backend/sql_agent/executor.py: execute_sql执行SQL
    - agent_backend/rag_engine/retrieval.py: search_sql_samples检索SQL样本
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agent_backend.agent.llm import get_sql_llm
from agent_backend.core.config_helper import get_database_url, get_max_rows
from agent_backend.core.config_loader import get_schema_runtime
from agent_backend.core.errors import AppError
from agent_backend.rag_engine.retrieval import search_sql_samples
from agent_backend.sql_agent.executor import execute_sql
from agent_backend.sql_agent.prompt_builder import build_sql_prompt
from agent_backend.sql_agent.sql_safety import (
    enforce_deny_select_columns,
    validate_sql_basic,
)

logger = logging.getLogger(__name__)

MAX_DISPLAY_ROWS = 50


class SqlQueryInput(BaseModel):
    """SQL查询工具入参模型"""
    question: str = Field(description="用户的自然语言问题，用于生成SQL查询")


def _clean_sql_markdown(sql: str) -> str:
    """
    清理LLM生成SQL中的Markdown格式标记。

    LLM有时会将SQL包裹在```sql...```代码块中，此函数去除这些标记。

    参数：
        sql: 原始SQL字符串

    返回：
        str: 清理后的纯SQL字符串
    """
    sql = sql.strip()
    sql = re.sub(r"^```sql\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"^```\s*", "", sql)
    sql = re.sub(r"\s*```$", "", sql)
    sql = re.sub(r"`([^`]+)`", r"\1", sql)
    return sql.strip()


def _build_markdown_table(rows: list[dict]) -> str:
    """
    将查询结果行构建为Markdown表格。

    参数：
        rows: 查询结果行列表，每行为dict（key为列名）

    返回：
        str: Markdown格式表格字符串，超过MAX_DISPLAY_ROWS时截断并提示
    """
    if not rows:
        return ""
    columns = list(rows[0].keys())
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, separator]
    for row in rows[:MAX_DISPLAY_ROWS]:
        cells = []
        for col in columns:
            val = row.get(col, "")
            if val is None:
                val = ""
            val = str(val).replace("|", "\\|").replace("\n", " ").replace("\r", "")
            cells.append(val)
        lines.append("| " + " | ".join(cells) + " |")
    if len(rows) > MAX_DISPLAY_ROWS:
        lines.append(f"| ... | 共 {len(rows)} 条，仅显示前 {MAX_DISPLAY_ROWS} 条 |")
    return "\n".join(lines)


@tool(args_schema=SqlQueryInput)
def sql_query(question: str) -> str:
    """
    查询桌面管理系统的数据库。
    当用户问题涉及设备数量统计、设备信息查询、在线率、告警记录、部门人员等
    需要从数据库获取数据时使用此工具。

    参数：
        question: 用户的自然语言问题，用于生成SQL查询

    返回：
        str: JSON格式字符串，包含sql/rows/row_count/columns/data_table字段；
             校验失败时包含error/hint字段
    """
    logger.info(f"\n[sql_query] 开始处理: {question}")

    try:
        runtime = get_schema_runtime()
        security = runtime.raw.security

        sql_samples = None
        try:
            sql_samples = search_sql_samples(question)
            if sql_samples:
                logger.info(f"\n[sql_query] 检索到 {len(sql_samples)} 个SQL样本")
            else:
                logger.info("\n[sql_query] 未检索到SQL样本")
        except Exception as e:
            logger.warning(f"\n[sql_query] SQL样本检索失败: {e}")

        prompt = build_sql_prompt(runtime, question, sql_samples=sql_samples)
        prompt += "\n\n【最重要】你必须严格模仿参考SQL样本的写法风格，包括：\n"
        prompt += "- 表关联方式（JOIN条件和关联表）\n"
        prompt += "- 别名规则（s_machine用m，s_group用g等）\n"
        prompt += "- 列别名写法（AS \"中文别名\"，中文别名必须用双引号包裹）\n"
        prompt += "- WHERE条件构建方式\n"
        prompt += "- 聚合函数使用方式\n"
        prompt += "如果没有参考SQL样本，请按照最简洁规范的SQL写法生成。\n"

        sql_llm = get_sql_llm()
        messages = [
            {"role": "system", "content": "你是一个专业的数据库查询助手，只返回 SQL 语句，不要包含任何解释或其他内容。"},
            {"role": "user", "content": prompt},
        ]
        from langchain_core.messages import HumanMessage, SystemMessage

        lc_messages = [
            SystemMessage(content=messages[0]["content"]),
            HumanMessage(content=messages[1]["content"]),
        ]
        response = sql_llm.invoke(lc_messages)
        sql = response.content.strip()
        logger.info(f"\n[sql_query] LLM生成SQL: {sql}")

        sql = _clean_sql_markdown(sql)

        try:
            sql = validate_sql_basic(sql)
        except AppError as e:
            logger.warning(f"\n[sql_query] SQL基础校验失败: {e.message}")
            return json.dumps({"error": f"SQL安全校验失败: {e.message}", "hint": "请重新生成SQL，确保只使用SELECT语句且不包含危险关键字"}, ensure_ascii=False)

        deny_select_columns = (security.deny_select_columns if security else []) if security else []
        try:
            enforce_deny_select_columns(sql, deny_select_columns)
        except AppError as e:
            logger.warning(f"\n[sql_query] SQL敏感列校验失败: {e.message}")
            return json.dumps({"error": f"SQL安全校验失败: {e.message}", "hint": "请重新生成SQL，确保不查询敏感列"}, ensure_ascii=False)

        db_url = get_database_url()
        if not db_url:
            return json.dumps({"error": "数据库未配置", "hint": "请检查DATABASE_URL配置"}, ensure_ascii=False)

        exec_result = execute_sql(sql=sql, params={}, database_url=db_url)
        logger.info(f"\n[sql_query] 执行结果: {len(exec_result) if exec_result else 0} 行")

        if not exec_result or len(exec_result) == 0:
            return json.dumps({
                "sql": sql,
                "rows": [],
                "row_count": 0,
                "columns": [],
                "data_table": "",
                "summary_hint": "查询结果为空，请告知用户没有找到匹配的数据，并建议可能的原因",
            }, ensure_ascii=False)

        columns = list(exec_result[0].keys())

        # 这里是保留了之前总结查询结果的逻辑，多行还会表格，如何llm够智能，这个应该交给llm来做最合适。
        if len(exec_result) == 1 and len(exec_result[0]) == 1:
            col_name = list(exec_result[0].keys())[0]
            col_value = list(exec_result[0].values())[0]
            data_table = f"{col_name}: {col_value}"
        else:
            data_table = _build_markdown_table(exec_result)

        return json.dumps({
            "sql": sql,
            "rows": exec_result[:MAX_DISPLAY_ROWS],
            "row_count": len(exec_result),
            "columns": columns,
            "data_table": data_table,
        }, ensure_ascii=False)

    except AppError as e:
        logger.error(f"[sql_query] AppError: {e.message}")
        return json.dumps({"error": e.message, "hint": "请尝试换一种方式提问"}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[sql_query] 异常: {type(e).__name__}: {e}")
        return json.dumps({"error": f"查询失败: {type(e).__name__}: {e}", "hint": "请尝试换一种方式提问"}, ensure_ascii=False)
