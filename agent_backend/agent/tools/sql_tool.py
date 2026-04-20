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
    - clean_sql_markdown: 清理LLM生成的SQL中的Markdown格式标记（来自sql_agent.utils）
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
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent_backend.llm.factory import get_sql_llm
from agent_backend.core.config import (
    get_database_url,
    get_schema_runtime,
    get_sql_log_full_prompt,
)
from agent_backend.core.errors import AppError
from agent_backend.rag_engine.retrieval import search_sql_samples
from agent_backend.sql_agent.executor import execute_sql, SqlExecutionError
from agent_backend.sql_agent.prompt_builder import (
    SQL_SYSTEM_PROMPT,
    SqlPromptBundle,
    build_sql_prompt_bundle,
)
from agent_backend.sql_agent.sql_safety import (
    enforce_deny_select_columns,
    validate_sql_basic,
)
from agent_backend.sql_agent.utils import clean_sql_markdown

logger = logging.getLogger(__name__)

MAX_DISPLAY_ROWS = 50


class _SqlJsonEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, datetime):
            return o.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(o, date):
            return o.strftime("%Y-%m-%d")
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _sanitize_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if isinstance(v, datetime):
                v = v.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(v, date):
                v = v.strftime("%Y-%m-%d")
            elif isinstance(v, Decimal):
                v = float(v)
            clean[k] = v
        out.append(clean)
    return out


class SqlQueryInput(BaseModel):
    """SQL查询工具入参模型"""
    question: str = Field(
        description=(
            "用户的自然语言问题，不是SQL语句。"
            "例如：查看客户端在线状态。"
            "不要传 SELECT * FROM ... 这样的SQL。"
        )
    )


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


def _summarize_sample_text(text: str, max_len: int = 160) -> str:
    normalized = " ".join(text.replace("\n", " ").split())
    if len(normalized) <= max_len:
        return normalized
    return normalized[:max_len] + "..."


def _log_sql_samples(sql_samples: list | None) -> None:
    if not sql_samples:
        logger.info("\n[sql_query] 【SQL样本】未命中，将回退到Schema信息直接生成SQL")
        return

    logger.info(f"\n[sql_query] 【SQL样本】命中 {len(sql_samples)} 个")
    for index, sample in enumerate(sql_samples, start=1):
        source = sample.heading or sample.source_path or "unknown"
        chunk_index = ""
        if isinstance(sample.metadata, dict):
            chunk_index = sample.metadata.get("chunk_index", "")
        has_sql_block = "是" if "```sql" in sample.text.lower() else "否"
        text_len = len(sample.text or "")
        logger.info(
            "[sql_query] 【SQL样本】%s. 来源=%s | chunk_index=%s | text_len=%s | has_sql_block=%s | score=%.4f | 摘要=%s",
            index,
            source,
            chunk_index if chunk_index != "" else "-",
            text_len,
            has_sql_block,
            sample.score,
            _summarize_sample_text(sample.text),
        )


def _log_prompt_bundle(bundle: SqlPromptBundle) -> None:
    sample_tables = ", ".join(bundle.sample_tables) if bundle.sample_tables else "无"
    fallback_desc = "否"
    if bundle.fallback_used:
        fallback_desc = "是"
        if bundle.fallback_reason:
            fallback_desc += f"（{bundle.fallback_reason}）"

    logger.info(
        "\n[sql_query] 【Schema裁剪】样本相关表=%s | 最终表数=%s | 最终列数=%s | 回退=%s",
        sample_tables,
        len(bundle.selected_tables),
        bundle.total_columns,
        fallback_desc,
    )

    if bundle.selected_columns_by_table:
        detail_parts = []
        for table_name, column_names in bundle.selected_columns_by_table.items():
            preview = ", ".join(column_names[:10])
            more = "" if len(column_names) <= 10 else f" ...(+{len(column_names) - 10})"
            detail_parts.append(f"{table_name}[{len(column_names)}]: {preview}{more}")
        logger.info("\n[sql_query] 【Schema裁剪详情】%s", " | ".join(detail_parts))

    logger.info(
        "\n[sql_query] 【Prompt摘要】长度=%s字符 | 表数=%s | 列数=%s | 同义词=%s | 样本=%s",
        len(bundle.prompt),
        len(bundle.selected_tables),
        bundle.total_columns,
        bundle.synonym_count,
        bundle.sample_count,
    )

    if get_sql_log_full_prompt():
        logger.info("\n[sql_query] 【完整Prompt】\n%s", bundle.prompt)


@tool(args_schema=SqlQueryInput)
def sql_query(question: str) -> str:
    """
    查询桌面管理系统的数据库。
    当用户问题涉及设备数量统计、设备信息查询、在线率、告警记录、部门人员、
    操作记录、远程操作记录、登录日志、任何"记录"或"日志"类查询等
    需要从数据库获取数据时使用此工具。
    只接受自然语言问题，不接受SQL语句本身。
    正确示例：{"question": "查看客户端在线状态"}
    错误示例：{"sql": "SELECT * FROM onlineinfo"}

    参数：
        question: 用户的自然语言问题，用于生成SQL查询，不是SQL语句

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
            _log_sql_samples(sql_samples)
        except Exception as e:
            logger.warning(f"\n[sql_query] SQL样本检索失败: {e}")

        prompt_bundle = build_sql_prompt_bundle(runtime, question, sql_samples=sql_samples)
        _log_prompt_bundle(prompt_bundle)
        prompt = prompt_bundle.prompt

        sql_llm = get_sql_llm()
        messages = [
            {"role": "system", "content": SQL_SYSTEM_PROMPT},
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

        sql = clean_sql_markdown(sql)

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

        try:
            exec_result = execute_sql(sql=sql, params={}, database_url=db_url)
        except SqlExecutionError as e:
            logger.warning(f"\n[sql_query] SQL执行错误，通知LLM自检: {e.db_error}")
            return json.dumps({
                "error": f"SQL执行失败，数据库返回错误: {e.db_error}",
                "failed_sql": e.original_sql,
                "hint": "你生成的SQL有语法错误或引用了不存在的字段/表，请根据数据库错误信息自检，修正SQL后重新生成。注意检查：1)表名和列名是否正确 2)SQL语法是否正确 3)JOIN条件是否完整",
            }, ensure_ascii=False)

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

        sanitized = _sanitize_rows(exec_result)

        # 请不要删除基础注释，旧方法留作纪念的
        # if len(exec_result) == 1 and len(exec_result[0]) == 1:
        #     col_name = list(exec_result[0].keys())[0]
        #     col_value = list(exec_result[0].values())[0]
        #     if isinstance(col_value, (datetime, date)):
        #         col_value = col_value.strftime("%Y-%m-%d %H:%M:%S") if isinstance(col_value, datetime) else col_value.strftime("%Y-%m-%d")
        #     elif isinstance(col_value, Decimal):
        #         col_value = float(col_value)
        #     data_table = f"{col_name}: {col_value}"
        # else:
        #     data_table = _build_markdown_table(sanitized)
        
        data_table = ""
        result_dict = {
            "sql": sql,
            "rows": sanitized[:MAX_DISPLAY_ROWS],
            "row_count": len(exec_result),
            "columns": columns,
            "data_table": data_table,
        }

        if len(exec_result) > 1 and columns:
            try:
                from agent_backend.agent.tools.export_tool import export_data
                export_json = json.dumps({"columns": columns, "rows": sanitized[:MAX_DISPLAY_ROWS]}, ensure_ascii=False, cls=_SqlJsonEncoder)
                export_result_str = export_data.invoke({
                    "data": export_json,
                    "filename": "query_result",
                    "format": "xlsx",
                })
                export_parsed = json.loads(export_result_str)
                if "download_url" in export_parsed:
                    result_dict["download_url"] = export_parsed["download_url"]
                    result_dict["download_filename"] = export_parsed.get("filename", "")
                    logger.info(f"\n[sql_query] 自动导出成功: {export_parsed.get('filename')}")
            except Exception as export_err:
                logger.warning(f"\n[sql_query] 自动导出失败: {export_err}")

        return json.dumps(result_dict, ensure_ascii=False, cls=_SqlJsonEncoder)

    except AppError as e:
        logger.error(f"[sql_query] AppError: {e.message}")
        return json.dumps({"error": e.message, "hint": "请尝试换一种方式提问"}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[sql_query] 异常: {type(e).__name__}: {e}")
        return json.dumps({"error": f"查询失败: {type(e).__name__}: {e}", "hint": "请尝试换一种方式提问"}, ensure_ascii=False)
