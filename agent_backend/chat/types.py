"""
聊天类型定义模块

文件目的：
    - 定义聊天相关的数据类型
    - 提供意图枚举
    - 统一类型定义

主要类型：
    - Intent: 意图枚举类型
      - SQL: SQL查询意图
      - RAG: RAG问答意图

使用场景：
    - 意图识别
    - 路由分发

相关文件：
    - agent_backend/chat/router.py: 意图识别
    - agent_backend/chat/handlers.py: 聊天处理
"""
from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    SQL = "sql"
    RAG = "rag"
