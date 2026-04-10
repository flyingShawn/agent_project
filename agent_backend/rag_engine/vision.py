"""
视觉模型客户端模块

文件功能：
    封装 Ollama 视觉模型的 HTTP 调用，将图片通过 OCR/描述转为 Markdown 文本，
    用于 RAG 文档导入时处理图片类文件。

核心作用与设计目的：
    - 定义 VisionClient 抽象基类，便于后续扩展其他视觉模型
    - OllamaVisionClient 实现：调用 Ollama /api/generate 接口，传递 base64 图片
    - 输出纯 Markdown 文本，可直接进入分块和向量化流程

主要使用场景：
    - 文档导入时解析图片文件（png/jpg/jpeg/webp）
    - 作为 Docling 解析失败时的回退方案

包含的主要类：
    - VisionClient: 视觉客户端抽象基类
    - OllamaVisionClient: Ollama 视觉模型客户端实现

专有技术说明：
    - 使用 Ollama /api/generate 接口（非 /api/chat），因为视觉模型需要 images 字段
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


class OllamaVisionClient(VisionClient):
    def __init__(self, *, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("RAG_VISION_BASE_URL") or "http://localhost:11434").rstrip("/")
        self.model = model or os.getenv("RAG_VISION_MODEL") or "qwen2.5-vl:7b"

    def image_to_markdown(self, image_path: Path) -> str:
        """
        调用 Ollama 视觉模型对图片做 OCR/描述，并输出可入库的 Markdown。

        参数：
            image_path: 图片文件路径

        返回：
            str: 视觉模型生成的 Markdown 文本

        异常：
            AppError(400): 图片文件不存在
            AppError(502): 视觉模型调用失败或返回无效

        专有技术说明：
            - 使用 Ollama /api/generate 的 images 字段传递 base64 图片
            - 返回值只取 response 文本，不做额外格式化
            - HTTP 超时 120 秒，适配视觉模型推理耗时
        """
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
