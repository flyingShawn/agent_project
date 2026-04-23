"""
SQL 样本章节解析工具。

只负责从 Markdown 样本文件中提取：
1. 检索用文本：标题 + 适用场景
2. 结构化元数据：关键表
3. 完整章节原文：供 prompt 构建时恢复
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from agent_backend.rag_engine.chunking import chunk_markdown


@dataclass(frozen=True)
class SqlSampleSection:
    heading: str
    full_text: str
    search_text: str
    key_tables: list[str]
    chunk_index: int


_KEY_TABLE_SPLIT_RE = re.compile(r"[,，、]")


def _normalize_text(text: str) -> str:
    return text.replace("\\_", "_").strip()


def _extract_prefixed_line(text: str, prefix: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith(f"{prefix}："):
            return line.split("：", 1)[1].strip()
        if line.startswith(f"{prefix}:"):
            return line.split(":", 1)[1].strip()
    return ""


def _extract_key_tables(text: str) -> list[str]:
    table_text = _extract_prefixed_line(text, "关键表")
    if not table_text:
        return []

    tables: list[str] = []
    for part in _KEY_TABLE_SPLIT_RE.split(table_text):
        table_name = _normalize_text(part).strip("`[]\"")
        if table_name:
            tables.append(table_name)
    return tables


def _build_search_text(*, heading: str, scenario: str) -> str:
    parts = [heading.strip()]
    if scenario:
        parts.append(f"适用场景：{scenario}")
    return "\n".join(part for part in parts if part)


def parse_sql_sample_sections(markdown: str, *, source_path: str = "") -> list[SqlSampleSection]:
    """
    将 SQL Markdown 样本按标题解析为章节。

    检索阶段只保留标题和适用场景，避免 SQL 代码、关键表等噪声稀释语义召回。
    完整章节原文仍然保留，供命中后恢复到 prompt 中。
    """
    sections: list[SqlSampleSection] = []

    for chunk in chunk_markdown(markdown, source_path=source_path, split_paragraphs=False):
        heading = (chunk.heading or "").strip()
        full_text = _normalize_text(chunk.text)
        if not heading or not full_text:
            continue

        scenario = _extract_prefixed_line(full_text, "适用场景")
        key_tables = _extract_key_tables(full_text)
        has_sql_block = "```sql" in full_text.lower()

        # 顶部说明等非样本章节直接跳过，只保留真正的 SQL 样本条目。
        if not scenario and not key_tables and not has_sql_block:
            continue

        sections.append(
            SqlSampleSection(
                heading=heading,
                full_text=full_text,
                search_text=_build_search_text(heading=heading, scenario=scenario),
                key_tables=key_tables,
                chunk_index=chunk.chunk_index,
            )
        )

    return sections
