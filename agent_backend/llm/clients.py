"""
LLM客户端模块

文件目的：
    - 封装大语言模型调用
    - 支持Ollama本地模型
    - 提供流式和同步两种调用方式

核心功能：
    1. 流式聊天（chat_stream）
    2. 同步聊天（chat_complete）
    3. 支持多模态（文本+图片）
    4. 自动选择模型（普通/视觉）

主要类：
    - OllamaChatClient: Ollama客户端实现

支持的模型：
    - qwen2.5:7b-instruct: 文本模型（默认）
    - qwen2.5-vl:7b-instruct: 视觉模型（处理图片）

使用场景：
    - 聊天对话
    - RAG问答
    - SQL生成

相关文件：
    - agent_backend/chat/handlers.py: 聊天处理
    - agent_backend/sql_agent/service.py: SQL生成
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
    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        vision_model: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip(
            "/"
        )
        self.model = model or os.getenv("CHAT_MODEL") or "qwen2.5:7b"
        self.vision_model = vision_model or os.getenv("VISION_MODEL") or "qwen2.5-vl:7b"
        logger.info(f"【LLM客户端】初始化完成")
        logger.info(f"  - Base URL: {self.base_url}")
        logger.info(f"  - 文本模型: {self.model}")
        logger.info(f"  - 视觉模型: {self.vision_model}")

    def chat_stream(
        self,
        messages: list[dict],
        *,
        images_base64: list[str] | None = None,
    ) -> Iterator[str]:
        url = f"{self.base_url}/api/chat"
        model = self.vision_model if images_base64 else self.model
        
        logger.info("=" * 50)
        logger.info("【LLM调用】开始流式聊天")
        logger.info(f"  - URL: {url}")
        logger.info(f"  - 模型: {model}")
        logger.info(f"  - 消息数: {len(messages)}")
        logger.info(f"  - 图片数: {len(images_base64) if images_base64 else 0}")

        ollama_messages = []
        for msg in messages:
            ollama_msg = {"role": msg["role"], "content": msg["content"]}
            if msg["role"] == "user" and images_base64:
                ollama_msg["images"] = images_base64
            ollama_messages.append(ollama_msg)

        payload = {"model": model, "messages": ollama_messages, "stream": True}
        logger.debug(f"【LLM调用】Payload: {json.dumps(payload, ensure_ascii=False)[:500]}...")

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            logger.info("【LLM调用】发送HTTP请求...")
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
                            logger.info(f"【LLM调用】流式响应完成，共 {chunk_count} 个文本块")
                            break
                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error(f"【LLM调用】Ollama调用失败: {type(e).__name__}: {e}")
            raise AppError(
                code="LLM_CALL_FAILED",
                message="调用大模型失败，请检查大模型配置",
                details={"error_type": type(e).__name__, "error_message": str(e)}
            )
        finally:
            logger.info("【LLM调用】结束")
            logger.info("=" * 50)

    def chat_complete(
        self,
        messages: list[dict],
        *,
        images_base64: list[str] | None = None,
    ) -> str:
        url = f"{self.base_url}/api/chat"
        model = self.vision_model if images_base64 else self.model

        ollama_messages = []
        for msg in messages:
            ollama_msg = {"role": msg["role"], "content": msg["content"]}
            if msg["role"] == "user" and images_base64:
                ollama_msg["images"] = images_base64
            ollama_messages.append(ollama_msg)

        payload = {"model": model, "messages": ollama_messages, "stream": False}

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
            logger.error(f"【LLM调用】Ollama调用失败: {type(e).__name__}: {e}")
            raise AppError(
                code="LLM_CALL_FAILED",
                message="调用大模型失败，请检查大模型配置",
                details={"error_type": type(e).__name__, "error_message": str(e)}
            )

        try:
            data = json.loads(body)
        except Exception as e:
            logger.error(f"【LLM调用】返回解析失败: {type(e).__name__}: {e}")
            raise AppError(
                code="LLM_RESPONSE_PARSE_FAILED",
                message="调用大模型失败，请检查大模型配置",
                details={"error_type": type(e).__name__, "error_message": str(e)}
            )

        if "message" not in data or "content" not in data["message"]:
            logger.error(f"【LLM调用】返回内容为空")
            raise AppError(
                code="LLM_RESPONSE_EMPTY",
                message="调用大模型失败，请检查大模型配置",
                details={"response_data": data}
            )

        return data["message"]["content"].strip()
