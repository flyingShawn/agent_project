"""
基础设施模块公共接口

文件功能：
    导出基础设施层的核心组件，为应用提供配置、异常、日志、中间件等基础能力。

在系统架构中的定位：
    位于基础设施层的顶层，被所有业务模块引用。

核心导出：
    - load_env_file: 环境变量文件加载
    - get_database_url: 获取业务数据库URL
    - get_max_rows: 获取SQL查询最大行数
    - get_schema_runtime: 获取Schema运行时配置
    - SchemaRuntime: Schema运行时配置类
    - AppError: 统一业务异常
    - register_exception_handlers: 注册全局异常处理器
    - configure_logging: 日志配置初始化
    - RequestIdMiddleware: 请求ID中间件

关联文件：
    - agent_backend/core/config.py: 统一配置管理
    - agent_backend/core/errors.py: 统一异常定义
    - agent_backend/core/logging.py: 日志配置
    - agent_backend/core/request_id.py: 请求ID中间件
"""
from agent_backend.core.config import load_env_file, get_database_url, get_max_rows, get_schema_runtime, SchemaRuntime
from agent_backend.core.errors import AppError, register_exception_handlers
from agent_backend.core.logging import configure_logging
from agent_backend.core.request_id import RequestIdMiddleware
