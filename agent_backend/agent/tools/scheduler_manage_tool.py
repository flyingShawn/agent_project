import asyncio
import json
import logging

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Literal

from agent_backend.scheduler import get_scheduler_manager

logger = logging.getLogger(__name__)


class ManageScheduledTaskInput(BaseModel):
    action: Literal["list", "pause", "resume", "delete", "update"] = Field(
        description="操作类型：list(查看任务列表)、pause(暂停)、resume(恢复)、delete(删除)、update(更新SQL)"
    )
    task_id: str | None = Field(default=None, description="任务ID，pause/resume/delete/update时必填")
    sql_template: str | None = Field(default=None, description="新的SQL模板，update时可选")
    description: str | None = Field(default=None, description="更新时的任务描述，update时可选")


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


@tool(args_schema=ManageScheduledTaskInput)
def manage_scheduled_task(
    action: Literal["list", "pause", "resume", "delete", "update"],
    task_id: str | None = None,
    sql_template: str | None = None,
    description: str | None = None,
) -> str:
    """
    管理已有的定时任务。支持查看任务列表、暂停、恢复、删除、更新任务。
    当用户要求"查看定时任务"、"暂停任务"、"删除任务"等管理操作时使用此工具。

    参数：
        action: 操作类型
        task_id: 任务ID（pause/resume/delete/update时必填）
        sql_template: 新SQL模板（update时可选）
        description: 任务描述（update时可选）
    """
    logger.info(f"\n[manage_scheduled_task] action={action}, task_id={task_id}")
    scheduler = get_scheduler_manager()

    if action == "list":
        result = _run_async(scheduler.get_tasks())
        if not result:
            return json.dumps({"message": "当前没有活跃的定时任务"}, ensure_ascii=False)
        return json.dumps({"tasks": result, "total": len(result)}, ensure_ascii=False)

    if not task_id:
        return json.dumps({"error": f"action={action} 时必须提供 task_id"}, ensure_ascii=False)

    if action == "pause":
        result = _run_async(scheduler.pause_task(task_id))
    elif action == "resume":
        result = _run_async(scheduler.resume_task(task_id))
    elif action == "delete":
        result = _run_async(scheduler.delete_task(task_id))
    elif action == "update":
        if sql_template:
            result = _run_async(scheduler.update_task_sql(task_id, sql_template))
        elif description:
            try:
                from agent_backend.llm.factory import get_sql_llm
                from agent_backend.sql_agent.sql_safety import validate_sql_basic
                from agent_backend.sql_agent.prompt_builder import build_sql_prompt
                from agent_backend.core.config import get_schema_runtime
                from langchain_core.messages import SystemMessage, HumanMessage

                runtime = get_schema_runtime()
                prompt = build_sql_prompt(runtime, description)
                sql_llm = get_sql_llm()
                messages = [
                    SystemMessage(content="你是一个专业的数据库查询助手，只返回 SQL 语句，不要包含任何解释或其他内容。"),
                    HumanMessage(content=prompt),
                ]
                response = sql_llm.invoke(messages)
                new_sql = response.content.strip()
                import re
                new_sql = re.sub(r"^```sql\s*", "", new_sql, flags=re.IGNORECASE)
                new_sql = re.sub(r"^```\s*", "", new_sql)
                new_sql = re.sub(r"\s*```$", "", new_sql)
                new_sql = new_sql.strip()

                try:
                    new_sql = validate_sql_basic(new_sql)
                except Exception as e:
                    return json.dumps({"error": f"SQL校验失败: {e}"}, ensure_ascii=False)

                result = _run_async(scheduler.update_task_sql(task_id, new_sql))
            except Exception as e:
                return json.dumps({"error": f"生成SQL失败: {e}"}, ensure_ascii=False)
        else:
            return json.dumps({"error": "update操作需要提供 sql_template 或 description"}, ensure_ascii=False)
    else:
        return json.dumps({"error": f"未知操作: {action}"}, ensure_ascii=False)

    return json.dumps(result, ensure_ascii=False)
