"""
Markdown文档分块模块

文件目的：
    - 将长文档切分成适合检索的小块
    - 保留文档结构信息（标题层级）
    - 支持重叠分块，提高检索效果

核心功能：
    1. 识别Markdown标题结构
    2. 按标题分节处理
    3. 控制分块大小（字符数）
    4. 支持块间重叠（overlap）

主要类：
    - Chunk: 分块数据结构

主要函数：
    - chunk_markdown(): Markdown分块主函数
    - _chunk_plain(): 纯文本分块

分块策略：
    1. 按标题（#）分割文档为多个section
    2. 每个section独立分块
    3. 如果section超过max_chars，按段落分割
    4. 如果段落仍太长，按字符数强制分割
    5. 块之间保留overlap字符，避免信息断裂

使用场景：
    - RAG文档导入前的预处理
    - 长文档检索优化

相关文件：
    - agent_backend/rag_engine/ingest.py: 文档导入主流程
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    heading_path: str | None = None


_heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def chunk_markdown(md: str, *, max_chars: int = 1800, overlap: int = 200) -> list[Chunk]:
    md = (md or "").strip()
    if not md:
        return []

    headings: list[tuple[int, str, int]] = []
    for m in _heading_re.finditer(md):
        level = len(m.group(1))
        title = m.group(2).strip()
        headings.append((level, title, m.start()))

    if not headings:
        return _chunk_plain(md, max_chars=max_chars, overlap=overlap)

    sections: list[tuple[str | None, str]] = []
    for i, (_, title, start) in enumerate(headings):
        end = headings[i + 1][2] if i + 1 < len(headings) else len(md)
        section_text = md[start:end].strip()
        sections.append((title, section_text))

    chunks: list[Chunk] = []
    idx = 0
    for heading, section_text in sections:
        for c in _chunk_plain(section_text, max_chars=max_chars, overlap=overlap):
            chunks.append(Chunk(index=idx, text=c.text, heading_path=heading))
            idx += 1
    return chunks


def _chunk_plain(text: str, *, max_chars: int, overlap: int) -> list[Chunk]:
    parts = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    joined: list[str] = []
    buf = ""
    for p in parts:
        if not buf:
            buf = p
            continue
        if len(buf) + 2 + len(p) <= max_chars:
            buf = f"{buf}\n\n{p}"
        else:
            joined.append(buf)
            buf = p
    if buf:
        joined.append(buf)

    out: list[Chunk] = []
    idx = 0
    for block in joined:
        if len(block) <= max_chars:
            out.append(Chunk(index=idx, text=block))
            idx += 1
            continue
        start = 0
        while start < len(block):
            end = min(len(block), start + max_chars)
            out.append(Chunk(index=idx, text=block[start:end].strip()))
            idx += 1
            if end >= len(block):
                break
            start = max(0, end - overlap)
    return out
