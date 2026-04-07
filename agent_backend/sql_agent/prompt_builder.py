"""
SQL生成Prompt构建器

文件目的：
    - 构建用于Text-to-SQL的提示词
    - 包含schema信息、few-shot样例
    - 提供生成约束和指导

核心功能：
    1. 提取schema摘要
    2. 选择相关的few-shot样例
    3. 组装完整的prompt
    4. 添加安全约束指令

主要函数：
    - build_sql_prompt(): 构建SQL生成prompt
    - select_few_shots(): 选择few-shot样例

Prompt组成：
    1. 角色定义：数据库SQL助手
    2. Schema信息：表、列、语义键
    3. 同义词映射：业务术语
    4. Few-shot样例：相似问题和SQL
    5. 约束指令：安全规则

使用场景：
    - LLM SQL生成
    - Text-to-SQL应用

相关文件：
    - agent_backend/sql_agent/service.py: SQL生成服务
    - agent_backend/core/config_loader.py: Schema配置
"""
from __future__ import annotations

import re
from typing import Any

from agent_backend.core.config_loader import SchemaRuntime


def _shot_score(question: str, shot_query: str) -> int:
    q = question.lower()
    s = shot_query.lower()
    score = 0
    for token in ["告警", "硬件", "策略", "部门", "用户", "在线", "ip", "mtid", "设备"]:
        if token in q and token in s:
            score += 3
    for ch in set(q):
        if ch and ch in s:
            score += 1
    return score


def select_few_shots(runtime: SchemaRuntime, question: str, *, k: int = 3) -> list[dict[str, Any]]:
    shots = runtime.raw.sql_shots or []
    ranked = sorted(shots, key=lambda x: _shot_score(question, x.user_query), reverse=True)
    out: list[dict[str, Any]] = []
    for s in ranked[:k]:
        out.append(
            {
                "user_query": s.user_query,
                "sql": s.sql.strip(),
                "requires_permission": s.requires_permission,
            }
        )
    return out


def build_sql_prompt(runtime: SchemaRuntime, question: str) -> str:
    """
    组装用于 Text-to-SQL 的 Prompt（包含 schema 摘要 + few-shot 样例）。

    约束目标：
        - 只生成单条 SELECT
        - 使用 :param 形式参数
        - 表/列命名尽量遵循 schema_metadata.yaml
    """
    naming = runtime.raw.naming
    security = runtime.raw.security

    schema_lines: list[str] = []
    for t in runtime.raw.tables:
        cols = ", ".join([f"{c.name}({c.semantic_key})" for c in t.columns[:30]])
        more = "" if len(t.columns) <= 30 else f" ...(+{len(t.columns) - 30})"
        schema_lines.append(f"- {t.name}: {cols}{more}")

    synonym_lines: list[str] = []
    for k, v in list(runtime.raw.synonyms.items())[:50]:
        synonym_lines.append(f"- {k}: {', '.join(v[:8])}")

    restricted = ", ".join(security.restricted_tables) if security else ""
    denied_cols = ", ".join(security.deny_select_columns) if security else ""
    quote = naming.identifier_quote if naming else None

    shots = select_few_shots(runtime, question, k=3)
    shot_block = "\n".join(
        [
            f"用户问：{s['user_query']}\nSQL：{s['sql']}\n"
            for s in shots
        ]
    ).strip()

    instructions = [
        "你是一个严谨的数据库 SQL 助手。",
        "只输出 SQL 本体，不要输出解释、不要 Markdown。",
        "只使用 SELECT 语句，禁止 INSERT/UPDATE/DELETE/DROP 等。",
        "禁止使用受限表；禁止返回敏感列。",
        "SQL 参数使用 :param 形式（例如 :ip, :limit）。",
        "",
        "【重要】表别名规则（必须严格遵守）：",
        "1. 定义别名后，整个SQL中必须使用别名，不能再用原表名",
        "2. 示例：FROM s_group g 之后，必须用 g.id，不能用 s_group.id",
        "3. 常用别名：s_machine 用 m，s_group 用 g，s_user 用 u，admininfo 用 a",
        "4. 其他表用单字母别名，且全程保持一致",
        "",
        "【重要】SQL生成原则：",
        "1. 优先使用简单的SQL，避免不必要的子查询",
        "2. 如果只是统计数量，用 SELECT COUNT(*) FROM 表名 即可",
        "3. 如果只是查询所有某个表数据，用 SELECT * FROM 表名 即可",
        # "4. 只有在需要关联多表时才使用 JOIN",
        "",
        "当涉及权限过滤时，WHERE 中使用 m.Groupid 并保留占位 {allowed_group_ids_sql}（由后续权限包装器展开）。",
    ]
    if quote:
        instructions.append(f"数据库标识符引用符是 {quote}，仅在必要时使用。")

    prompt = "\n".join(
        [
            "\n".join(instructions),
            "",
            f"受限表: {restricted}" if restricted else "受限表: 无",
            f"敏感列(禁止返回): {denied_cols}" if denied_cols else "敏感列(禁止返回): 无",
            "",
            "数据库表与列(列后括号为 semantic_key)：",
            "\n".join(schema_lines),
            "",
            "同义词(部分)：",
            "\n".join(synonym_lines) if synonym_lines else "- 无",
            "",
            "Few-shot 示例：",
            shot_block if shot_block else "(无)",
            "",
            f"用户问题：{question}",
            "SQL：",
        ]
    )
    return re.sub(r"\n{3,}", "\n\n", prompt).strip() + "\n"
