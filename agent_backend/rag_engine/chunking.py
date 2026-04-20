from __future__ import annotations

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    text: str
    heading: str
    chunk_index: int


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _split_by_headings(markdown: str) -> list[tuple[str, str]]:
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
