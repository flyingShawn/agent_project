"""
定时任务执行器模块

文件功能：
    负责定时任务的具体执行逻辑，包括读取任务SQL、执行查询、处理结果、
    记录执行结果到数据库。是 SchedulerManager 的执行层。

在系统架构中的定位：
    位于 scheduler 子包的执行层，被 SchedulerManager 通过 APScheduler 调度调用。
    - 对上：SchedulerManager 通过 APScheduler job 触发 execute_task()
    - 对下：调用 sql_agent.executor.execute_sql() 执行SQL查询

主要使用场景：
    - APScheduler 按调度周期自动触发任务执行
    - SchedulerManager.run_task_now() 手动触发任务执行

核心类与函数：
    - TaskExecutor: 任务执行器
      - execute_task(): 执行指定任务，读取SQL模板并查询数据库
      - _process_result(): 处理查询结果，生成摘要和截断大数据
      - _read_task(): 从数据库读取任务定义
      - _write_success_result() / _write_error_result(): 记录执行结果
      - _update_task_timing(): 更新任务的最后/下次执行时间

专有技术说明：
    - 异步+线程桥接：execute_sql() 是同步函数，通过 asyncio.to_thread() 在线程池中执行
    - 超时控制：单次执行超时55秒，避免长时间运行的SQL阻塞调度器
    - 结果截断：超过 RESULT_DATA_MAX_SIZE (64KB) 的结果会被截断，防止数据库膨胀
    - 结果摘要：自动生成 result_summary，单值结果直接展示数值，多行结果展示行数

关联文件：
    - agent_backend/scheduler/manager.py: SchedulerManager 调度触发执行
    - agent_backend/sql_agent/executor.py: execute_sql() 执行SQL查询
    - agent_backend/db/models.py: AgentTask / AgentTaskResult ORM 模型
    - agent_backend/db/chat_history.py: async_session 异步数据库会话
"""
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
    """
    定时任务执行器。

    负责读取任务SQL模板、执行查询、处理结果并持久化执行记录。
    被 APScheduler 通过 SchedulerManager 调度调用。
    """

    async def execute_task(self, task_id: str) -> dict[str, Any]:
        """
        执行指定定时任务。

        执行流程：
            1. 从数据库读取任务定义（SQL模板、agent_name等）
            2. 通过 asyncio.to_thread 在线程池中执行SQL查询
            3. 处理查询结果（截断、摘要生成）
            4. 将执行结果写入 agent_task_result 表
            5. 更新任务的 last_run_at / next_run_at 时间戳

        参数：
            task_id: 要执行的任务唯一标识

        返回：
            dict: 执行结果，包含 task_id, status, row_count, duration_ms
                  失败时包含 error 字段

        超时机制：
            单次执行超时55秒（预留5秒给结果写入），超时后记录错误结果。

        异常处理：
            - TimeoutError: 记录超时错误结果
            - 其他异常: 记录具体错误信息到结果表
            - 所有异常均不抛出，返回错误字典
        """
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
        """
        处理SQL查询结果，生成JSON数据、摘要和行数。

        参数：
            rows: SQL查询返回的行列表

        返回：
            tuple: (result_data_json, result_summary, row_count)
            - result_data_json: 结果JSON字符串，超过64KB时截断
            - result_summary: 结果摘要文本
            - row_count: 结果行数

        摘要生成策略：
            - 0行: "查询返回 0 行数据"
            - 1行单列: "查询结果: {value}"（直接展示数值）
            - 其他: "查询返回 N 行数据"
        """
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
        """
        从数据库读取任务定义。

        参数：
            task_id: 任务唯一标识

        返回：
            dict | None: 包含 task_id, agent_name, sql_template, task_type 的字典
                        任务不存在时返回 None
        """
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
        """
        记录成功的任务执行结果到数据库。

        参数：
            task_id: 任务唯一标识
            agent_name: 智能体名称
            run_at: 执行开始时间戳
            result_data: 查询结果JSON字符串
            result_summary: 结果摘要文本
            row_count: 结果行数
            duration_ms: 执行耗时（毫秒）
        """
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
        """
        记录失败的任务执行结果到数据库。

        参数：
            task_id: 任务唯一标识
            agent_name: 智能体名称
            run_at: 执行开始时间戳
            error_message: 错误信息文本
            duration_ms: 执行耗时（毫秒）
        """
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
        """
        更新任务的最后执行时间和下次执行时间。

        参数：
            task_id: 任务唯一标识

        实现要点：
            - last_run_at 设为当前时间
            - next_run_at 从 APScheduler 的 job.next_run_time 获取
            - 获取 next_run_time 可能失败（如任务已暂停），此时静默跳过
        """
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
