"""
运维简报模块公共接口

文件功能：
    导出运维简报模块的核心类和工厂函数。

在系统架构中的定位：
    位于运维简报模块的顶层，被 api/v1/ops.py 和 main.py 引用。

核心导出：
    - OpsReportManager: 运维简报管理器（单例模式）
    - get_ops_report_manager: 获取管理器实例的工厂函数

关联文件：
    - agent_backend/ops_reports/manager.py: 管理器实现
    - agent_backend/ops_reports/executor.py: 报告生成器实现
"""
from agent_backend.ops_reports.manager import OpsReportManager, get_ops_report_manager

__all__ = ["OpsReportManager", "get_ops_report_manager"]
