from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agent_backend.core.config_loader import SchemaRuntime


_IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_INT_RE = re.compile(r"\b(\d{1,10})\b")


@dataclass(frozen=True)
class TemplateMatch:
    name: str
    sql: str
    requires_permission: str | None
    params: dict[str, Any]


def _extract_ip(text: str) -> str | None:
    m = _IP_RE.search(text)
    return m.group(1) if m else None


def _extract_first_int(text: str) -> int | None:
    m = _INT_RE.search(text)
    return int(m.group(1)) if m else None


def _extract_limit(text: str, *, default: int = 50, max_limit: int = 500) -> int:
    m = re.search(r"(最近|前|top|TOP)\s*(\d{1,4})\s*(条|个|台)?", text)
    if m:
        v = int(m.group(2))
        return max(1, min(max_limit, v))
    return default


def _score_overlap(question: str, intent: str) -> int:
    q = question.strip().lower()
    i = intent.strip().lower()
    score = 0
    for token in ["告警", "硬件", "策略", "部门", "用户", "在线", "IP", "ip", "mtid", "设备"]:
        if token.lower() in q and token.lower() in i:
            score += 2
        elif token.lower() in q and token.lower() in intent:
            score += 1
    for ch in set(q):
        if ch and ch in i:
            score += 1
    return score


def select_query_pattern(runtime: SchemaRuntime, question: str) -> TemplateMatch | None:
    """
    基于 schema_metadata.yaml 的 query_patterns 做一次“模板优先”匹配。

    说明：
        - 这里的匹配策略刻意保持简单：以“少量关键字 + IP/数字提取”为主。
        - 命中模板时可绕开大模型生成，直接得到结构更稳定且更安全的 SQL。
    """
    if not runtime.raw.query_patterns:
        return None

    import logging
    logger = logging.getLogger(__name__)

    best: tuple[int, Any] | None = None
    for p in runtime.raw.query_patterns:
        s = _score_overlap(question, f"{p.name} {p.user_intent}")
        logger.info(f"模板匹配: 名称={p.name}, 用户意图={p.user_intent}, 得分={s}")
        if best is None or s > best[0]:
            best = (s, p)

    if best is None or best[0] < 4:  # 降低最低匹配分，从8降到4
        logger.info(f"最佳匹配得分: {best[0] if best else 0}, 低于最低阈值，不匹配")
        return None

    logger.info(f"选中模板: {best[1].name}, 得分={best[0]}")
    p = best[1]
    params: dict[str, Any] = {}

    ip = _extract_ip(question)
    if ":ip" in p.sql and ip:
        params["ip"] = ip
    if ":limit" in p.sql:
        params["limit"] = _extract_limit(question)

    if ":mtid" in p.sql:
        mtid = _extract_first_int(question)
        if mtid is not None:
            params["mtid"] = mtid

    if ":policy_id" in p.sql:
        policy_id = _extract_first_int(question)
        if policy_id is not None:
            params["policy_id"] = policy_id

    if ":code" in p.sql:
        m = re.search(r"code\s*[:=]?\s*['\"]?([A-Za-z0-9_]+)['\"]?", question, flags=re.I)
        if m:
            params["code"] = m.group(1)

    required_params = set(re.findall(r":([A-Za-z_][A-Za-z0-9_]*)", p.sql))
    if not required_params.issubset(set(params.keys())):
        return None

    return TemplateMatch(
        name=p.name,
        sql=p.sql.strip(),
        requires_permission=p.requires_permission,
        params=params,
    )
