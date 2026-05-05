"""
任务执行器模块

文件功能：
    TaskExecutor 负责校验任务参数并调用 TaskDefinition.execute 执行任务，
    同时记录执行历史到数据库。

核心类：
    TaskExecutor: 任务执行器

关联文件：
    - task_engine/base.py: TaskDefinition, TaskResult
    - task_engine/registry.py: TaskRegistry
    - db/models.py: TaskExecution ORM 模型
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

from .base import TaskDefinition, TaskResult
from .registry import get_task_registry


class TaskNotFoundError(Exception):
    pass


class TaskParamValidationError(Exception):
    pass


class TaskExecutor:

    async def execute_task(
        self, agent_type: str, task_id: str, params: dict, user_id: str = "admin"
    ) -> TaskResult:
        registry = get_task_registry()
        task = registry.get_task(agent_type, task_id)
        if not task:
            raise TaskNotFoundError(f"任务不存在: {agent_type}/{task_id}")

        validation_errors = self._validate_all_params(task, params)
        if validation_errors:
            raise TaskParamValidationError(json.dumps(validation_errors, ensure_ascii=False))

        execution_id = uuid.uuid4().hex[:16]
        created_at = time.time()

        try:
            from agent_backend.db.chat_history import async_session
            from agent_backend.db.models import TaskExecution

            async with async_session() as session:
                execution = TaskExecution(
                    execution_id=execution_id,
                    agent_type=agent_type,
                    task_id=task_id,
                    user_id=user_id,
                    params=json.dumps(params, ensure_ascii=False),
                    status="running",
                    created_at=created_at,
                    updated_at=created_at,
                )
                session.add(execution)
                await session.commit()
        except Exception as e:
            logger.warning(f"\n记录任务执行开始失败: {e}")

        try:
            result = await task.execute(params)
            await self._update_execution_status(
                execution_id, "success" if result.success else "failed", result.model_dump()
            )
            return result
        except Exception as e:
            logger.error(f"\n任务执行异常: {e}")
            await self._update_execution_status(execution_id, "failed", {"error": str(e)})
            return TaskResult(success=False, message=f"任务执行异常: {e}")

    def _validate_all_params(self, task: TaskDefinition, params: dict) -> dict[str, str]:
        errors: dict[str, str] = {}
        for step in task.steps:
            for param in step.params:
                value = params.get(param.key)
                if param.required and (value is None or value == "" or value == []):
                    errors[param.key] = f"{param.label}为必填项"
                if param.validation and value is not None:
                    min_val = param.validation.get("min")
                    max_val = param.validation.get("max")
                    if min_val is not None and isinstance(value, (int, float)) and value < min_val:
                        errors[param.key] = f"{param.label}不能小于{min_val}"
                    if max_val is not None and isinstance(value, (int, float)) and value > max_val:
                        errors[param.key] = f"{param.label}不能大于{max_val}"
        return errors

    async def _update_execution_status(
        self, execution_id: str, status: str, result_data: dict | None = None
    ):
        try:
            from agent_backend.db.chat_history import async_session
            from agent_backend.db.models import TaskExecution

            async with async_session() as session:
                from sqlalchemy import update

                stmt = (
                    update(TaskExecution)
                    .where(TaskExecution.execution_id == execution_id)
                    .values(
                        status=status,
                        result=json.dumps(result_data, ensure_ascii=False) if result_data else None,
                        updated_at=time.time(),
                    )
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.warning(f"\n更新任务执行状态失败: {e}")


_task_executor: TaskExecutor | None = None


def get_task_executor() -> TaskExecutor:
    global _task_executor
    if _task_executor is None:
        _task_executor = TaskExecutor()
    return _task_executor
