import asyncio
import json
import logging
import re

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent_backend.core.config import get_database_url, get_schema_runtime
from agent_backend.llm.factory import get_sql_llm
from agent_backend.rag_engine.retrieval import search_sql_samples
from agent_backend.scheduler import get_scheduler_manager
from agent_backend.sql_agent.executor import execute_sql, SqlExecutionError
from agent_backend.sql_agent.prompt_builder import build_sql_prompt
from agent_backend.sql_agent.sql_safety import (
    enforce_deny_select_columns,
    validate_sql_basic,
)

logger = logging.getLogger(__name__)


class ScheduleTaskInput(BaseModel):
    task_name: str = Field(description="任务名称，如'统计在线客户端数量'")
    description: str = Field(description="任务的自然语言描述，如'每隔30分钟统计在线客户端数量'")
    interval_seconds: int | None = Field(default=None, description="间隔秒数，如1800表示30分钟")
    cron_expr: str | None = Field(default=None, description="cron表达式，如'0 */2 * * *'表示每2小时")
    sql_template: str | None = Field(default=None, description="可选的SQL模板，不提供则由LLM生成")


def _clean_sql_markdown(sql: str) -> str:
    sql = sql.strip()
    sql = re.sub(r"^```sql\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"^```\s*", "", sql)
    sql = re.sub(r"\s*```$", "", sql)
    sql = re.sub(r"`([^`]+)`", r"\1", sql)
    return sql.strip()


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@tool(args_schema=ScheduleTaskInput)
def schedule_task(
    task_name: str,
    description: str,
    interval_seconds: int | None = None,
    cron_expr: str | None = None,
    sql_template: str | None = None,
) -> str:
    """
    创建定时任务。当用户要求"每隔N分钟/小时"、"定时"、"定期"执行某个查询或统计时使用此工具。
    例如："每隔30分钟记录在线客户端数量"、"每天统计告警数量"。

    参数：
        task_name: 任务名称
        description: 任务描述
        interval_seconds: 间隔秒数（与cron_expr二选一）
        cron_expr: cron表达式（与interval_seconds二选一）
        sql_template: 可选SQL模板，不提供则自动生成
    """
    logger.info(f"\n[schedule_task] 创建任务: {task_name}, 描述: {description}")

    if not interval_seconds and not cron_expr:
        return json.dumps({"error": "必须提供 interval_seconds 或 cron_expr 之一"}, ensure_ascii=False)

    task_type = "interval" if interval_seconds else "cron"
    task_config = {}
    if task_type == "interval":
        task_config["interval_seconds"] = interval_seconds
    else:
        task_config["cron_expr"] = cron_expr

    if not sql_template:
        logger.info("\n[schedule_task] 未提供SQL模板，调用LLM生成...")
        try:
            runtime = get_schema_runtime()

            sql_samples = None
            try:
                sql_samples = search_sql_samples(description)
            except Exception:
                pass

            prompt = build_sql_prompt(runtime, description, sql_samples=sql_samples)
            sql_llm = get_sql_llm()
            from langchain_core.messages import SystemMessage, HumanMessage
            messages = [
                SystemMessage(content="你是一个专业的数据库查询助手，只返回 SQL 语句，不要包含任何解释或其他内容。"),
                HumanMessage(content=prompt),
            ]
            response = sql_llm.invoke(messages)
            sql_template = _clean_sql_markdown(response.content.strip())
            logger.info(f"\n[schedule_task] LLM生成SQL: {sql_template}")
        except Exception as e:
            logger.error(f"\n[schedule_task] LLM生成SQL失败: {e}")
            return json.dumps({"error": f"生成SQL失败: {e}"}, ensure_ascii=False)

    try:
        sql_template = validate_sql_basic(sql_template)
    except Exception as e:
        return json.dumps({"error": f"SQL安全校验失败: {e}"}, ensure_ascii=False)

    try:
        runtime = get_schema_runtime()
        security = runtime.raw.security
        deny_select_columns = (security.deny_select_columns if security else []) if security else []
        enforce_deny_select_columns(sql_template, deny_select_columns)
    except Exception as e:
        return json.dumps({"error": f"SQL敏感列校验失败: {e}"}, ensure_ascii=False)

    db_url = get_database_url()
    if db_url:
        try:
            execute_sql(sql=sql_template, params={}, database_url=db_url, max_rows=1)
            logger.info("\n[schedule_task] SQL试执行验证通过")
        except SqlExecutionError as e:
            return json.dumps({
                "error": f"SQL试执行失败: {e.db_error}",
                "hint": "生成的SQL有误，请调整描述后重试",
            }, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"\n[schedule_task] SQL试执行异常（非阻塞）: {e}")

    try:
        scheduler = get_scheduler_manager()
        result = _run_async(scheduler.add_task(
            task_name=task_name,
            task_type=task_type,
            task_config=task_config,
            sql_template=sql_template,
            description=description,
            created_by="chat",
        ))
    except Exception as e:
        logger.error(f"\n[schedule_task] 创建任务失败: {e}")
        return json.dumps({"error": f"创建任务失败: {e}"}, ensure_ascii=False)

    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    result["sql_template"] = sql_template
    return json.dumps(result, ensure_ascii=False)
