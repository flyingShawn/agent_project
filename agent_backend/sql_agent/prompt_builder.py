from __future__ import annotations

import re

from agent_backend.core.config_loader import SchemaRuntime
from agent_backend.rag_engine.retrieval import RetrievedChunk


def build_sql_prompt(
    runtime: SchemaRuntime,
    question: str,
    *,
    sql_samples: list[RetrievedChunk] | None = None,
) -> str:
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

    shot_block = ""
    if sql_samples:
        shot_parts = []
        for i, sample in enumerate(sql_samples, 1):
            shot_parts.append(f"示例{i}（来源：{sample.heading or sample.source_path}）：\n{sample.text}")
        shot_block = "\n\n".join(shot_parts)

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
        "",
        "当涉及权限过滤时，WHERE 中使用 m.Groupid 并保留占位 {allowed_group_ids_sql}（由后续权限包装器展开）。",
    ]
    if quote:
        instructions.append(f"数据库标识符引用符是 {quote}，仅在必要时使用。")

    prompt_parts = [
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
    ]

    if shot_block:
        prompt_parts.extend([
            "",
            "参考SQL样本（请参考其写法风格和表关联方式，但需根据实际问题调整）：",
            shot_block,
        ])

    prompt_parts.extend([
        "",
        f"用户问题：{question}",
        "SQL：",
    ])

    prompt = "\n".join(prompt_parts)
    return re.sub(r"\n{3,}", "\n\n", prompt).strip() + "\n"
