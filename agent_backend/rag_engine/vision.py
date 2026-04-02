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

        说明：
            - 使用 Ollama /api/generate 的 images 字段传递 base64 图片；
            - 返回值只取 response 文本，不做额外格式化。
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
