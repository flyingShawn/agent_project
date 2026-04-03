"""
LLM客户端模块

文件目的：
    - 封装大语言模型调用
    - 支持Ollama本地模型
    - 提供流式和同步两种调用方式
    - 支持模拟响应模式

核心功能：
    1. 流式聊天（chat_stream）
    2. 同步聊天（chat_complete）
    3. 支持多模态（文本+图片）
    4. 自动选择模型（普通/视觉）
    5. 模拟响应模式（Mock）

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
import time
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
        use_mock: bool | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip(
            "/"
        )
        self.model = model or os.getenv("CHAT_MODEL") or "qwen2.5:7b"
        self.vision_model = vision_model or os.getenv("VISION_MODEL") or "qwen2.5-vl:7b"
        self.use_mock = use_mock if use_mock is not None else (os.getenv("USE_MOCK", "false").lower() == "true")
        logger.info(f"【LLM客户端】初始化完成")
        logger.info(f"  - Base URL: {self.base_url}")
        logger.info(f"  - 文本模型: {self.model}")
        logger.info(f"  - 视觉模型: {self.vision_model}")
        logger.info(f"  - Mock模式: {self.use_mock}")

    def _get_mock_response(self, messages: list[dict]) -> str:
        user_message = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_message = msg["content"]
                break
        
        question_lower = user_message.lower()
        
        if "你好" in user_message or "hello" in question_lower or "hi" in question_lower:
            return "你好！我是桌管系统 AI 助手。我可以帮助你：\n\n- 查询设备资产信息\n- 了解策略配置方法\n- 排查常见问题\n- 分析数据统计\n\n请问有什么可以帮你的？"
        
        if "部门" in user_message:
            return "根据系统数据，目前有以下部门：\n\n| 部门名称 | 部门编码 | 负责人 |\n|---------|---------|-------|\n| 研发部 | RND | 张三 |\n| 市场部 | MKT | 李四 |\n| 财务部 | FIN | 王五 |\n| 人事部 | HR | 赵六 |\n| 运维部 | OPS | 钱七 |\n\n共 5 个部门。"
        
        if "设备" in user_message or "机器" in user_message or "在线" in user_message:
            return "查询结果如下：\n\n| IP | 设备名称 | 状态 | 所属部门 | 最后上线 |\n|----|---------|-----|---------|---------|\n| 192.168.1.10 | 研发部-张三-PC | 在线 | 研发部 | 2024-01-15 09:30:00 |\n| 192.168.1.11 | 研发部-李四-PC | 离线 | 研发部 | 2024-01-14 18:45:00 |\n| 192.168.1.20 | 市场部-王五-PC | 在线 | 市场部 | 2024-01-15 08:50:00 |\n\n共查询到 **3** 台设备，其中 **2** 台在线，**1** 台离线。"
        
        if "统计" in user_message or "多少" in user_message:
            return "当前系统统计数据：\n\n- 总设备数：156 台\n- 在线设备：128 台\n- 离线设备：28 台\n- 在线率：82.1%\n\n如需更详细的统计信息，请告诉我具体需要查询什么。"
        
        return "我理解你的问题了。作为桌管系统AI助手，我可以帮你查询设备信息、部门信息、统计数据等。请尝试问一些具体的问题，比如：\n\n- 一共有哪些部门？\n- 有多少设备在线？\n- 研发部有哪些设备？"

    def chat_stream(
        self,
        messages: list[dict],
        *,
        images_base64: list[str] | None = None,
    ) -> Iterator[str]:
        if self.use_mock:
            logger.info("【LLM调用】使用Mock模式")
            response = self._get_mock_response(messages)
            for char in response:
                yield char
                time.sleep(0.02)
            return
        
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
            logger.warning(f"【LLM调用】Ollama调用失败，切换到Mock模式: {type(e).__name__}: {e}")
            response = self._get_mock_response(messages)
            for char in response:
                yield char
                time.sleep(0.02)
        finally:
            logger.info("【LLM调用】结束")
            logger.info("=" * 50)

    def chat_complete(
        self,
        messages: list[dict],
        *,
        images_base64: list[str] | None = None,
    ) -> str:
        if self.use_mock:
            logger.info("【LLM调用】使用Mock模式（chat_complete）")
            return self._get_mock_response(messages)
        
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
            logger.warning(f"【LLM调用】Ollama调用失败，切换到Mock模式: {type(e).__name__}: {e}")
            return self._get_mock_response(messages)

        try:
            data = json.loads(body)
        except Exception as e:
            logger.warning(f"【LLM调用】返回解析失败，切换到Mock模式: {type(e).__name__}: {e}")
            return self._get_mock_response(messages)

        if "message" not in data or "content" not in data["message"]:
            logger.warning(f"【LLM调用】返回内容为空，切换到Mock模式")
            return self._get_mock_response(messages)

        return data["message"]["content"].strip()
