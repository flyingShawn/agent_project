"""
LLM 客户端模块

文件功能：
    封装 Ollama 大语言模型的 HTTP 调用，提供流式和同步两种对话方式，
    并自动根据是否包含图片切换文本模型与视觉模型。

核心作用与设计目的：
    - 统一封装 Ollama /api/chat 接口调用，屏蔽 HTTP 通信细节
    - 支持流式输出（chat_stream）和同步输出（chat_complete）两种模式
    - 自动检测图片输入，切换至视觉模型处理多模态请求
    - 使用 urllib 标准库实现，避免引入额外 HTTP 依赖

主要使用场景：
    - 聊天对话（SSE 流式推送）
    - RAG 问答（流式输出文档检索结果）
    - SQL 生成（同步调用获取完整 SQL）

包含的主要类与函数：
    - OllamaChatClient: Ollama 客户端实现类
        - __init__(): 初始化客户端，配置服务地址和模型名称
        - chat_stream(): 流式聊天，逐块 yield 文本片段
        - chat_complete(): 同步聊天，返回完整文本

专有技术说明：
    - 使用 Ollama 本地部署的 Qwen2.5 系列模型
    - 文本模型默认 qwen2.5:7b，视觉模型默认 qwen2.5-vl:7b
    - 通过 OLLAMA_BASE_URL/CHAT_MODEL/VISION_MODEL 环境变量配置
    - HTTP 超时设置为 120 秒，适配大模型推理耗时

相关联的调用文件：
    - agent_backend/chat/handlers.py: 聊天处理器调用 chat_stream
    - agent_backend/sql_agent/service.py: SQL 生成调用 chat_complete
    - agent_backend/rag_engine/vision.py: 视觉模型调用（使用 /api/generate 接口）
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Iterator

from agent_backend.core.errors import AppError

logger = logging.getLogger(__name__)


class OllamaChatClient:
    """
    Ollama 聊天客户端，封装与 Ollama /api/chat 接口的 HTTP 通信。

    支持两种调用模式：
        - 流式（chat_stream）：逐块 yield 文本片段，适用于 SSE 推送
        - 同步（chat_complete）：返回完整文本，适用于 SQL 生成等需要完整结果的场景

    模型自动切换规则：
        - 传入 images_base64 且非空时，使用 vision_model（视觉模型）
        - 否则使用 model（文本模型）
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        vision_model: str | None = None,
    ) -> None:
        """
        初始化 Ollama 聊天客户端。

        参数：
            base_url: Ollama 服务地址，默认读取 OLLAMA_BASE_URL 环境变量或 http://localhost:11434
            model: 文本对话模型名称，默认读取 CHAT_MODEL 环境变量或 qwen2.5:7b
            vision_model: 视觉模型名称，默认读取 VISION_MODEL 环境变量或 qwen2.5-vl:7b

        说明：
            - 三个参数均可通过环境变量配置，优先使用显式传入值
        """
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip(
            "/"
        )
        self.model = model or os.getenv("CHAT_MODEL") or "qwen2.5:7b"
        self.vision_model = vision_model or os.getenv("VISION_MODEL") or "qwen2.5-vl:7b"
        logger.info(f"\n【LLM客户端】初始化完成")
        logger.info(f"\n - Base URL: {self.base_url}")
        logger.info(f"\n - 文本模型: {self.model}")
        logger.info(f"\n - 视觉模型: {self.vision_model}")

    def chat_stream(
        self,
        messages: list[dict],
        *,
        images_base64: list[str] | None = None,
    ) -> Iterator[str]:
        """
        流式聊天，逐块 yield LLM 生成的文本片段。

        调用 Ollama /api/chat 接口（stream=True），逐行解析 NDJSON 响应，
        提取每条消息中的 content 字段并 yield。

        参数：
            messages: 消息列表，格式 [{"role": "system/user/assistant", "content": "..."}]
            images_base64: Base64 编码的图片列表，非空时自动切换至视觉模型

        返回：
            Iterator[str]: LLM 生成的文本片段迭代器

        异常：
            AppError(LLM_CALL_FAILED): Ollama 调用失败时抛出（网络错误、超时等）

        性能考量：
            - HTTP 超时 120 秒，适配大模型推理耗时
            - 流式输出可减少用户感知延迟，首 token 延迟取决于模型推理速度
        """
        url = f"{self.base_url}/api/chat"
        model = self.vision_model if images_base64 else self.model
        
        logger.info(f"""
{'=' * 50}
【LLM调用】开始流式聊天
 - URL: {url}
 - 模型: {model}
 - 消息数: {len(messages)}
 - 图片数: {len(images_base64) if images_base64 else 0}
""")
        ollama_messages = []
        for msg in messages:
            ollama_msg = {"role": msg["role"], "content": msg["content"]}
            if msg["role"] == "user" and images_base64:
                ollama_msg["images"] = images_base64
            ollama_messages.append(ollama_msg)

        payload = {"model": model, "messages": ollama_messages, "stream": True, "think": False}
        logger.debug(f"\n【LLM调用】Payload: {json.dumps(payload, ensure_ascii=False)[:500]}...")

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            logger.info("\n【LLM调用】发送HTTP请求...")
            with urllib.request.urlopen(req, timeout=120) as resp:
                buffer = ""
                chunk_count = 0
                for line in resp:
                    line_text = line.decode("utf-8")
                    if not line_text.strip():
                        continue

                    try:
                        data = json.loads(line_text)
                        if "message" in data and "content" in data["message"]:
                            content = data["message"]["content"]
                            if content:
                                chunk_count += 1
                                yield content
                        if data.get("done", False):
                            logger.info(f"\n【LLM调用】流式响应完成，共 {chunk_count} 个文本块")
                            break
                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error(f"\n【LLM调用】Ollama调用失败: {type(e).__name__}: {e}")
            raise AppError(
                code="LLM_CALL_FAILED",
                message="调用大模型失败，请检查大模型配置",
                details={"error_type": type(e).__name__, "error_message": str(e)}
            )
        finally:
            logger.info("\n【LLM调用】结束")
            logger.info("=" * 50)

    def chat_complete(
        self,
        messages: list[dict],
        *,
        images_base64: list[str] | None = None,
    ) -> str:
        """
        同步聊天，返回 LLM 生成的完整文本。

        调用 Ollama /api/chat 接口（stream=False），等待完整响应后返回。

        参数：
            messages: 消息列表，格式 [{"role": "system/user/assistant", "content": "..."}]
            images_base64: Base64 编码的图片列表，非空时自动切换至视觉模型

        返回：
            str: LLM 生成的完整文本（已去除首尾空白）

        异常：
            AppError(LLM_CALL_FAILED): Ollama 调用失败（网络错误、超时等）
            AppError(LLM_RESPONSE_PARSE_FAILED): 响应 JSON 解析失败
            AppError(LLM_RESPONSE_EMPTY): 响应中无有效内容

        性能考量：
            - 同步调用会阻塞直到模型完成推理，耗时可能较长
            - 适用于 SQL 生成等需要完整结果的场景，不适用于实时对话
        """
        url = f"{self.base_url}/api/chat"
        model = self.vision_model if images_base64 else self.model

        ollama_messages = []
        for msg in messages:
            ollama_msg = {"role": msg["role"], "content": msg["content"]}
            if msg["role"] == "user" and images_base64:
                ollama_msg["images"] = images_base64
            ollama_messages.append(ollama_msg)

        payload = {"model": model, "messages": ollama_messages, "stream": False, "think": False}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
        except Exception as e:
            logger.error(f"\n【LLM调用】Ollama调用失败: {type(e).__name__}: {e}")
            raise AppError(
                code="LLM_CALL_FAILED",
                message="调用大模型失败，请检查大模型配置",
                details={"error_type": type(e).__name__, "error_message": str(e)}
            )

        try:
            data = json.loads(body)
        except Exception as e:
            logger.error(f"\n【LLM调用】返回解析失败: {type(e).__name__}: {e}")
            raise AppError(
                code="LLM_RESPONSE_PARSE_FAILED",
                message="调用大模型失败，请检查大模型配置",
                details={"error_type": type(e).__name__, "error_message": str(e)}
            )

        if "message" not in data or "content" not in data["message"]:
            logger.error(f"\n【LLM调用】返回内容为空")
            raise AppError(
                code="LLM_RESPONSE_EMPTY",
                message="调用大模型失败，请检查大模型配置",
                details={"response_data": data}
            )

        return data["message"]["content"].strip()
