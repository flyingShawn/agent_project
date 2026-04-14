"""
网络搜索工具模块

文件功能：
    定义web_search Tool，通过Tavily搜索API搜索互联网获取信息。
    作为LangGraph Tool注册，由LLM通过Tool Calling自主调用。

在系统架构中的定位：
    位于Agent工具层，为Agent提供外部信息获取能力。
    补充内部知识库(RAG)和数据库(SQL)无法覆盖的外部知识。

主要使用场景：
    - 用户问"Windows 11最新版本号"等最新资讯
    - 用户问"xxx错误码怎么解决"等外部知识查询
    - 内部知识库无法回答的技术文档查询

核心函数：
    - web_search: LangGraph Tool，接收搜索关键词，返回搜索结果列表
    - _search_with_tavily: 使用tavily-python SDK调用Tavily API
    - _search_with_requests: 使用requests库直接调用Tavily API（SDK未安装时的回退方案）

专有技术说明：
    - 搜索引擎：Tavily Search API（专为AI Agent优化的搜索服务）
    - 双重调用策略：优先使用tavily-python SDK，未安装时回退到requests直接调用
    - 环境变量控制：TAVILY_API_KEY为空时工具返回配置提示，不会报错
    - 搜索深度：使用basic模式（平衡速度和成本）

配置说明：
    - TAVILY_API_KEY: Tavily API密钥（必填，申请地址：https://tavily.com/）
    - WEB_SEARCH_MAX_RESULTS: 搜索结果数量（默认5）

关联文件：
    - agent_backend/agent/tools/__init__.py: ALL_TOOLS注册
    - agent_backend/agent/prompts.py: SYSTEM_PROMPT中搜索工具决策规则
    - agent_backend/agent/nodes.py: tool_result_node收集web_search_results
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _search_with_tavily(query: str, api_key: str, max_results: int = 5) -> list[dict]:
    """
    使用tavily-python SDK调用Tavily搜索API。

    参数：
        query: 搜索关键词
        api_key: Tavily API密钥
        max_results: 最大返回结果数

    返回：
        list[dict]: 搜索结果列表，每项包含title/url/content字段

    依赖：
        tavily-python包（pip install tavily-python）
    """
    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    response = client.search(query=query, max_results=max_results, search_depth="basic")
    results = []
    for item in response.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
        })
    return results


def _search_with_requests(query: str, api_key: str, max_results: int = 5) -> list[dict]:
    """
    使用requests库直接调用Tavily搜索API。

    当tavily-python SDK未安装时的回退方案。
    直接构造HTTP请求调用Tavily REST API。

    参数：
        query: 搜索关键词
        api_key: Tavily API密钥
        max_results: 最大返回结果数

    返回：
        list[dict]: 搜索结果列表，每项包含title/url/content字段

    依赖：
        requests包
    """
    import requests

    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
        })
    return results


class WebSearchInput(BaseModel):
    """网络搜索工具入参模型"""
    query: str = Field(description="搜索关键词，应精炼准确")


@tool(args_schema=WebSearchInput)
def web_search(query: str) -> str:
    """
    搜索互联网获取信息。
    当用户问题涉及外部知识、最新资讯、错误码查询、技术文档等
    内部知识库和数据库无法覆盖的内容时使用此工具。
    返回搜索结果的标题、链接和摘要。

    参数：
        query: 搜索关键词

    返回：
        str: JSON格式字符串，包含query/results/formatted字段；
             未配置时包含error和hint字段
    """
    logger.info(f"\n[web_search] 搜索: {query}")

    try:
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            return json.dumps({
                "error": "网络搜索未配置",
                "hint": "请设置环境变量 TAVILY_API_KEY 以启用网络搜索功能",
            }, ensure_ascii=False)

        max_results = int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "5"))

        try:
            results = _search_with_tavily(query, api_key, max_results)
        except ImportError:
            logger.info(f"\n[web_search] tavily-python未安装，使用requests回退")
            results = _search_with_requests(query, api_key, max_results)

        if not results:
            return json.dumps({
                "query": query,
                "results": [],
                "message": "未找到相关结果",
            }, ensure_ascii=False)

        formatted_parts = []
        for i, item in enumerate(results, 1):
            formatted_parts.append(
                f"【{i}】{item['title']}\n链接: {item['url']}\n摘要: {item['content']}"
            )

        logger.info(f"\n[web_search] 搜索完成: {query}, 结果数: {len(results)}")
        return json.dumps({
            "query": query,
            "results": results,
            "formatted": "\n\n".join(formatted_parts),
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[web_search] 异常: {type(e).__name__}: {e}")
        return json.dumps({
            "error": f"搜索失败: {type(e).__name__}: {e}",
        }, ensure_ascii=False)
