"""
LLM客户端配置模块

文件功能：
    封装langchain-openai的ChatOpenAI客户端初始化，统一管理LLM连接配置。
    替代旧架构中的自研OpenAICompatibleClient，提供原生Tool Calling支持。

在系统架构中的定位：
    位于Agent基础设施层，为agent_node和sql_query Tool提供LLM调用能力。
    通过环境变量（LLM_BASE_URL/LLM_API_KEY/CHAT_MODEL）动态配置后端。

主要使用场景：
    - agent_node中获取支持Tool Calling的流式LLM实例
    - sql_query Tool中获取同步LLM实例（用于SQL生成）

核心函数：
    - get_llm: 获取ChatOpenAI实例，支持流式/同步、温度等参数配置
    - get_sql_llm: 获取SQL生成专用的LLM实例（同步、温度0）

专有技术说明：
    - 根据base_url自动判断后端类型，注入对应的思考关闭参数：
      - DashScope/阿里云: enable_thinking=False
      - DeepSeek: thinking.type=disabled
      - 其他（Ollama等）: reasoning_effort=none
    - 思考功能关闭可显著减少响应延迟，避免模型进入长时间推理

关联文件：
    - agent_backend/agent/nodes.py: agent_node调用get_llm
    - agent_backend/agent/tools/sql_tool.py: sql_query调用get_sql_llm
    - agent_backend/core/config_helper.py: load_env_file加载环境变量
"""
from __future__ import annotations

import logging
import os

from langchain_openai import ChatOpenAI

from agent_backend.core.config_helper import load_env_file

logger = logging.getLogger(__name__)

load_env_file()


def get_llm(
    *,
    streaming: bool = True,
    temperature: float = 0.3,
) -> ChatOpenAI:
    """
    获取ChatOpenAI实例，统一管理LLM连接配置。

    根据环境变量自动配置后端地址、API Key、模型名称，
    并根据后端类型注入思考关闭参数以减少响应延迟。

    参数：
        streaming: 是否启用流式输出，默认True（agent_node需要流式以支持SSE）
        temperature: 生成温度，默认0.3；SQL生成场景应传0.0

    返回：
        ChatOpenAI: 配置好的LLM客户端实例

    性能注意事项：
        - streaming=True时配合astream_events可实现逐token流式输出
        - 思考关闭参数可避免模型进入长时间推理，显著降低首token延迟
    """
    base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    api_key = os.getenv("LLM_API_KEY") or "ollama"
    model = os.getenv("CHAT_MODEL", "qwen2.5:7b")

    kwargs: dict = {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "streaming": streaming,
        "temperature": temperature,
        "max_tokens": 4096,
    }

    if "dashscope" in base_url or "aliyuncs" in base_url:
        kwargs["extra_body"] = {"enable_thinking": False}
    elif "deepseek" in base_url:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    else:
        kwargs["extra_body"] = {"reasoning_effort": "none"}

    logger.info(
        "LLM初始化: base_url=%s, model=%s, streaming=%s, extra_body=%s",
        base_url, model, streaming, kwargs.get("extra_body"),
    )

    return ChatOpenAI(**kwargs)


def get_sql_llm() -> ChatOpenAI:
    """
    获取SQL生成专用的LLM实例。

    使用同步模式（streaming=False）和最低温度（temperature=0.0），
    确保SQL生成结果的确定性和一致性。

    返回：
        ChatOpenAI: 配置为同步、零温度的LLM客户端实例
    """
    return get_llm(streaming=False, temperature=0.0)
