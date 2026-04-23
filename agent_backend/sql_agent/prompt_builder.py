"""
SQL 生成提示词构建模块

文件功能：
    根据数据库 Schema 运行时配置和 RAG 检索的 SQL 样本，
    构建发送给 LLM 的 SQL 生成提示词。通过精简 Schema 信息、
    注入同义词映射和参考样本，引导 LLM 生成准确合规的 SQL。

在系统架构中的定位：
    位于 SQL Agent 的提示词层，被 sql_agent/executor.py 和
    agent/tools/scheduler_tool.py 调用，为 LLM 生成 SQL 提供上下文。

主要使用场景：
    - 用户提问时，构建 SQL 生成提示词
    - 定时任务创建时，为自动生成的 SQL 构建提示词

核心函数：
    - build_sql_prompt(): 构建完整的 SQL 生成提示词
    - _extract_tables_from_samples(): 从 RAG 样本中提取涉及的表名

专有技术说明：
    - Schema 精简策略：当有 RAG 样本时，只包含样本涉及的表和列，
      减少提示词长度，提高 LLM 生成精度
    - 同义词过滤：只展示与当前查询相关的同义词映射
    - 别名规则注入：强制 LLM 遵守表别名和列别名规则
    - 敏感列过滤：在提示词中声明禁止返回的敏感列

关联文件：
    - agent_backend/core/config.py: SchemaRuntime 运行时配置
    - agent_backend/rag_engine/retrieval.py: RetrievedChunk RAG 检索结果
    - agent_backend/sql_agent/executor.py: SQL 执行器（调用方）
    - agent_backend/agent/tools/scheduler_tool.py: 定时任务工具（调用方）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import re

from agent_backend.core.config import (
    SchemaRuntime,
    get_sql_prompt_instructions,
    get_sql_system_prompt,
)
from agent_backend.rag_engine.retrieval import RetrievedChunk
from agent_backend.rag_engine.settings import RagIngestSettings
from agent_backend.rag_engine.sql_samples import parse_sql_sample_sections

SQL_SYSTEM_PROMPT = get_sql_system_prompt()

_COLUMN_REF_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")
_TABLE_ALIAS_RE = re.compile(
    r'\b(?:FROM|JOIN)\s+([`"]?[A-Za-z_][A-Za-z0-9_]*[`"]?)(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?',
    re.IGNORECASE,
)
_RESERVED_ALIAS_TOKENS = {
    "ON", "WHERE", "GROUP", "ORDER", "LIMIT", "HAVING", "LEFT", "RIGHT",
    "INNER", "OUTER", "FULL", "JOIN", "UNION",
}


@dataclass(frozen=True)
class SqlPromptBundle:
    prompt: str
    selected_tables: list[str]
    selected_columns_by_table: dict[str, list[str]]
    synonym_count: int
    sample_count: int
    fallback_used: bool
    sample_tables: list[str] = field(default_factory=list)
    fallback_tables: list[str] = field(default_factory=list)
    fallback_reason: str = ""
    total_columns: int = 0


def _normalize_sql_text(text: str) -> str:
    return text.replace("\\_", "_")


def _normalize_identifier(identifier: str) -> str:
    return identifier.strip().strip("`[]\"").replace("\\_", "_").lower()


def _ordered_table_names(runtime: SchemaRuntime, table_names: set[str]) -> list[str]:
    return [t.name for t in runtime.raw.tables if t.name.lower() in table_names]


def _build_synonym_lookup(runtime: SchemaRuntime) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = {}
    for key, values in (runtime.raw.synonyms or {}).items():
        if "." not in key:
            continue
        table_name, column_name = key.split(".", 1)
        lookup[f"{table_name.lower()}.{column_name.lower()}"] = list(values)
    return lookup


def _question_mentions(question_text: str, candidate: str | None) -> bool:
    if not candidate:
        return False

    normalized = candidate.strip().lower()
    if not normalized:
        return False
    if normalized in question_text:
        return True

    for token in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", normalized):
        if len(token) >= 2 and token in question_text:
            return True
    return False


def _extract_tables_from_samples(samples: list[RetrievedChunk]) -> set[str]:
    """
    从 RAG 检索的 SQL 样本中提取涉及的数据库表名。

    参数：
        samples: RAG 检索返回的 SQL 样本列表

    返回：
        set[str]: 表名集合（小写）

    提取策略：
        1. 从"关键表："标记行中解析逗号分隔的表名
        2. 从 SQL 语法中正则匹配 FROM/JOIN 后的表名
    """
    tables = set()
    for sample in samples:
        metadata = sample.metadata or {}
        for table_name in metadata.get("key_tables", []) or []:
            normalized_table_name = _normalize_identifier(table_name)
            if normalized_table_name:
                tables.add(normalized_table_name)

        text = _normalize_sql_text(sample.text)
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("关键表：") or stripped.startswith("关键表:"):
                table_str = stripped.split("：", 1)[-1].split(":", 1)[-1].strip()
                for t in table_str.split(","):
                    t = _normalize_identifier(t.strip())
                    if t:
                        tables.add(t)
        from_pattern = re.findall(r'\bFROM\s+(\w+)', text, re.IGNORECASE)
        join_pattern = re.findall(r'\bJOIN\s+(\w+)', text, re.IGNORECASE)
        for t in from_pattern + join_pattern:
            tables.add(_normalize_identifier(t))
    return tables


def _extract_table_aliases(text: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    normalized = _normalize_sql_text(text)
    for match in _TABLE_ALIAS_RE.finditer(normalized):
        table_name = _normalize_identifier(match.group(1) or "")
        alias = _normalize_identifier(match.group(2) or "")
        if not table_name:
            continue
        aliases[table_name] = table_name
        if alias and alias.upper() not in _RESERVED_ALIAS_TOKENS:
            aliases[alias] = table_name
    return aliases


def _extract_columns_from_samples(
    runtime: SchemaRuntime,
    samples: list[RetrievedChunk],
    sample_tables: set[str],
) -> dict[str, set[str]]:
    table_column_lookup = {
        t.name.lower(): {c.name.lower(): c.name for c in t.columns}
        for t in runtime.raw.tables
    }
    sample_columns = {table_name: set() for table_name in sample_tables}
    if not sample_tables:
        return sample_columns

    for sample in samples:
        text = _normalize_sql_text(sample.text)
        lower_text = text.lower()
        aliases = _extract_table_aliases(text)
        relevant_tables = {table_name for table_name in aliases.values() if table_name in sample_columns}
        if not relevant_tables:
            relevant_tables = set(sample_tables)

        for alias, column_name in _COLUMN_REF_RE.findall(text):
            table_name = aliases.get(alias.lower())
            if not table_name or table_name not in sample_columns:
                continue
            actual_column = table_column_lookup.get(table_name, {}).get(column_name.lower())
            if actual_column:
                sample_columns[table_name].add(actual_column)

        for table_name in relevant_tables:
            for lower_column_name, actual_column in table_column_lookup.get(table_name, {}).items():
                if re.search(
                    rf"(?<![A-Za-z0-9_]){re.escape(lower_column_name)}(?![A-Za-z0-9_])",
                    lower_text,
                ):
                    sample_columns[table_name].add(actual_column)

    return sample_columns


def _collect_question_columns(
    runtime: SchemaRuntime,
    question: str,
    candidate_tables: set[str],
) -> dict[str, set[str]]:
    question_text = question.lower()
    synonym_lookup = _build_synonym_lookup(runtime)
    matched_columns: dict[str, set[str]] = {table_name: set() for table_name in candidate_tables}

    for table_def in runtime.raw.tables:
        table_name = table_def.name.lower()
        if table_name not in candidate_tables:
            continue

        for column_def in table_def.columns:
            synonym_key = f"{table_name}.{column_def.name.lower()}"
            candidates = [column_def.name, column_def.comment or "", column_def.semantic_key or ""]
            candidates.extend(synonym_lookup.get(synonym_key, []))
            if any(_question_mentions(question_text, value) for value in candidates):
                matched_columns[table_name].add(column_def.name)

    return matched_columns


def _collect_required_columns(
    runtime: SchemaRuntime,
    candidate_tables: set[str],
) -> dict[str, set[str]]:
    required_columns: dict[str, set[str]] = {table_name: set() for table_name in candidate_tables}
    table_column_lookup = {
        t.name.lower(): {c.name.lower(): c.name for c in t.columns}
        for t in runtime.raw.tables
    }

    for table_def in runtime.raw.tables:
        table_name = table_def.name.lower()
        if table_name not in candidate_tables:
            continue

        if table_def.primary_key:
            actual_column = table_column_lookup[table_name].get(table_def.primary_key.lower())
            if actual_column:
                required_columns[table_name].add(actual_column)

        for join_key in table_def.join_keys or []:
            actual_column = table_column_lookup[table_name].get(join_key.lower())
            if actual_column:
                required_columns[table_name].add(actual_column)

    for relationship in runtime.raw.relationships or []:
        for side in (relationship.from_field, relationship.to):
            if "." not in side:
                continue
            table_name, column_name = side.split(".", 1)
            table_key = table_name.lower()
            if table_key not in candidate_tables:
                continue
            actual_column = table_column_lookup.get(table_key, {}).get(column_name.lower())
            if actual_column:
                required_columns[table_key].add(actual_column)

    return required_columns


@lru_cache(maxsize=32)
def _load_sql_sections(source_path: str) -> dict[str, str]:
    settings = RagIngestSettings()
    base_dir = Path(settings.resolve_path(settings.sql_dir))

    candidate_paths = [Path(source_path)]
    candidate_paths.append(base_dir / source_path)
    candidate_paths.append(base_dir / Path(source_path).name)

    file_path = next((path for path in candidate_paths if path.exists()), None)
    if file_path is None:
        return {}

    markdown = file_path.read_text(encoding="utf-8", errors="replace")
    return {
        section.heading: section.full_text
        for section in parse_sql_sample_sections(markdown, source_path=file_path.name)
    }


def _prepare_sql_samples(sql_samples: list[RetrievedChunk]) -> list[RetrievedChunk]:
    prepared: list[RetrievedChunk] = []
    seen: set[tuple[str, str]] = set()

    for sample in sql_samples:
        dedupe_key = (sample.source_path or "", sample.heading or "")
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        metadata = dict(sample.metadata or {})
        full_text = sample.text
        if sample.heading and sample.source_path:
            full_text = _load_sql_sections(sample.source_path).get(sample.heading, sample.text)
            if full_text != sample.text:
                metadata["hydrated_from_source"] = True

        prepared.append(
            RetrievedChunk(
                text=full_text,
                source_path=sample.source_path,
                heading=sample.heading,
                score=sample.score,
                raw_vector_score=sample.raw_vector_score,
                metadata=metadata,
                raw_bm25_score=sample.raw_bm25_score,
                vector_score_norm=sample.vector_score_norm,
                bm25_score_norm=sample.bm25_score_norm,
            )
        )

    return prepared


def build_sql_prompt_bundle(
    runtime: SchemaRuntime,
    question: str,
    *,
    sql_samples: list[RetrievedChunk] | None = None,
) -> SqlPromptBundle:
    naming = runtime.raw.naming
    security = runtime.raw.security

    raw_sql_samples = sql_samples or []
    sql_samples = _prepare_sql_samples(raw_sql_samples)
    available_tables = {t.name.lower() for t in runtime.raw.tables}
    sample_tables = _extract_tables_from_samples(sql_samples) & available_tables if sql_samples else set()
    ordered_sample_tables = _ordered_table_names(runtime, sample_tables)

    fallback_used = False
    fallback_reason = ""
    fallback_tables: list[str] = []

    if sample_tables:
        selected_tables = ordered_sample_tables
        selected_table_keys = {table_name.lower() for table_name in selected_tables}
        sample_columns = _extract_columns_from_samples(runtime, sql_samples, selected_table_keys)
        question_columns = _collect_question_columns(runtime, question, selected_table_keys)
        required_columns = _collect_required_columns(runtime, selected_table_keys)
    else:
        selected_tables = [t.name for t in runtime.raw.tables]
        selected_table_keys = {table_name.lower() for table_name in selected_tables}
        sample_columns = {}
        question_columns = {}
        required_columns = {}
        fallback_used = True
        fallback_reason = "未命中SQL样本或SQL样本未提取到相关表，已回退到全量表结构"

    schema_lines: list[str] = []
    selected_columns_by_table: dict[str, list[str]] = {}
    total_columns = 0
    selected_table_set = set(selected_tables)

    for table_def in runtime.raw.tables:
        if table_def.name not in selected_table_set:
            continue

        display_columns = list(table_def.columns[:30])
        if sample_tables:
            selected_column_names = set(sample_columns.get(table_def.name.lower(), set()))
            selected_column_names.update(question_columns.get(table_def.name.lower(), set()))
            selected_column_names.update(required_columns.get(table_def.name.lower(), set()))

            filtered_columns = [column for column in table_def.columns if column.name in selected_column_names][:30]
            if filtered_columns:
                display_columns = filtered_columns
            else:
                fallback_tables.append(table_def.name)
                fallback_used = True
                if not fallback_reason:
                    fallback_reason = "部分相关表未提取到相关列，已回退到表内前30列"

        selected_columns_by_table[table_def.name] = [column.name for column in display_columns]
        total_columns += len(display_columns)

        cols = ", ".join([f"{column.name}({column.comment or column.semantic_key})" for column in display_columns])
        more = "" if len(table_def.columns) <= len(display_columns) else f" ...(+{len(table_def.columns) - len(display_columns)})"
        desc = f"({table_def.description})" if table_def.description else ""
        schema_lines.append(f"- {table_def.name}{desc}: {cols}{more}")

    related_synonyms: list[str] = []
    synonyms = runtime.raw.synonyms or {}
    if sample_tables:
        selected_column_lookup = {
            table_name.lower(): {column_name.lower() for column_name in column_names}
            for table_name, column_names in selected_columns_by_table.items()
        }
        for key, values in synonyms.items():
            if "." not in key:
                continue
            table_name, column_name = key.split(".", 1)
            table_key = table_name.lower()
            if table_key in selected_table_keys and column_name.lower() in selected_column_lookup.get(table_key, set()):
                related_synonyms.append(f"- {key}: {', '.join(values[:8])}")
    else:
        for key, values in list(synonyms.items())[:50]:
            related_synonyms.append(f"- {key}: {', '.join(values[:8])}")

    if not related_synonyms and sample_tables:
        for key, values in synonyms.items():
            if "." not in key:
                continue
            table_name = key.split(".", 1)[0].lower()
            if table_name in selected_table_keys:
                related_synonyms.append(f"- {key}: {', '.join(values[:8])}")

    if not related_synonyms:
        for key, values in list(synonyms.items())[:50]:
            related_synonyms.append(f"- {key}: {', '.join(values[:8])}")

    denied_cols = ", ".join(security.deny_select_columns) if security else ""
    quote = naming.identifier_quote if naming else None

    shot_block = ""
    if sql_samples:
        shot_parts = []
        for i, sample in enumerate(sql_samples, 1):
            shot_parts.append(f"示例{i}（来源：{sample.heading or sample.source_path}）：\n{sample.text}")
        shot_block = "\n\n".join(shot_parts)

    instructions_text = get_sql_prompt_instructions().strip()
    if quote:
        instructions_text += f"\n数据库标识符引用符是 {quote}，仅在必要时使用。"

    prompt_parts = [
        instructions_text,
        "",
        f"敏感列(禁止返回): {denied_cols}" if denied_cols else "敏感列(禁止返回): 无",
        "",
        "数据库表与列(表后括号为表说明，列后括号为列注释)：",
        "\n".join(schema_lines),
        "",
        "同义词：",
        "\n".join(related_synonyms) if related_synonyms else "- 无",
    ]

    if shot_block:
        prompt_parts.extend([
            "",
            "参考SQL样本（必须严格模仿其写法风格和表关联方式，根据实际问题调整内容）：",
            shot_block,
        ])

    prompt_parts.extend([
        "",
        f"用户问题：{question}",
        "SQL：",
    ])

    prompt = re.sub(r"\n{3,}", "\n\n", "\n".join(prompt_parts)).strip() + "\n"
    return SqlPromptBundle(
        prompt=prompt,
        selected_tables=selected_tables,
        selected_columns_by_table=selected_columns_by_table,
        synonym_count=len(related_synonyms),
        sample_count=len(sql_samples),
        fallback_used=fallback_used,
        sample_tables=ordered_sample_tables,
        fallback_tables=fallback_tables,
        fallback_reason=fallback_reason,
        total_columns=total_columns,
    )


def build_sql_prompt(
    runtime: SchemaRuntime,
    question: str,
    *,
    sql_samples: list[RetrievedChunk] | None = None,
) -> str:
    """
    构建 SQL 生成提示词。

    参数：
        runtime: SchemaRuntime 运行时配置，包含表结构、同义词、安全规则等
        question: 用户的自然语言问题
        sql_samples: RAG 检索的参考 SQL 样本（可选）

    返回：
        str: 完整的提示词字符串，包含指令、Schema、同义词、样本和问题

    构建策略：
        1. 若有 sql_samples，只包含样本涉及的表（精简策略），否则包含所有表
        2. 若精简后无表可展示，回退到包含所有表
        3. 同义词按样本涉及的表过滤，无样本时展示前50条
        4. 注入别名规则、敏感列禁止、字段使用约束等指令
        5. 若有样本，追加"参考SQL样本"段落，要求严格模仿
    """
    return build_sql_prompt_bundle(runtime, question, sql_samples=sql_samples).prompt
