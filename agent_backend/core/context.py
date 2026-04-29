"""
智能体上下文变量模块

文件功能：
    定义跨请求链路传递 agent_type 的上下文变量。
    通过 contextvars 实现，确保在异步环境中每个请求
    独立持有自己的 agent_type，互不干扰。

在系统架构中的定位：
    位于基础设施层，被 API 层设置、工具层读取，
    贯穿整个请求处理链路。

核心组件：
    - current_agent_type: ContextVar[str]，当前请求对应的智能体类型标识

使用方式：
    - API 层（设置）：current_agent_type.set("desk-agent")
    - 工具层（读取）：agent_type = current_agent_type.get()
    - 默认值：desk-agent

关联文件：
    - agent_backend/api/v1/chat.py: 请求入口设置 agent_type
    - agent_backend/agent/tools/sql_tool.py: 读取 agent_type 获取对应配置
    - agent_backend/agent/tools/rag_tool.py: 读取 agent_type 获取对应 RAG 配置
"""
import contextvars

current_agent_type: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_agent_type", default="desk-agent"
)
