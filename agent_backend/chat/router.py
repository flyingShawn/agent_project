"""
意图识别路由模块

文件目的：
    - 识别用户问题的意图类型
    - 决定使用SQL查询还是RAG问答
    - 提供智能路由功能

核心功能：
    1. 关键词匹配
    2. 正则模式匹配
    3. 评分机制
    4. 意图分类

主要函数：
    - classify_intent(): 分类用户意图

分类策略：
    1. 优先匹配正则模式
       - SQL模式：IP地址、数量统计、时间范围等
       - RAG模式：如何、为什么、排查问题等
    
    2. 关键词评分
       - SQL关键词：查询、统计、多少、设备等
       - RAG关键词：怎么、如何、为什么、配置等
    
    3. 选择得分高的意图
       - SQL得分高 -> Intent.SQL
       - RAG得分高 -> Intent.RAG
       - 相等 -> 默认SQL

使用场景：
    - 聊天API的意图识别
    - 多模式问答路由

相关文件：
    - agent_backend/chat/types.py: 意图类型定义
    - agent_backend/chat/handlers.py: 聊天处理器
"""
from __future__ import annotations

import logging
import re

from agent_backend.chat.types import Intent

logger = logging.getLogger(__name__)


SQL_KEYWORDS = [
    "查询",
    "统计",
    "多少",
    "几个",
    "多少个",
    "在线数",
    "多少台",
    "告警",
    "某IP",
    "某个IP",
    "IP为",
    "mtid",
    "资产",
    "设备",
    "机器",
    "开机率",
    "登录",
    "USB",
    "禁用",
    "启用",
    "变更",
    "趋势",
    "部门",
    "组织",
    "用户",
    "员工",
]

RAG_KEYWORDS = [
    "怎么",
    "如何",
    "为什么",
    "原因",
    "怎么回事",
    "流程",
    "方案",
    "解释",
    "设置",
    "配置",
    "排查",
    "水印",
    "远程连接",
    "操作手册",
    "文档",
]

SQL_PATTERNS = [
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
    r"(多少|几台|数量|统计|查询).*(机器|设备|在线|告警)",
    r"(最近|今日|昨日|本周|本月).*(登录|开机|告警|变更)",
]

RAG_PATTERNS = [
    r"(怎么|如何).*(设置|配置|操作)",
    r"(为什么|原因|怎么回事)",
    r"(排查|解决|处理).*(问题|故障)",
]


def classify_intent(question: str) -> Intent:
    logger.info(f"【意图识别】开始分析问题: {question}")
    question_lower = question.lower()

    for pattern in SQL_PATTERNS:
        if re.search(pattern, question):
            logger.info(f"【意图识别】匹配SQL正则模式: {pattern}")
            logger.info(f"【意图识别】结果: SQL")
            return Intent.SQL

    for pattern in RAG_PATTERNS:
        if re.search(pattern, question):
            logger.info(f"【意图识别】匹配RAG正则模式: {pattern}")
            logger.info(f"【意图识别】结果: RAG")
            return Intent.RAG

    sql_score = sum(1 for kw in SQL_KEYWORDS if kw in question_lower)
    rag_score = sum(1 for kw in RAG_KEYWORDS if kw in question_lower)
    
    matched_sql_kw = [kw for kw in SQL_KEYWORDS if kw in question_lower]
    matched_rag_kw = [kw for kw in RAG_KEYWORDS if kw in question_lower]
    
    logger.info(f"【意图识别】关键词评分:")
    logger.info(f"  - SQL关键词匹配: {matched_sql_kw} (得分: {sql_score})")
    logger.info(f"  - RAG关键词匹配: {matched_rag_kw} (得分: {rag_score})")

    if sql_score > rag_score:
        logger.info(f"【意图识别】结果: SQL (SQL得分更高)")
        return Intent.SQL
    elif rag_score > sql_score:
        logger.info(f"【意图识别】结果: RAG (RAG得分更高)")
        return Intent.RAG
    else:
        logger.info(f"【意图识别】结果: RAG (得分相等，默认RAG)")
        return Intent.RAG
