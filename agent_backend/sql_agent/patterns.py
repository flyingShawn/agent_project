"""
SQL 查询模板匹配模块

文件功能：
    基于 schema_metadata.yaml 中的 query_patterns 配置，对用户问题进行"模板优先"匹配，
    命中时直接返回预定义的 SQL 模板，绕过大模型生成，获得更稳定和安全的 SQL。

核心作用与设计目的：
    - 通过关键字评分机制匹配用户问题与查询模板
    - 自动提取问题中的 IP 地址、数字、limit 等参数填入模板
    - 命中模板时无需调用 LLM，降低延迟和成本
    - 模板 SQL 经过人工审核，安全性更高

主要使用场景：
    - SQL Agent 生成流程的第一步：优先尝试模板匹配
    - 常见查询模式（如"查询某IP设备信息"、"统计在线设备数量"）的快速响应

包含的主要函数：
    - select_query_pattern(): 模板匹配主函数，返回 TemplateMatch 或 None
    - _extract_ip(): 从文本中提取 IP 地址（内部方法）
    - _extract_first_int(): 从文本中提取第一个整数（内部方法）
    - _extract_limit(): 从文本中提取 limit 数值（内部方法）
    - _score_overlap(): 计算问题与模板意图的关键字重叠评分（内部方法）

相关联的调用文件：
    - agent_backend/sql_agent/service.py: SQL 生成流程中调用 select_query_pattern()
    - agent_backend/core/config_loader.py: 提供 SchemaRuntime 和 query_patterns 数据
"""
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
