from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from agent_backend.core.errors import AppError
from agent_backend.rag_engine.vision import OllamaVisionClient, VisionClient


@dataclass(frozen=True)
class ParsedDoc:
    source_path: str
    markdown: str
    content_type: str


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def parse_documents(paths: Iterable[Path], *, vision_base_url: str | None = None, vision_model: str | None = None) -> list[ParsedDoc]:
    docs: list[ParsedDoc] = []
    for p in paths:
        docs.append(parse_document(p, vision_base_url=vision_base_url, vision_model=vision_model))
    return docs


def parse_document(path: Path, *, vision_base_url: str | None = None, vision_model: str | None = None) -> ParsedDoc:
    content_type = _guess_content_type(path)
    suffix = path.suffix.lower()

    if suffix in {".md", ".txt"}:
        md = path.read_text(encoding="utf-8", errors="ignore").strip()
        if suffix == ".txt":
            md = f"```\n{md}\n```" if md else ""
        return ParsedDoc(source_path=str(path), markdown=md, content_type=content_type)

    if suffix in _IMAGE_SUFFIXES:
        md = ""
        if _has_docling():
            try:
                md = _parse_with_docling(path)
            except Exception:
                md = ""
        if not md:
            md = _parse_image_with_vision(
                path,
                client=OllamaVisionClient(base_url=vision_base_url, model=vision_model),
            )
        return ParsedDoc(source_path=str(path), markdown=(md or "").strip(), content_type=content_type)

    if _has_docling():
        md = _parse_with_docling(path)
        return ParsedDoc(source_path=str(path), markdown=(md or "").strip(), content_type=content_type)

    raise AppError(code="docling_unavailable", message="Docling 未安装或不可用，请先安装依赖后再解析文档", http_status=500)


def _guess_content_type(path: Path) -> str:
    ctype, _ = mimetypes.guess_type(str(path))
    return ctype or "application/octet-stream"


def _has_docling() -> bool:
    try:
        import docling  # noqa: F401

        return True
    except Exception:
        return False


def _parse_with_docling(path: Path) -> str:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(path))
    doc = result.document
    return (doc.export_to_markdown() or "").strip()


def _parse_image_with_vision(path: Path, *, client: VisionClient) -> str:
    md = client.image_to_markdown(path)
    title = path.name
    return f"# {title}\n\n{md}".strip()
