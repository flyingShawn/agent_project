"""
视觉模型客户端模块

文件功能：
    封装视觉模型的 HTTP 调用，将图片通过 OCR/描述转为 Markdown 文本，
    用于 RAG 文档导入时处理图片类文件。

核心作用与设计目的：
    - 定义 VisionClient 抽象基类，便于后续扩展其他视觉模型
    - OpenAIVisionClient 实现：调用 OpenAI 兼容 /v1/chat/completions 接口，传递 base64 图片
    - OllamaVisionClient 实现：调用 Ollama /api/generate 接口（兼容保留）
    - 输出纯 Markdown 文本，可直接进入分块和向量化流程

主要使用场景：
    - 文档导入时解析图片文件（png/jpg/jpeg/webp）
    - 作为 Docling 解析失败时的回退方案

包含的主要类：
    - VisionClient: 视觉客户端抽象基类
    - OpenAIVisionClient: OpenAI 兼容协议视觉模型客户端（推荐）
    - OllamaVisionClient: Ollama 视觉模型客户端（兼容保留）

专有技术说明：
    - OpenAIVisionClient 使用 /v1/chat/completions 接口，图片以 OpenAI 多模态格式传入
    - 通过 LLM_BASE_URL/LLM_API_KEY 环境变量切换后端
    - 默认模型：qwen2.5-vl:7b（Qwen2.5 视觉语言模型）
    - 图片以 base64 编码传入，HTTP 超时 120 秒

相关联的调用文件：
    - agent_backend/rag_engine/docling_parser.py: 图片解析时调用
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path

from agent_backend.core.errors import AppError


class VisionClient:
    def image_to_markdown(self, image_path: Path) -> str:
        raise NotImplementedError


class OpenAIVisionClient(VisionClient):
    def __init__(self, *, base_url: str | None = None, api_key: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or "http://localhost:11434/v1").rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY") or ""
        self.model = model or os.getenv("VISION_MODEL") or "qwen2.5-vl:7b"

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def image_to_markdown(self, image_path: Path) -> str:
        if not image_path.exists() or not image_path.is_file():
            raise AppError(code="image_not_found", message=f"图片不存在: {image_path}", http_status=400)

        img_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        prompt = (
            "请识别这张图片中的文字（如有），并给出简要说明。"
            "只输出 Markdown 纯文本，不要输出代码块，不要输出解释。"
            "若有明确的标题/小节，请使用 #/## 标题。"
        )

        url = f"{self.base_url}/chat/completions"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                ],
            }
        ]
        payload = {"model": self.model, "messages": messages, "stream": False}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._build_headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
        except Exception as e:
            raise AppError(
                code="vision_call_failed",
                message="调用视觉模型失败",
                http_status=502,
                details={"reason": str(e), "base_url": self.base_url, "model": self.model},
            ) from e

        try:
            data = json.loads(body)
        except Exception as e:
            raise AppError(
                code="vision_response_invalid",
                message="视觉模型返回非 JSON",
                http_status=502,
                details={"body_head": body[:2000]},
            ) from e

        choices = data.get("choices", [])
        if not choices or "message" not in choices[0] or "content" not in choices[0]["message"]:
            raise AppError(code="vision_empty_response", message="视觉模型返回为空", http_status=502)

        text = (choices[0]["message"]["content"] or "").strip()
        if not text:
            raise AppError(code="vision_empty_response", message="视觉模型返回为空", http_status=502)
        return text


class OllamaVisionClient(VisionClient):
    def __init__(self, *, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("RAG_VISION_BASE_URL") or "http://localhost:11434").rstrip("/")
        self.model = model or os.getenv("RAG_VISION_MODEL") or "qwen2.5-vl:7b"

    def image_to_markdown(self, image_path: Path) -> str:
        if not image_path.exists() or not image_path.is_file():
            raise AppError(code="image_not_found", message=f"图片不存在: {image_path}", http_status=400)

        img_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        prompt = (
            "请识别这张图片中的文字（如有），并给出简要说明。"
            "只输出 Markdown 纯文本，不要输出代码块，不要输出解释。"
            "若有明确的标题/小节，请使用 #/## 标题。"
        )

        url = f"{self.base_url}/api/generate"
        payload = {"model": self.model, "prompt": prompt, "stream": False, "images": [img_b64]}
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
            raise AppError(
                code="vision_call_failed",
                message="调用视觉模型失败",
                http_status=502,
                details={"reason": str(e), "base_url": self.base_url, "model": self.model},
            ) from e

        try:
            data = json.loads(body)
        except Exception as e:
            raise AppError(
                code="vision_response_invalid",
                message="视觉模型返回非 JSON",
                http_status=502,
                details={"body_head": body[:2000]},
            ) from e

        text = (data.get("response") or "").strip()
        if not text:
            raise AppError(code="vision_empty_response", message="视觉模型返回为空", http_status=502)
        return text
