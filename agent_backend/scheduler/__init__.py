"""
定时任务调度子包入口

文件功能：
    统一导出 scheduler 子包的公共接口，供外部模块导入使用。

在系统架构中的定位：
    作为 scheduler 子包的 __init__.py，简化外部导入路径。
    外部模块可直接 from agent_backend.scheduler import get_scheduler_manager。

核心导出：
    - SchedulerManager: 定时任务调度管理器类
    - get_scheduler_manager: 获取单例实例的工厂函数

关联文件：
    - agent_backend/scheduler/manager.py: SchedulerManager 和 get_scheduler_manager 的实现
"""
from agent_backend.scheduler.manager import SchedulerManager, get_scheduler_manager

__all__ = ["SchedulerManager", "get_scheduler_manager"]
