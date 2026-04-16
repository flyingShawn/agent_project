from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_backend.rag_engine.chunking import Chunk, chunk_markdown
from agent_backend.rag_engine.embedding import EmbeddingModel
from agent_backend.rag_engine.qdrant_store import QdrantVectorStore
from agent_backend.rag_engine.settings import RagIngestSettings
from agent_backend.rag_engine.state import IngestStateStore

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    files_scanned: int = 0
    files_skipped: int = 0
    files_processed: int = 0
    chunks_upserted: int = 0
    errors: list[str] = field(default_factory=list)


def _collect_files(docs_dir: str, extensions: list[str]) -> list[Path]:
    base = Path(docs_dir)
    if not base.exists():
        logger.warning(f"\n目录不存在: {docs_dir}")
        return []
    ext_set = {e.lower() for e in extensions}
    files = sorted(
        f for f in base.rglob("*") if f.is_file() and f.suffix.lower() in ext_set
    )
    return files


def _parse_file(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in (".md", ".txt"):
        return file_path.read_text(encoding="utf-8", errors="replace")

    if suffix in (".docx", ".xlsx", ".pdf"):
        try:
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()
            result = converter.convert(str(file_path))
            return result.document.export_to_markdown()
        except ImportError:
            logger.warning(f"\ndocling未安装，跳过文件: {file_path}")
            return ""
        except Exception as e:
            logger.warning(f"\nDocling解析失败 {file_path}: {e}")
            try:
                return file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return ""

    logger.warning(f"\n不支持的文件格式: {file_path}")
    return ""


def _stable_id(file_path: str, chunk_index: int) -> str:
    raw = f"{file_path}:{chunk_index}"
    return str(uuid.UUID(hashlib.md5(raw.encode()).hexdigest()))


def ingest_directory(
    *,
    docs_dir: str,
    settings: RagIngestSettings,
    state_store: IngestStateStore,
    mode: str = "incremental",
    kb_type: str = "docs",
) -> IngestResult:
    result = IngestResult()

    collection = (
        settings.qdrant_sql_collection if kb_type == "sql" else settings.qdrant_collection
    )

    embedding_model = EmbeddingModel(model_name=settings.embedding_model)
    dim = embedding_model.dimension

    store = QdrantVectorStore(
        url=settings.qdrant_url,
        path=settings.qdrant_path,
        api_key=settings.qdrant_api_key,
        collection=collection,
        dim=dim,
    )
    store.ensure_collection()

    files = _collect_files(docs_dir, settings.supported_extensions)
    result.files_scanned = len(files)
    logger.info(f"\n扫描到 {len(files)} 个文件 (目录: {docs_dir})")

    for fp in files:
        fp_str = str(fp)

        if mode == "incremental" and not state_store.is_changed(fp_str):
            logger.info(f"\n跳过未变更文件: {fp.name}")
            result.files_skipped += 1
            continue

        logger.info(f"\n处理文件: {fp.name}")
        markdown = _parse_file(fp)
        if not markdown.strip():
            logger.warning(f"\n文件内容为空，跳过: {fp.name}")
            result.files_skipped += 1
            continue

        chunks = chunk_markdown(
            markdown,
            max_chars=settings.chunk_max_chars,
            overlap=settings.chunk_overlap,
            source_path=fp.name,
        )

        if not chunks:
            result.files_skipped += 1
            continue

        texts = [c.text for c in chunks]
        try:
            vectors = embedding_model.embed(texts)
        except Exception as e:
            err = f"向量化失败 {fp.name}: {e}"
            logger.error(f"\n{err}")
            result.errors.append(err)
            continue

        points = []
        for chunk, vector in zip(chunks, vectors):
            point_id = _stable_id(fp_str, chunk.chunk_index)
            points.append(
                {
                    "id": point_id,
                    "vector": vector,
                    "payload": {
                        "text": chunk.text,
                        "source_path": fp.name,
                        "heading": chunk.heading,
                        "chunk_index": chunk.chunk_index,
                    },
                }
            )

        try:
            store.upsert(points)
            result.chunks_upserted += len(points)
            result.files_processed += 1
            state_store.update(fp_str)
            logger.info(
                f"\n写入完成: {fp.name} -> {len(points)} 个向量点"
            )
        except Exception as e:
            err = f"Qdrant写入失败 {fp.name}: {e}"
            logger.error(f"\n{err}")
            result.errors.append(err)

    state_store.persist()
    logger.info(
        f"\n同步完成: 扫描={result.files_scanned}, "
        f"跳过={result.files_skipped}, "
        f"处理={result.files_processed}, "
        f"写入={result.chunks_upserted}"
    )
    if result.errors:
        logger.warning(f"\n错误数: {len(result.errors)}")

    return result
