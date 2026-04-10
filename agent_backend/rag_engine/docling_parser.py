"""
文档解析模块

文件功能：
    将不同格式的文档（docx/xlsx/pdf/md/txt/图片等）统一解析为 Markdown 格式，
    为后续分块和向量化提供标准化的文本输入。

核心作用与设计目的：
    - 支持多种文档格式，通过文件后缀自动选择解析策略
    - 优先使用 Docling 解析器（支持 docx/xlsx/pdf/pptx 等格式）
    - 图片文件先尝试 Docling，失败后回退至 Ollama 视觉模型 OCR
    - md/txt 文件直接读取，txt 文件包裹在代码块中

主要使用场景：
    - RAG 文档导入时的文档解析环节
    - 支持的知识库文件格式：pdf, docx, pptx, xlsx, md, txt, png, jpg, jpeg, webp

包含的主要函数：
    - parse_documents(): 批量解析文档列表
    - parse_document(): 解析单个文档，返回 ParsedDoc
    - _parse_with_docling(): 使用 Docling 库解析文档（内部方法）
    - _parse_image_with_vision(): 使用 Ollama 视觉模型解析图片（内部方法）

专有技术说明：
    - Docling 库（docling/document_converter）：IBM 开源的文档解析库，
      支持 docx/xlsx/pdf/pptx 等格式转为 Markdown
    - Ollama 视觉模型（qwen2.5-vl:7b）：用于图片 OCR 和描述生成

相关联的调用文件：
    - agent_backend/rag_engine/ingest.py: 文档导入时调用 parse_document()
    - agent_backend/rag_engine/vision.py: 图片 OCR 实现
"""
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
    """
    解析单个文档，返回统一的 ParsedDoc 结构。

    解析策略（按文件后缀选择）：
        - .md: 直接读取文本
        - .txt: 读取文本并包裹在代码块中
        - .png/.jpg/.jpeg/.webp: 先尝试 Docling，失败后回退至 Ollama 视觉模型
        - 其他格式（docx/xlsx/pdf/pptx 等）: 使用 Docling 解析

    参数：
        path: 文档文件路径
        vision_base_url: Ollama 视觉模型服务地址（可选）
        vision_model: Ollama 视觉模型名称（可选）

    返回：
        ParsedDoc: 包含 source_path、markdown 和 content_type 的解析结果

    异常：
        AppError(500): 非 md/txt/图片格式且 Docling 不可用时抛出
    """
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
