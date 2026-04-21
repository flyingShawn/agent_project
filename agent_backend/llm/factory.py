"""
LLM客户端配置模块

文件功能：
    封装langchain-openai的ChatOpenAI客户端初始化，统一管理LLM连接配置。
    替代旧架构中的自研OpenAICompatibleClient，提供原生Tool Calling支持。

在系统架构中的定位：
    位于LLM基础设施层，为agent_node和sql_query Tool提供LLM调用能力。
    通过AppSettings统一管理LLM连接配置。

核心函数：
    - get_llm: 获取ChatOpenAI实例，支持流式/同步、温度等参数配置
    - get_sql_llm: 获取SQL生成专用的LLM实例（同步、温度0）

关联文件：
    - agent_backend/agent/nodes.py: agent_node调用get_llm
    - agent_backend/agent/tools/sql_tool.py: sql_query调用get_sql_llm
    - agent_backend/core/config.py: AppSettings统一配置管理
"""
from __future__ import annotations

import logging

import httpx
from langchain_openai import ChatOpenAI

from agent_backend.core.config import get_settings

logger = logging.getLogger(__name__)


def get_llm(
    *,
    streaming: bool = True,
    temperature: float = 0.3,
) -> ChatOpenAI:
    """
    获取ChatOpenAI LLM实例。

    根据配置中的base_url自动适配不同厂商的特殊参数：
        - 阿里云通义千问: 禁用思考模式（enable_thinking=False）
        - DeepSeek: 禁用思考模式（thinking.type=disabled）
        - 其他: 关闭推理努力度（reasoning_effort=none）

    参数：
        streaming: 是否启用流式输出，默认True
        temperature: 生成温度，默认0.3

    返回：
        配置完成的ChatOpenAI实例
    """
    settings = get_settings()
    llm_cfg = settings.llm

    base_url = llm_cfg.llm_base_url.rstrip("/")
    api_key = llm_cfg.llm_api_key or "ollama"
    model = llm_cfg.chat_model

    http_client = httpx.Client(proxy=None, timeout=httpx.Timeout(300.0, connect=10.0))
    http_async_client = httpx.AsyncClient(proxy=None, timeout=httpx.Timeout(300.0, connect=10.0))

    kwargs: dict = {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "streaming": streaming,
        "temperature": temperature,
        "max_tokens": 4096,
        "http_client": http_client,
        "http_async_client": http_async_client,
    }

    if "dashscope" in base_url or "aliyuncs" in base_url:
        kwargs["extra_body"] = {"enable_thinking": False}
    elif "deepseek" in base_url:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    else:
        kwargs["extra_body"] = {"reasoning_effort": "none"}

    logger.info(
        "\nLLM初始化: base_url=%s, model=%s, streaming=%s, extra_body=%s",
        base_url, model, streaming, kwargs.get("extra_body"),
    )

    return ChatOpenAI(**kwargs)


def get_sql_llm() -> ChatOpenAI:
    """
    获取SQL生成专用LLM实例。

    使用同步模式（streaming=False）和零温度（temperature=0），
    确保SQL生成的确定性和一致性。

    返回：
        同步模式、零温度的ChatOpenAI实例
    """
    return get_llm(streaming=False, temperature=0.0)
