"""
任务注册表模块

文件功能：
    TaskRegistry 单例，按 agent_type 注册和管理所有 TaskDefinition 子类实例。
    启动时自动扫描 task_engine/tasks/ 目录下的任务定义模块并完成注册。

核心类：
    TaskRegistry: 任务注册表单例

关联文件：
    - task_engine/base.py: TaskDefinition 基类
    - task_engine/tasks/: 各智能体任务定义
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

logger = logging.getLogger(__name__)

from .base import TaskDefinition


class TaskRegistry:
    _instance: TaskRegistry | None = None

    def __init__(self):
        self._tasks: dict[str, dict[str, TaskDefinition]] = {}
        self._load_all()

    @classmethod
    def get_instance(cls) -> TaskRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    def _load_all(self):
        tasks_pkg = Path(__file__).parent / "tasks"
        if not tasks_pkg.exists():
            logger.info("\n任务定义目录不存在: %s", tasks_pkg)
            return

        for finder, module_name, is_pkg in pkgutil.walk_packages(
            [str(tasks_pkg)], prefix="agent_backend.task_engine.tasks."
        ):
            try:
                module = importlib.import_module(module_name)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, TaskDefinition)
                        and attr is not TaskDefinition
                        and attr.task_id
                        and attr.agent_type
                    ):
                        try:
                            instance = attr()
                            self.register(instance)
                            logger.info(
                                "\n注册任务: %s/%s", instance.agent_type, instance.task_id
                            )
                        except Exception as e:
                            logger.warning(
                                "\n注册任务失败 %s.%s: %s", module_name, attr_name, e
                            )
            except Exception as e:
                logger.warning("\n加载任务模块失败 %s: %s", module_name, e)

    def register(self, task: TaskDefinition):
        if task.agent_type not in self._tasks:
            self._tasks[task.agent_type] = {}
        self._tasks[task.agent_type][task.task_id] = task

    def get_tasks(self, agent_type: str) -> list[TaskDefinition]:
        return list(self._tasks.get(agent_type, {}).values())

    def get_task(self, agent_type: str, task_id: str) -> TaskDefinition | None:
        return self._tasks.get(agent_type, {}).get(task_id)

    def has_tasks(self, agent_type: str) -> bool:
        return bool(self._tasks.get(agent_type))

    def reload(self):
        self._tasks.clear()
        self._load_all()


def get_task_registry() -> TaskRegistry:
    return TaskRegistry.get_instance()
