"""
RAG文档分块模块

文件功能：
    将Markdown文档按标题和段落进行智能分块，生成结构化的Chunk对象。
    分块策略兼顾语义完整性（按标题切分）和向量检索粒度（按段落合并/拆分）。

在系统架构中的定位：
    位于RAG引擎的数据预处理层，被 ingest.py 在文档导入流程中调用。

主要使用场景：
    - 文档导入时对Markdown内容进行分块
    - SQL样本文档分块后过滤有效SQL片段

核心类与函数：
    - Chunk: 分块数据结构，包含文本内容、所属标题和块索引
    - chunk_markdown: 主入口函数，执行标题切分→段落合并→生成Chunk列表
    - _split_by_headings: 按Markdown标题切分为(标题, 正文)列表
    - _split_by_paragraphs: 按段落合并/拆分，控制块大小和重叠

分块策略说明：
    1. 先按Markdown标题（#~######）切分为多个语义段落
    2. 每个段落内按双换行符拆分为子段落
    3. 子段落按max_chars合并，超出时拆分
    4. 相邻块之间保留overlap字符重叠，保证跨块语义连续性

关联文件：
    - agent_backend/rag_engine/ingest.py: 调用 chunk_markdown 进行文档分块
    - agent_backend/rag_engine/settings.py: 提供 chunk_max_chars、chunk_overlap 配置
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """文档分块数据结构

    参数：
        text: 分块文本内容
        heading: 所属标题（空字符串表示无标题的 preamble）
        chunk_index: 全局分块索引，用于生成稳定的向量点ID
    """
    text: str
    heading: str
    chunk_index: int


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _split_by_headings(markdown: str) -> list[tuple[str, str]]:
    """
    按Markdown标题切分文档为(标题, 正文)列表。

    切分规则：
        - 以 #~###### 标题行为分隔点
        - 标题前的内容作为无标题preamble
        - 每个标题到下一个标题之间的内容归入该标题段落
        - 空段落被跳过

    参数：
        markdown: 原始Markdown文本

    返回：
        (标题, 正文) 元组列表，标题为空字符串表示preamble
    """
    parts: list[tuple[str, str]] = []
    matches = list(_HEADING_RE.finditer(markdown))
    if not matches:
        return [("", markdown.strip())]

    if matches[0].start() > 0:
        preamble = markdown[: matches[0].start()].strip()
        if preamble:
            parts.append(("", preamble))

    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        if body:
            parts.append((heading, body))

    return parts


def _split_by_paragraphs(text: str, max_chars: int, overlap: int) -> list[str]:
    """
    按段落合并/拆分文本，控制每块大小在max_chars以内。

    合并策略：
        - 按双换行符拆分为子段落
        - 逐段合并，超出max_chars时开始新块
        - 新块保留前一块末尾overlap字符作为重叠上下文
        - 超长单段落按max_chars硬切分

    参数：
        text: 待分块的文本
        max_chars: 每块最大字符数
        overlap: 相邻块重叠字符数

    返回：
        分块后的文本列表
    """
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 2 <= max_chars:
            if current:
                current += "\n\n" + para
            else:
                current = para
        else:
            if current:
                chunks.append(current)
                if overlap > 0 and len(current) > overlap:
                    current = current[-overlap:] + "\n\n" + para
                else:
                    current = para
            else:
                if len(para) <= max_chars:
                    current = para
                else:
                    for j in range(0, len(para), max_chars - overlap):
                        piece = para[j : j + max_chars]
                        if piece.strip():
                            chunks.append(piece)
                    current = ""

    if current.strip():
        chunks.append(current)

    return chunks


def chunk_markdown(
    markdown: str,
    *,
    max_chars: int = 800,
    overlap: int = 100,
    source_path: str = "",
    split_paragraphs: bool = True,
) -> list[Chunk]:
    """
    Markdown文档分块主入口函数。

    执行流程：
        1. 按标题切分为语义段落
        2. 每个段落内按段落合并/拆分（可选）
        3. 生成带全局索引的Chunk列表

    参数：
        markdown: 原始Markdown文本
        max_chars: 每块最大字符数，默认800
        overlap: 相邻块重叠字符数，默认100
        source_path: 源文件路径，仅用于日志输出
        split_paragraphs: 是否按段落细分，False时每个标题段落作为整块

    返回：
        Chunk对象列表，按chunk_index有序排列
    """
    sections = _split_by_headings(markdown)
    all_chunks: list[Chunk] = []
    idx = 0

    for heading, body in sections:
        if split_paragraphs:
            sub_chunks = _split_by_paragraphs(body, max_chars, overlap)
        else:
            sub_chunks = [body.strip()] if body.strip() else []
        for sc in sub_chunks:
            all_chunks.append(
                Chunk(text=sc, heading=heading, chunk_index=idx)
            )
            idx += 1

    if not all_chunks and markdown.strip():
        all_chunks.append(
            Chunk(text=markdown.strip(), heading="", chunk_index=0)
        )

    logger.info(
        f"\n分块完成: {source_path} -> {len(all_chunks)} 个块"
    )
    return all_chunks
