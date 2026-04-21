"""
SSE（Server-Sent Events）流式响应工具模块

文件功能：
    提供SSE事件格式化函数，将事件名和数据编码为SSE协议文本格式。
    用于Agent聊天流式响应、实时数据推送等场景。

在系统架构中的定位：
    位于基础设施层的响应工具层，被 api/v1/chat.py 等流式API调用。

核心函数：
    - sse_event: 将事件名和数据格式化为SSE协议文本

SSE协议说明：
    每个事件由 event: 和 data: 行组成，以空行分隔。
    多行数据每行都需要 data: 前缀。

关联文件：
    - agent_backend/api/v1/chat.py: 聊天流式响应使用SSE
"""
import json


def sse_event(event: str, data: str | dict) -> str:
    """
    将事件名和数据格式化为SSE协议文本。

    参数：
        event: SSE事件名称（如 "message"、"tool_call"、"error"）
        data: 事件数据，字符串或字典（字典自动序列化为JSON）

    返回：
        符合SSE协议格式的文本，包含event行、data行和结束空行
    """
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False)
    lines = data.split("\n")
    return f"event: {event}\n" + "".join(f"data: {line}\n" for line in lines) + "\n"
