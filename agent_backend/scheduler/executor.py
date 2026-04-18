import asyncio
import json
import logging
import time
from typing import Any

from sqlalchemy import select

from agent_backend.db.chat_history import async_session
from agent_backend.db.models import AgentTask, AgentTaskResult
from agent_backend.sql_agent.executor import execute_sql

logger = logging.getLogger(__name__)

SCHEDULER_SESSION_ID = "__scheduler__"
RESULT_DATA_MAX_SIZE = 64 * 1024


class TaskExecutor:

    async def execute_task(self, task_id: str) -> dict[str, Any]:
        start_time = time.time()
        task_info = await self._read_task(task_id)
        if not task_info:
            logger.error(f"\n[TaskExecutor] 任务不存在: {task_id}")
            return {"error": f"任务不存在: {task_id}"}

        agent_name = task_info["agent_name"]
        sql_template = task_info["sql_template"]
        run_at = time.time()

        try:
            rows = await asyncio.wait_for(
                asyncio.to_thread(
                    execute_sql,
                    sql=sql_template,
                    params={},
                    session_id=SCHEDULER_SESSION_ID,
                ),
                timeout=55.0,
            )

            duration_ms = int((time.time() - start_time) * 1000)
            result_data, result_summary, row_count = self._process_result(rows)

            await self._write_success_result(
                task_id=task_id,
                agent_name=agent_name,
                run_at=run_at,
                result_data=result_data,
                result_summary=result_summary,
                row_count=row_count,
                duration_ms=duration_ms,
            )
            await self._update_task_timing(task_id)

            logger.info(f"\n[TaskExecutor] 任务执行成功: {task_id}, {row_count}行, {duration_ms}ms")
            return {"task_id": task_id, "status": "success", "row_count": row_count, "duration_ms": duration_ms}

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            await self._write_error_result(
                task_id=task_id,
                agent_name=agent_name,
                run_at=run_at,
                error_message="任务执行超时（55秒）",
                duration_ms=duration_ms,
            )
            return {"task_id": task_id, "status": "error", "error": "任务执行超时"}

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"\n[TaskExecutor] 任务执行失败: {task_id}: {e}")
            await self._write_error_result(
                task_id=task_id,
                agent_name=agent_name,
                run_at=run_at,
                error_message=str(e),
                duration_ms=duration_ms,
            )
            return {"task_id": task_id, "status": "error", "error": str(e)}

    @staticmethod
    def _process_result(rows: list[dict[str, Any]]) -> tuple[str, str, int]:
        row_count = len(rows)
        result_data_str = json.dumps(rows, ensure_ascii=False, default=str)

        if len(result_data_str) > RESULT_DATA_MAX_SIZE:
            result_data_str = result_data_str[:RESULT_DATA_MAX_SIZE] + "\n...[truncated]"
            truncated = True
        else:
            truncated = False

        if row_count == 0:
            result_summary = "查询返回 0 行数据"
        elif row_count == 1 and len(rows[0]) == 1:
            value = list(rows[0].values())[0]
            result_summary = f"查询结果: {value}"
        else:
            result_summary = f"查询返回 {row_count} 行数据"
            if truncated:
                result_summary += "（结果已截断）"

        return result_data_str, result_summary, row_count

    @staticmethod
    async def _read_task(task_id: str) -> dict[str, Any] | None:
        async with async_session() as session:
            result = await session.execute(select(AgentTask).where(AgentTask.task_id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return None
            return {
                "task_id": task.task_id,
                "agent_name": task.agent_name,
                "sql_template": task.sql_template,
                "task_type": task.task_type,
            }

    @staticmethod
    async def _write_success_result(
        *,
        task_id: str,
        agent_name: str,
        run_at: float,
        result_data: str,
        result_summary: str,
        row_count: int,
        duration_ms: int,
    ) -> None:
        now = time.time()
        async with async_session() as session:
            result_record = AgentTaskResult(
                task_id=task_id,
                agent_name=agent_name,
                run_at=run_at,
                status="success",
                result_data=result_data,
                result_summary=result_summary,
                row_count=row_count,
                duration_ms=duration_ms,
                created_at=now,
            )
            session.add(result_record)
            await session.commit()

    @staticmethod
    async def _write_error_result(
        *,
        task_id: str,
        agent_name: str,
        run_at: float,
        error_message: str,
        duration_ms: int,
    ) -> None:
        now = time.time()
        async with async_session() as session:
            result_record = AgentTaskResult(
                task_id=task_id,
                agent_name=agent_name,
                run_at=run_at,
                status="error",
                error_message=error_message,
                duration_ms=duration_ms,
                created_at=now,
            )
            session.add(result_record)
            await session.commit()

    @staticmethod
    async def _update_task_timing(task_id: str) -> None:
        async with async_session() as session:
            result = await session.execute(select(AgentTask).where(AgentTask.task_id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return

            now = time.time()
            task.last_run_at = now
            task.updated_at = now

            try:
                from agent_backend.scheduler.manager import get_scheduler_manager
                manager = get_scheduler_manager()
                if manager._scheduler:
                    job = manager._scheduler.get_job(task_id)
                    if job and job.next_run_time:
                        import datetime
                        task.next_run_at = job.next_run_time.timestamp()
            except Exception:
                pass

            await session.commit()
