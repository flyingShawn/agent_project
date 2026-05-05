"""
任务引擎模块

文件功能：
    提供任务注册、校验、执行的统一入口。
    各智能体的任务定义位于 task_engine/tasks/ 子目录。

核心导出：
    TaskDefinition: 任务定义基类
    TaskResult: 任务执行结果
    TaskParamType: 参数类型枚举
    TaskParam: 参数定义
    TaskStep: 步骤定义
    TaskParamOption: 选项值对象
    get_task_registry: 获取任务注册表单例
    get_task_executor: 获取任务执行器单例

关联文件：
    - task_engine/base.py: 基类与数据模型
    - task_engine/registry.py: 任务注册表
    - task_engine/executor.py: 任务执行器
    - task_engine/schemas.py: API 数据模型
"""
from .base import TaskDefinition, TaskParam, TaskParamOption, TaskParamType, TaskResult, TaskStep
from .executor import TaskExecutor, TaskNotFoundError, TaskParamValidationError, get_task_executor
from .registry import TaskRegistry, get_task_registry
from .schemas import TaskExecuteRequest, TaskOptionQueryParams, TaskValidateRequest

__all__ = [
    "TaskDefinition",
    "TaskParam",
    "TaskParamOption",
    "TaskParamType",
    "TaskResult",
    "TaskStep",
    "TaskRegistry",
    "get_task_registry",
    "TaskExecutor",
    "get_task_executor",
    "TaskNotFoundError",
    "TaskParamValidationError",
    "TaskValidateRequest",
    "TaskExecuteRequest",
    "TaskOptionQueryParams",
]
