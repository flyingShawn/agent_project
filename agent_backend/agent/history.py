"""
会话历史管理模块

文件功能：
    管理对话历史的压缩和过滤，解决长会话中历史消息对当前回答的干扰问题。

核心策略：
    1. 滑动窗口：只保留最近N轮对话，超出部分直接丢弃
    2. 历史压缩：窗口内长assistant消息截断为摘要，移除详细数据
    3. 话题感知：检测话题切换时缩小窗口+强制压缩，减少不相关上下文干扰

在系统架构中的定位：
    位于Agent编排层，被chat.py在构建initial_state前调用，
    对从数据库加载的原始历史消息进行智能压缩和过滤。

关联文件：
    - agent_backend/api/v1/chat.py: 调用manage_history()处理历史消息
    - agent_backend/core/config.py: 提供历史管理相关配置
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_STOP_WORDS = {
    "的", "了", "是", "在", "有", "和", "等", "进行", "当前", "最近",
    "查询", "统计", "多少", "哪些", "什么", "如何", "怎么", "请", "帮",
    "我", "你", "给", "看", "下", "一", "个", "这", "那", "要", "能",
    "可以", "需要", "想", "问", "说", "做", "用", "到", "去", "来",
    "中", "里", "上", "前", "后", "时", "天", "年", "月", "日",
    "数量", "记录", "信息", "情况", "数据", "列出", "显示", "查看",
    "分析", "对比", "比较", "汇总", "总结", "报告",
}


def _extract_keywords(text: str) -> set[str]:
    cleaned = re.sub(r'[，。！？、；：\u201c\u201d\u2018\u2019\uff08\uff09\u3010\u3011\s\d]', '', text)
    for sw in _STOP_WORDS:
        cleaned = cleaned.replace(sw, '')
    keywords: set[str] = set()
    for i in range(len(cleaned) - 1):
        keywords.add(cleaned[i:i + 2])
    for i in range(len(cleaned) - 2):
        keywords.add(cleaned[i:i + 3])
    return keywords


def _compute_topic_similarity(q1: str, q2: str) -> float:
    kw1 = _extract_keywords(q1)
    kw2 = _extract_keywords(q2)
    if not kw1 or not kw2:
        return 0.0
    intersection = kw1 & kw2
    union = kw1 | kw2
    return len(intersection) / len(union)


def _compress_assistant_message(content: str, max_chars: int = 200, force: bool = False) -> str:
    if not force and len(content) <= max_chars:
        return content

    lines = content.split('\n')
    summary_parts: list[str] = []
    char_count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if char_count + len(stripped) > max_chars * 0.7:
            break
        if re.match(r'^\|[-:\s|]+\|$', stripped):
            continue
        if stripped.startswith('|') and stripped.count('|') >= 3:
            continue
        if stripped.startswith('```'):
            continue
        summary_parts.append(stripped)
        char_count += len(stripped)

    summary = '\n'.join(summary_parts)
    if len(summary) > max_chars:
        summary = summary[:max_chars]

    if not summary.strip():
        summary = content[:max_chars]

    return f"{summary}\n[...此前回答的详细数据和表格已省略]"


def _group_into_rounds(messages: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    rounds: list[list[dict[str, str]]] = []
    current_round: list[dict[str, str]] = []
    for msg in messages:
        current_round.append(msg)
        if msg["role"] == "assistant":
            rounds.append(current_round)
            current_round = []
    if current_round:
        rounds.append(current_round)
    return rounds


def manage_history(
    history: list[dict[str, str]],
    current_question: str,
    max_rounds: int = 6,
    compress_threshold: int = 500,
    topic_shift_threshold: float = 0.15,
) -> list[dict[str, str]]:
    """
    管理对话历史，返回经过压缩和过滤的消息列表。

    策略：
    1. 按轮次分组（user+assistant为一轮）
    2. 超出窗口的轮次直接丢弃（不再保留压缩版本）
    3. 窗口内：最近2轮保持原样，更早的轮次压缩长assistant消息
    4. 话题切换时：窗口减半，窗口内所有assistant消息强制压缩
    """
    if not history:
        return history

    rounds = _group_into_rounds(history)
    total_rounds = len(rounds)

    last_user_msg = ""
    for msg in reversed(history):
        if msg["role"] == "user":
            last_user_msg = msg["content"]
            break

    is_topic_shift = False
    if last_user_msg and current_question:
        similarity = _compute_topic_similarity(current_question, last_user_msg)
        is_topic_shift = similarity < topic_shift_threshold
        if is_topic_shift:
            logger.info(
                f"\n[history] 检测到话题切换 (相似度={similarity:.2f}): "
                f"上一问='{last_user_msg[:30]}' → 当前='{current_question[:30]}'"
            )

    effective_max_rounds = max(2, max_rounds // 2) if is_topic_shift else max_rounds

    dropped_rounds = max(0, total_rounds - effective_max_rounds)
    keep_rounds = rounds[dropped_rounds:] if dropped_rounds > 0 else rounds

    result: list[dict[str, str]] = []

    for i, round_msgs in enumerate(keep_rounds):
        is_recent = i >= len(keep_rounds) - 2
        for msg in round_msgs:
            if msg["role"] == "assistant":
                if is_recent and not is_topic_shift:
                    result.append(msg)
                elif is_topic_shift:
                    compressed = _compress_assistant_message(
                        msg["content"],
                        max_chars=int(compress_threshold * 0.6),
                        force=True,
                    )
                    result.append({"role": "assistant", "content": compressed})
                else:
                    if len(msg["content"]) > compress_threshold:
                        compressed = _compress_assistant_message(
                            msg["content"], max_chars=int(compress_threshold * 0.6)
                        )
                        result.append({"role": "assistant", "content": compressed})
                    else:
                        result.append(msg)
            else:
                result.append(msg)

    logger.info(
        f"\n[history] 历史管理: 原始{total_rounds}轮/{len(history)}条 → "
        f"丢弃{dropped_rounds}轮, 保留{len(keep_rounds)}轮/{len(result)}条, "
        f"话题切换={'是' if is_topic_shift else '否'}, "
        f"窗口={effective_max_rounds}轮"
    )

    return result
