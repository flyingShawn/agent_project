from __future__ import annotations

import json
import os
import urllib.request

from agent_backend.core.config_helper import load_env_file
from agent_backend.core.errors import AppError

# 确保加载.env文件
load_env_file()


class LlmClient:
    def generate(self, prompt: str) -> str:
        raise NotImplementedError


class OllamaClient(LlmClient):
    def __init__(self, *, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL") or os.getenv("CHAT_MODEL") or "qwen2.5:7b"

    def generate(self, prompt: str) -> str:
        """
        调用本机 Ollama /api/generate 生成文本。

        说明：
            - 采用 stream=false 一次性返回，便于服务端处理与测试。
        """
        url = f"{self.base_url}/api/generate"
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
        except Exception as e:
            raise AppError(
                code="llm_call_failed",
                message="调用 Ollama 失败",
                http_status=502,
                details={"reason": str(e), "base_url": self.base_url},
            ) from e

        try:
            data = json.loads(body)
        except Exception as e:
            raise AppError(
                code="llm_response_invalid",
                message="Ollama 返回非 JSON",
                http_status=502,
                details={"body_head": body[:2000]},
            ) from e

        text = (data.get("response") or "").strip()
        if not text:
            raise AppError(
                code="llm_empty_response",
                message="大模型返回为空",
                http_status=502,
            )
        return text


class DummyClient(LlmClient):
    def __init__(self, sql: str = "SELECT 1") -> None:
        self.sql = sql

    def generate(self, prompt: str) -> str:
        return self.sql
