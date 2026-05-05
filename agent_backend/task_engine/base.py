"""
任务引擎基类定义模块

文件功能：
    定义任务引擎的核心抽象基类和数据模型，所有智能体的任务定义
    均需继承 TaskDefinition 并实现 execute 方法。

核心类：
    TaskParamType: 任务参数类型枚举
    TaskParamOption: 选项值对象
    TaskParam: 单个参数定义
    TaskStep: 任务步骤定义
    TaskResult: 任务执行结果
    TaskDefinition: 任务定义抽象基类

关联文件：
    - task_engine/registry.py: TaskRegistry 注册任务定义子类
    - task_engine/executor.py: TaskExecutor 执行任务
    - task_engine/tasks/: 各智能体具体任务实现
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel

from agent_backend.core.context import current_agent_type

import logging
logger = logging.getLogger(__name__)


class TaskParamType(str, Enum):
    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    FILE_PATH = "file_path"
    DATE = "date"
    TIME = "time"
    BOOLEAN = "boolean"
    CLIENT_SELECTOR = "client_selector"
    DEPARTMENT_SELECTOR = "department_selector"


class TaskParamOption(BaseModel):
    label: str
    value: Any


class TaskParam(BaseModel):
    key: str
    label: str
    type: TaskParamType
    required: bool = True
    default: Any = None
    options: list[TaskParamOption] | None = None
    placeholder: str | None = None
    description: str | None = None
    validation: dict | None = None
    options_api: str | None = None


class TaskStep(BaseModel):
    id: str
    title: str
    description: str | None = None
    params: list[TaskParam]


class TaskResult(BaseModel):
    success: bool
    message: str
    data: Any = None
    result_type: str = "text"


class TaskDefinition(ABC):
    task_id: str = ""
    name: str = ""
    description: str = ""
    icon: str = "task"
    category: str = "default"
    agent_type: str = ""
    steps: list[TaskStep] = []

    @abstractmethod
    async def execute(self, params: dict) -> TaskResult:
        pass

    async def validate_step(self, step_id: str, params: dict) -> dict:
        step = next((s for s in self.steps if s.id == step_id), None)
        if not step:
            return {"valid": False, "errors": {"_step": f"步骤不存在: {step_id}"}}

        errors: dict[str, str] = {}
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

        return {"valid": len(errors) == 0, "errors": errors}

    def get_summary(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "category": self.category,
            "agent_type": self.agent_type,
            "step_count": len(self.steps),
        }

    def get_schema(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "category": self.category,
            "agent_type": self.agent_type,
            "steps": [step.model_dump() for step in self.steps],
        }

    def _get_api_base_url(self) -> str:
        from agent_backend.agent.registry import get_registry

        agent_type = self.agent_type or current_agent_type.get("")
        try:
            registry = get_registry()
            config = registry.get_agent_config(agent_type)
            if config and config.tasks and config.tasks.api_base_url:
                return config.tasks.api_base_url
        except Exception as e:
            logger.warning(f"\n获取任务 API 地址失败: {e}")
        return ""
