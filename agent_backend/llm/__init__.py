"""
LLM模块公共接口

文件功能：
    导出LLM模块的核心类和工厂函数，提供统一的LLM调用入口。

在系统架构中的定位：
    位于LLM模块的顶层，对外暴露 get_llm、get_sql_llm 工厂函数和底层客户端类。

核心导出：
    - get_llm: 获取通用ChatOpenAI实例（支持流式/同步）
    - get_sql_llm: 获取SQL生成专用LLM实例（同步、温度0）
    - OpenAICompatibleClient: 自研OpenAI兼容HTTP客户端
    - OllamaChatClient: Ollama原生协议HTTP客户端

关联文件：
    - agent_backend/llm/factory.py: LangChain ChatOpenAI工厂
    - agent_backend/llm/clients.py: 底层HTTP客户端实现
"""
from agent_backend.llm.factory import get_llm, get_sql_llm
from agent_backend.llm.clients import OpenAICompatibleClient, OllamaChatClient
