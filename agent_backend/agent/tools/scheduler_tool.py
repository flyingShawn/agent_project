"""
定时任务创建工具模块

文件功能：
    定义 LangChain @tool 装饰的 schedule_task 工具，供 Agent 在对话中
    根据用户需求创建定时任务。支持自动生成SQL模板或使用用户提供的SQL。

在系统架构中的定位：
    位于 Agent 工具层，是 LLM Tool Calling 机制中的一环。
    - 对上：被 agent_node 通过 bind_tools 绑定到 LLM，LLM 自主决策调用
    - 对下：调用 SchedulerManager.add_task() 创建任务，调用 sql_agent 生成/校验SQL

主要使用场景：
    - 用户在对话中说"每隔30分钟统计在线客户端数量"等周期性需求
    - LLM 识别意图后调用此工具创建定时任务

核心函数：
    - schedule_task(): @tool 装饰的定时任务创建工具
    - ScheduleTaskInput: Pydantic 输入模型
    - clean_sql_markdown(): 清理LLM返回SQL中的Markdown标记（来自sql_agent.utils）
    - _run_async(): 在同步工具函数中运行异步协程的桥接器

专有技术说明：
    - 同步/异步桥接：LangChain @tool 函数是同步的，但 SchedulerManager 是异步的，
      通过 _run_async() 使用 ThreadPoolExecutor 桥接
    - SQL自动生成：当用户未提供 sql_template 时，调用 LLM + RAG样本自动生成SQL
    - SQL安全校验：生成/提供的SQL必须通过 validate_sql_basic() 和敏感列校验
    - SQL试执行：校验通过后在数据库上试执行SQL（max_rows=1），验证SQL可执行性

关联文件：
    - agent_backend/scheduler/manager.py: SchedulerManager.add_task() 创建任务
    - agent_backend/sql_agent/sql_safety.py: SQL安全校验
    - agent_backend/sql_agent/executor.py: execute_sql() SQL试执行
    - agent_backend/sql_agent/prompt_builder.py: build_sql_prompt() SQL生成提示词
    - agent_backend/llm/factory.py: get_sql_llm() SQL生成LLM实例
"""
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
from agent_backend.sql_agent.prompt_builder import build_sql_prompt, SQL_SYSTEM_PROMPT
from agent_backend.sql_agent.sql_safety import (
    enforce_deny_select_columns,
    validate_sql_basic,
)
from agent_backend.sql_agent.utils import clean_sql_markdown

logger = logging.getLogger(__name__)


class ScheduleTaskInput(BaseModel):
    """
    schedule_task 工具的输入参数模型。

    字段说明：
        task_name: 任务名称，如"统计在线客户端数量"
        description: 任务的自然语言描述，如"每隔30分钟统计在线客户端数量"
        interval_seconds: 间隔秒数，如1800表示30分钟（与cron_expr二选一）
        cron_expr: cron表达式，如"0 */2 * * *"表示每2小时（与interval_seconds二选一）
        sql_template: 可选的SQL模板，不提供则由LLM自动生成
    """
    task_name: str = Field(description="任务名称，如'统计在线客户端数量'")
    description: str = Field(description="任务的自然语言描述，如'每隔30分钟统计在线客户端数量'")
    interval_seconds: int | None = Field(default=None, description="间隔秒数，如1800表示30分钟")
    cron_expr: str | None = Field(default=None, description="cron表达式，如'0 */2 * * *'表示每2小时")
    sql_template: str | None = Field(default=None, description="可选的SQL模板，不提供则由LLM生成")


def _run_async(coro):
    """
    在同步上下文中运行异步协程的桥接器。

    LangChain @tool 函数是同步的，但 SchedulerManager 的方法都是异步的。
    此函数根据当前事件循环状态选择合适的执行策略：
        - 事件循环未运行：直接 loop.run_until_complete()
        - 事件循环正在运行（如 FastAPI 中）：在新线程中启动新事件循环
        - 无事件循环：asyncio.run()

    参数：
        coro: 异步协程对象

    返回：
        协程的执行结果
    """
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

    返回：
        str: JSON格式的创建结果，包含 task_id, task_name, status, sql_template
             失败时包含 error 字段

    执行流程：
        1. 校验必须提供 interval_seconds 或 cron_expr 之一
        2. 若未提供 sql_template，调用 LLM + RAG样本自动生成SQL
        3. SQL安全校验（validate_sql_basic + 敏感列校验）
        4. SQL试执行验证（max_rows=1，确保SQL可执行）
        5. 调用 SchedulerManager.add_task() 创建任务
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
                SystemMessage(content=SQL_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
            response = sql_llm.invoke(messages)
            sql_template = clean_sql_markdown(response.content.strip())
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
