"""
定时任务调度管理器模块

文件功能：
    定时任务的核心管理模块，负责任务的完整生命周期管理，包括创建、暂停、恢复、
    删除、执行和结果查询。基于 APScheduler 3.x AsyncIOScheduler 实现异步调度，
    通过 SQLite 持久化任务定义和执行结果。

在系统架构中的定位：
    位于 scheduler 子包的核心层，是定时任务功能的"大脑"。
    - 对上：被 API 路由层（api/v1/scheduler.py）和 Agent 工具层（agent/tools/）调用
    - 对下：调用 executor 执行具体任务，通过 chat_history 的 async_session 持久化数据

主要使用场景：
    - 应用启动时恢复和加载默认任务
    - API 路由层响应前端任务管理请求
    - Agent 工具层响应聊天创建/管理任务请求
    - 定时自动执行已注册的周期性任务

核心类与函数：
    - SchedulerManager: 单例调度管理器，封装所有任务操作
      - start(): 启动调度器，恢复数据库任务，加载配置文件默认任务
      - shutdown(): 优雅关闭调度器
      - add_task(): 创建新任务（校验同名、持久化、注册调度）
      - pause_task() / resume_task() / delete_task(): 任务状态管理
      - update_task_sql(): 更新任务SQL模板
      - get_tasks() / get_task() / get_task_results(): 任务与结果查询
      - run_task_now(): 手动触发任务执行
    - get_scheduler_manager(): 获取单例实例的工厂函数

专有技术说明：
    - 单例模式：通过 __new__ + _initialized 标志实现，确保全局唯一调度器实例
    - 配置热更新：_load_default_tasks() 会对比配置文件与数据库中的SQL模板，
      当配置文件变更时自动更新活跃任务的SQL模板
    - 软删除策略：delete_task() 将状态设为 completed 而非物理删除，保留历史数据
    - 结果自动清理：每天凌晨3:00清理超过 RESULT_RETENTION_DAYS 天的旧结果

关联文件：
    - agent_backend/scheduler/executor.py: TaskExecutor 执行具体SQL任务
    - agent_backend/db/models.py: AgentTask / AgentTaskResult ORM 模型
    - agent_backend/db/chat_history.py: async_session 异步数据库会话
    - agent_backend/configs/scheduled_tasks.yaml: 默认任务配置文件
    - agent_backend/api/v1/scheduler.py: REST API 路由
    - agent_backend/agent/tools/scheduler_tool.py: Agent 创建任务工具
"""
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
    """
    定时任务调度管理器（单例模式）。

    封装 APScheduler AsyncIOScheduler，提供任务的完整生命周期管理。
    通过 SQLite 持久化任务定义和执行结果，支持配置文件热更新。

    核心职责：
        1. 调度器启停管理
        2. 任务CRUD操作（创建、查询、暂停、恢复、删除）
        3. 从数据库恢复任务、从配置文件加载默认任务
        4. 过期结果自动清理

    线程安全说明：
        单例实例在应用启动时创建，后续调用 get_scheduler_manager() 均返回同一实例。
        APScheduler 内部保证 job 执行的线程安全（max_instances=1）。
    """
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
        """调度器是否正在运行。"""
        return self._scheduler is not None and self._scheduler.running

    async def start(self) -> None:
        """
        启动调度器并初始化任务。

        执行流程：
            1. 创建 TaskExecutor 和 AsyncIOScheduler 实例
            2. 从数据库恢复活跃任务（_recover_tasks_from_db）
            3. 从配置文件加载默认任务（_load_default_tasks）
            4. 注册过期结果清理定时任务
            5. 启动调度器

        幂等性：
            若调度器已在运行，直接返回不重复启动。
        """
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
        """
        优雅关闭调度器。

        参数：
            wait: 是否等待正在执行的任务完成，默认 True

        关闭后 _scheduler 置为 None，后续调用 start() 可重新启动。
        """
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
        """
        创建新的定时任务。

        参数：
            task_name: 任务名称，如"统计在线客户端数量"。同名活跃任务会被拒绝
            task_type: 任务类型，"interval"（固定间隔）或 "cron"（cron表达式）
            task_config: 任务调度配置，interval 类型含 interval_seconds，cron 类型含 cron_expr
            sql_template: 要周期执行的 SQL 模板
            description: 任务自然语言描述
            created_by: 创建来源，"chat"（对话创建）或 "system"（配置文件加载）

        返回：
            dict: 成功时 {"task_id": ..., "task_name": ..., "status": "active"}
                  失败时 {"error": "已存在同名活跃任务: ..."}

        业务规则：
            - 同名活跃任务不可重复创建，避免调度冲突
            - task_id 格式为 {agent_name}_{task_type}_{uuid8}，保证全局唯一
            - 创建后立即注册到 APScheduler，无需重启即可生效
        """
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
        """
        暂停活跃的定时任务。

        参数：
            task_id: 要暂停的任务ID

        返回：
            dict: 成功时 {"task_id": ..., "status": "paused"}
                  失败时 {"error": "任务不存在" / "任务当前状态为 xxx，无法暂停"}

        效果：
            - 数据库状态更新为 paused
            - APScheduler 中移除对应 job，停止自动调度
            - 可通过 resume_task() 恢复
        """
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
        """
        恢复已暂停的定时任务。

        参数：
            task_id: 要恢复的任务ID

        返回：
            dict: 成功时 {"task_id": ..., "status": "active"}
                  失败时 {"error": "任务不存在" / "任务当前状态为 xxx，无法恢复"}

        效果：
            - 数据库状态更新为 active
            - 重新注册到 APScheduler，恢复自动调度
        """
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
        """
        软删除定时任务（状态标记为 completed）。

        参数：
            task_id: 要删除的任务ID

        返回：
            dict: 成功时 {"task_id": ..., "status": "completed"}
                  失败时 {"error": "任务不存在"}

        注意：
            采用软删除策略，将状态设为 completed 而非物理删除，
            保留任务定义和执行历史，便于审计和恢复。
        """
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
        """
        更新任务的 SQL 模板。

        参数：
            task_id: 要更新的任务ID
            sql_template: 新的 SQL 模板

        返回：
            dict: 成功时 {"task_id": ..., "status": "updated"}
                  失败时 {"error": "任务不存在"}

        注意：
            仅更新 SQL 模板文本，不改变调度配置。
            下次任务执行时将使用新的 SQL。
        """
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
        """
        获取所有非已完成状态的定时任务列表。

        返回：
            list[dict]: 任务字典列表，按创建时间倒序排列。
            每个字典包含 task_id, agent_name, task_name, task_type, task_config,
            sql_template, description, status, last_run_at, next_run_at,
            created_by, created_at 等字段。

        过滤规则：
            排除 status == "completed" 的软删除任务。
        """
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
        """
        根据任务ID获取单个任务的详细信息。

        参数：
            task_id: 任务唯一标识

        返回：
            dict | None: 任务详情字典，不存在时返回 None
        """
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
        """
        获取指定任务的执行结果列表。

        参数：
            task_id: 任务唯一标识
            limit: 返回结果数量上限，默认20，范围1-100

        返回：
            list[dict]: 执行结果字典列表，按执行时间倒序排列。
            每个字典包含 id, task_id, agent_name, run_at, status,
            result_data, result_summary, row_count, error_message,
            duration_ms, created_at 等字段。
        """
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
        """
        手动触发任务立即执行（不等待调度周期）。

        参数：
            task_id: 要执行的任务ID

        返回：
            dict: 执行结果，包含 task_id, status, row_count, duration_ms
                  失败时包含 error 字段

        超时机制：
            单次执行超时时间为60秒，超时后返回错误结果并记录。

        异常处理：
            任务不存在或状态不允许执行时返回错误信息，不抛异常。
        """
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
        """
        获取调度器运行状态信息。

        返回：
            dict: 包含 running（是否运行）、active_tasks（活跃任务数）、
            jobs（所有job的ID和下次执行时间）。
        """
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
        """
        将任务注册到 APScheduler 调度器。

        参数：
            task_id: 任务唯一标识，同时作为 APScheduler job ID
            task_type: "interval" 或 "cron"
            task_config: 调度配置字典

        触发器映射：
            - interval → IntervalTrigger(seconds=interval_seconds)
            - cron → CronTrigger(minute/hour/day/month/day_of_week)

        注意：
            replace_existing=True 确保重复注册时覆盖旧 job 而非报错。
        """
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
        """
        从数据库恢复所有活跃任务到调度器。

        在应用启动时调用，遍历 agent_task 表中 status="active" 的记录，
        解析 task_config 并注册到 APScheduler。

        容错机制：
            单个任务恢复失败不影响其他任务，错误记录到日志。
        """
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
        """
        从配置文件 scheduled_tasks.yaml 加载默认任务。

        加载策略（按优先级）：
            1. 活跃任务（status=active）：对比SQL模板，若配置文件有变更则热更新
            2. 非活跃任务（status!=active）：重新激活并更新配置
            3. 新任务（数据库中不存在）：创建并注册

        配置热更新：
            当配置文件中的 sql_template 与数据库中不一致时，
            自动更新活跃任务的SQL模板，无需重启服务。

        配置文件路径：
            agent_backend/configs/scheduled_tasks.yaml
        """
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
                existing_task = existing.scalar_one_or_none()
                if existing_task and existing_task.status == "active":
                    new_sql = task_def.get("sql_template", "")
                    if new_sql and existing_task.sql_template != new_sql:
                        existing_task.sql_template = new_sql
                        existing_task.task_name = task_def.get("task_name", task_id)
                        existing_task.description = task_def.get("description")
                        existing_task.updated_at = time.time()
                        await session.commit()
                        logger.info(f"\n[Scheduler] 更新活跃任务的SQL模板: {task_id}")
                    continue

                if existing_task and existing_task.status != "active":
                    existing_task.status = "active"
                    existing_task.sql_template = task_def.get("sql_template", "")
                    existing_task.task_name = task_def.get("task_name", task_id)
                    existing_task.description = task_def.get("description")
                    existing_task.updated_at = time.time()
                    task_type = existing_task.task_type
                    task_config = json.loads(existing_task.task_config) if existing_task.task_config else {}
                    await session.commit()
                    self._register_task_to_scheduler(task_id, task_type, task_config)
                    loaded_count += 1
                    logger.info(f"\n[Scheduler] 重新激活已完成任务: {task_id}")
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
        """
        注册过期任务结果的自动清理定时任务。

        清理策略：
            每天凌晨3:00执行，删除 created_at 超过 RESULT_RETENTION_DAYS 天的
            AgentTaskResult 记录。默认保留7天。

        性能考虑：
            使用 DELETE 批量删除，避免逐条查询。
        """
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
        """
        清理过期的任务执行结果。

        计算截止时间 = 当前时间 - RESULT_RETENTION_DAYS * 86400，
        删除 agent_task_result 表中 created_at 早于截止时间的记录。
        """
        cutoff = time.time() - RESULT_RETENTION_DAYS * 86400
        async with async_session() as session:
            result = await session.execute(
                delete(AgentTaskResult).where(AgentTaskResult.created_at < cutoff)
            )
            await session.commit()
            logger.info(f"\n[Scheduler] 清理了 {result.rowcount} 条过期任务结果（>{RESULT_RETENTION_DAYS}天）")


def get_scheduler_manager() -> SchedulerManager:
    """
    获取 SchedulerManager 单例实例。

    返回：
        SchedulerManager: 全局唯一的调度管理器实例

    使用场景：
        在 API 路由、Agent 工具等需要操作定时任务的地方调用此函数。
    """
    return SchedulerManager()
