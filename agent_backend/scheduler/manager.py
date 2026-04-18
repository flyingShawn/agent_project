import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, update, delete, func

from agent_backend.db.chat_history import async_session
from agent_backend.db.models import AgentTask, AgentTaskResult
from agent_backend.scheduler.executor import TaskExecutor

logger = logging.getLogger(__name__)

SCHEDULER_SESSION_ID = "__scheduler__"
RESULT_RETENTION_DAYS = 7
RESULT_DATA_MAX_SIZE = 64 * 1024

_CONFIGS_DIR = Path(__file__).parent.parent / "configs"


class SchedulerManager:
    _instance: "SchedulerManager | None" = None

    def __new__(cls) -> "SchedulerManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_initialized"):
            self._scheduler: AsyncIOScheduler | None = None
            self._executor: TaskExecutor | None = None
            self._initialized = True

    @property
    def is_running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running

    async def start(self) -> None:
        if self._scheduler is not None and self._scheduler.running:
            logger.info("\n[Scheduler] 调度器已在运行中")
            return

        self._executor = TaskExecutor()
        self._scheduler = AsyncIOScheduler(
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60}
        )

        await self._recover_tasks_from_db()
        await self._load_default_tasks()
        self._register_cleanup_job()

        self._scheduler.start()
        logger.info("\n[Scheduler] 调度器已启动")

    async def shutdown(self, wait: bool = True) -> None:
        if self._scheduler is None:
            return
        logger.info("\n[Scheduler] 正在关闭调度器...")
        self._scheduler.shutdown(wait=wait)
        self._scheduler = None
        logger.info("\n[Scheduler] 调度器已关闭")

    async def add_task(
        self,
        *,
        task_name: str,
        task_type: str,
        task_config: dict[str, Any],
        sql_template: str,
        description: str | None = None,
        created_by: str = "chat",
    ) -> dict[str, Any]:
        agent_name = os.environ.get("AGENT_NAME", "desk-agent")
        task_id = f"{agent_name}_{task_type}_{uuid.uuid4().hex[:8]}"
        now = time.time()

        async with async_session() as session:
            existing = await session.execute(
                select(AgentTask).where(AgentTask.task_name == task_name, AgentTask.status == "active")
            )
            if existing.scalar_one_or_none():
                return {"error": f"已存在同名活跃任务: {task_name}"}

            task = AgentTask(
                task_id=task_id,
                agent_name=agent_name,
                task_name=task_name,
                task_type=task_type,
                task_config=json.dumps(task_config, ensure_ascii=False),
                sql_template=sql_template,
                description=description,
                status="active",
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            await session.commit()

        self._register_task_to_scheduler(task_id, task_type, task_config)
        logger.info(f"\n[Scheduler] 任务已创建: {task_id} ({task_name})")
        return {"task_id": task_id, "task_name": task_name, "status": "active"}

    async def pause_task(self, task_id: str) -> dict[str, Any]:
        async with async_session() as session:
            result = await session.execute(select(AgentTask).where(AgentTask.task_id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return {"error": f"任务不存在: {task_id}"}
            if task.status != "active":
                return {"error": f"任务当前状态为 {task.status}，无法暂停"}

            task.status = "paused"
            task.updated_at = time.time()
            await session.commit()

        if self._scheduler:
            try:
                self._scheduler.remove_job(task_id)
            except Exception:
                pass

        logger.info(f"\n[Scheduler] 任务已暂停: {task_id}")
        return {"task_id": task_id, "status": "paused"}

    async def resume_task(self, task_id: str) -> dict[str, Any]:
        async with async_session() as session:
            result = await session.execute(select(AgentTask).where(AgentTask.task_id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return {"error": f"任务不存在: {task_id}"}
            if task.status != "paused":
                return {"error": f"任务当前状态为 {task.status}，无法恢复"}

            task.status = "active"
            task.updated_at = time.time()
            await session.commit()
            task_config = json.loads(task.task_config)
            task_type = task.task_type

        self._register_task_to_scheduler(task_id, task_type, task_config)
        logger.info(f"\n[Scheduler] 任务已恢复: {task_id}")
        return {"task_id": task_id, "status": "active"}

    async def delete_task(self, task_id: str) -> dict[str, Any]:
        async with async_session() as session:
            result = await session.execute(select(AgentTask).where(AgentTask.task_id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return {"error": f"任务不存在: {task_id}"}

            task.status = "completed"
            task.updated_at = time.time()
            await session.commit()

        if self._scheduler:
            try:
                self._scheduler.remove_job(task_id)
            except Exception:
                pass

        logger.info(f"\n[Scheduler] 任务已删除: {task_id}")
        return {"task_id": task_id, "status": "completed"}

    async def update_task_sql(self, task_id: str, sql_template: str) -> dict[str, Any]:
        async with async_session() as session:
            result = await session.execute(select(AgentTask).where(AgentTask.task_id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return {"error": f"任务不存在: {task_id}"}

            task.sql_template = sql_template
            task.updated_at = time.time()
            await session.commit()

        logger.info(f"\n[Scheduler] 任务SQL已更新: {task_id}")
        return {"task_id": task_id, "status": "updated"}

    async def get_tasks(self) -> list[dict[str, Any]]:
        async with async_session() as session:
            result = await session.execute(
                select(AgentTask).where(AgentTask.status != "completed").order_by(AgentTask.created_at.desc())
            )
            tasks = result.scalars().all()
            return [
                {
                    "task_id": t.task_id,
                    "agent_name": t.agent_name,
                    "task_name": t.task_name,
                    "task_type": t.task_type,
                    "task_config": json.loads(t.task_config) if t.task_config else {},
                    "sql_template": t.sql_template,
                    "description": t.description,
                    "status": t.status,
                    "last_run_at": t.last_run_at,
                    "next_run_at": t.next_run_at,
                    "created_by": t.created_by,
                    "created_at": t.created_at,
                }
                for t in tasks
            ]

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        async with async_session() as session:
            result = await session.execute(select(AgentTask).where(AgentTask.task_id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return None
            return {
                "task_id": task.task_id,
                "agent_name": task.agent_name,
                "task_name": task.task_name,
                "task_type": task.task_type,
                "task_config": json.loads(task.task_config) if task.task_config else {},
                "sql_template": task.sql_template,
                "description": task.description,
                "status": task.status,
                "last_run_at": task.last_run_at,
                "next_run_at": task.next_run_at,
                "created_by": task.created_by,
                "created_at": task.created_at,
            }

    async def get_task_results(self, task_id: str, limit: int = 20) -> list[dict[str, Any]]:
        async with async_session() as session:
            result = await session.execute(
                select(AgentTaskResult)
                .where(AgentTaskResult.task_id == task_id)
                .order_by(AgentTaskResult.run_at.desc())
                .limit(limit)
            )
            results = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "task_id": r.task_id,
                    "agent_name": r.agent_name,
                    "run_at": r.run_at,
                    "status": r.status,
                    "result_data": r.result_data,
                    "result_summary": r.result_summary,
                    "row_count": r.row_count,
                    "error_message": r.error_message,
                    "duration_ms": r.duration_ms,
                    "created_at": r.created_at,
                }
                for r in results
            ]

    async def run_task_now(self, task_id: str) -> dict[str, Any]:
        task_info = await self.get_task(task_id)
        if not task_info:
            return {"error": f"任务不存在: {task_id}"}
        if task_info["status"] not in ("active", "paused"):
            return {"error": f"任务状态为 {task_info['status']}，无法手动执行"}

        try:
            result = await asyncio.wait_for(
                self._executor.execute_task(task_id),
                timeout=60.0,
            )
            return result
        except asyncio.TimeoutError:
            return {"error": "任务执行超时（60秒）"}
        except Exception as e:
            logger.error(f"\n[Scheduler] 手动执行任务失败: {task_id}: {e}")
            return {"error": f"任务执行失败: {e}"}

    def get_scheduler_info(self) -> dict[str, Any]:
        if not self._scheduler:
            return {"running": False, "active_tasks": 0}
        jobs = self._scheduler.get_jobs()
        return {
            "running": self._scheduler.running,
            "active_tasks": len(jobs),
            "jobs": [
                {"job_id": j.id, "next_run_time": str(j.next_run_time)} for j in jobs
            ],
        }

    def _register_task_to_scheduler(
        self, task_id: str, task_type: str, task_config: dict[str, Any]
    ) -> None:
        if not self._scheduler:
            return

        try:
            if task_type == "interval":
                seconds = task_config.get("interval_seconds", 1800)
                trigger = IntervalTrigger(seconds=seconds)
            elif task_type == "cron":
                cron_expr = task_config.get("cron_expr", "0 * * * *")
                parts = cron_expr.split()
                trigger = CronTrigger(
                    minute=parts[0] if len(parts) > 0 else "*",
                    hour=parts[1] if len(parts) > 1 else "*",
                    day=parts[2] if len(parts) > 2 else "*",
                    month=parts[3] if len(parts) > 3 else "*",
                    day_of_week=parts[4] if len(parts) > 4 else "*",
                )
            else:
                logger.warning(f"\n[Scheduler] 未知任务类型: {task_type}")
                return

            self._scheduler.add_job(
                self._executor.execute_task,
                trigger=trigger,
                id=task_id,
                args=[task_id],
                replace_existing=True,
            )
            logger.info(f"\n[Scheduler] 任务已注册到调度器: {task_id} (type={task_type})")
        except Exception as e:
            logger.error(f"\n[Scheduler] 注册任务失败: {task_id}: {e}")

    async def _recover_tasks_from_db(self) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(AgentTask).where(AgentTask.status == "active")
            )
            tasks = result.scalars().all()
            for task in tasks:
                try:
                    task_config = json.loads(task.task_config)
                    self._register_task_to_scheduler(task.task_id, task.task_type, task_config)
                except Exception as e:
                    logger.error(f"\n[Scheduler] 恢复任务失败: {task.task_id}: {e}")
        logger.info(f"\n[Scheduler] 从数据库恢复了 {len(tasks)} 个活跃任务")

    async def _load_default_tasks(self) -> None:
        config_path = _CONFIGS_DIR / "scheduled_tasks.yaml"
        if not config_path.exists():
            logger.info("\n[Scheduler] 未找到默认任务配置文件，跳过加载")
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"\n[Scheduler] 加载默认任务配置失败: {e}")
            return

        agent_name = os.environ.get("AGENT_NAME", "desk-agent")
        tasks = config.get("tasks", [])
        loaded_count = 0

        async with async_session() as session:
            for task_def in tasks:
                task_id = task_def.get("task_id")
                if not task_id:
                    continue

                existing = await session.execute(
                    select(AgentTask).where(AgentTask.task_id == task_id)
                )
                if existing.scalar_one_or_none():
                    continue

                task_type = task_def.get("task_type", "interval")
                task_config: dict[str, Any] = {}
                if task_type == "interval":
                    task_config["interval_seconds"] = task_def.get("interval_seconds", 1800)
                elif task_type == "cron":
                    task_config["cron_expr"] = task_def.get("cron_expr", "0 * * * *")

                now = time.time()
                task = AgentTask(
                    task_id=task_id,
                    agent_name=agent_name,
                    task_name=task_def.get("task_name", task_id),
                    task_type=task_type,
                    task_config=json.dumps(task_config, ensure_ascii=False),
                    sql_template=task_def.get("sql_template", ""),
                    description=task_def.get("description"),
                    status="active",
                    created_by="system",
                    created_at=now,
                    updated_at=now,
                )
                session.add(task)
                self._register_task_to_scheduler(task_id, task_type, task_config)
                loaded_count += 1

            await session.commit()

        logger.info(f"\n[Scheduler] 从配置文件加载了 {loaded_count} 个新默认任务")

    def _register_cleanup_job(self) -> None:
        if not self._scheduler:
            return
        self._scheduler.add_job(
            self._cleanup_old_results,
            CronTrigger(hour="3", minute="0"),
            id="__cleanup_old_results__",
            replace_existing=True,
        )
        logger.info("\n[Scheduler] 已注册结果清理任务（每天凌晨3:00）")

    @staticmethod
    async def _cleanup_old_results() -> None:
        cutoff = time.time() - RESULT_RETENTION_DAYS * 86400
        async with async_session() as session:
            result = await session.execute(
                delete(AgentTaskResult).where(AgentTaskResult.created_at < cutoff)
            )
            await session.commit()
            logger.info(f"\n[Scheduler] 清理了 {result.rowcount} 条过期任务结果（>{RESULT_RETENTION_DAYS}天）")


def get_scheduler_manager() -> SchedulerManager:
    return SchedulerManager()
