"""
RAG文档导入核心模块

文件目的：
    - 实现文档导入的核心流程
    - 支持全量和增量两种导入模式
    - 管理文档指纹和状态存储

核心功能：
    1. 扫描文档目录，收集待处理文件
    2. 计算文档指纹（MD5），判断是否需要更新
    3. 解析文档（支持多种格式）
    4. 分块处理（chunking）
    5. 向量化（embedding）
    6. 存储到向量数据库（Qdrant）
    7. 更新状态存储

主要函数：
    - ingest_directory(): 导入目录下的所有文档

导入流程：
    1. 收集文件 -> _collect_files()
    2. 计算指纹 -> _fingerprint()
    3. 判断是否需要更新（增量模式）
    4. 解析文档 -> parse_document()
    5. 分块 -> chunk_markdown()
    6. 向量化 -> embedder.embed_texts()
    7. 存储 -> store.upsert()
    8. 更新状态 -> state_store.save()

相关文件：
    - agent_backend/rag_engine/chunking.py: 文档分块
    - agent_backend/rag_engine/embedding.py: 向量化
    - agent_backend/rag_engine/qdrant_store.py: 向量存储
    - agent_backend/rag_engine/docling_parser.py: 文档解析
    - agent_backend/rag_engine/state.py: 状态存储
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from agent_backend.core.errors import AppError
from agent_backend.rag_engine.chunking import chunk_markdown
from agent_backend.rag_engine.docling_parser import parse_document
from agent_backend.rag_engine.embedding import build_default_embedder
from agent_backend.rag_engine.qdrant_store import QdrantVectorStore
from agent_backend.rag_engine.settings import RagIngestSettings
from agent_backend.rag_engine.state import IngestStateStore

@dataclass(frozen=True)
class IngestResult:
    files_scanned: int
    files_skipped: int
    chunks_upserted: int


def ingest_directory(
    *,
    docs_dir: str,
    settings: RagIngestSettings,
    state_store: IngestStateStore,
    mode: Literal["full", "incremental"] = "incremental",
) -> IngestResult:
    root = Path(docs_dir)
    if not root.exists() or not root.is_dir():
        raise AppError(code="docs_dir_invalid", message=f"docs_dir 不存在或不是目录: {root}", http_status=400)

    files = _collect_files(root, settings.allowed_extensions)
    files_scanned = len(files)
    prev = state_store.load()
    next_state = prev.copy()

    embedder = build_default_embedder(settings.embedding_model)
    store = QdrantVectorStore(
        url=settings.qdrant_url,
        path=settings.qdrant_path,
        api_key=settings.qdrant_api_key,
        collection=settings.qdrant_collection,
        dim=embedder.dim,
    )
    store.ensure_collection()

    files_skipped = 0
    chunks_upserted = 0

    for path in files:
        stat = path.stat()
        fingerprint = _fingerprint(path)

        prev_fp = prev.get(str(path))
        if mode == "incremental" and prev_fp == fingerprint:
            files_skipped += 1
            continue

        if prev_fp and prev_fp != fingerprint:
            store.delete_by_source_path(str(path))

        parsed = parse_document(path, vision_base_url=settings.vision_base_url, vision_model=settings.vision_model)
        chunks = chunk_markdown(
            parsed.markdown,
            max_chars=settings.chunk_max_chars,
            overlap=settings.chunk_overlap_chars,
        )
        if not chunks:
            next_state[str(path)] = fingerprint
            continue

        texts = [c.text for c in chunks]
        emb = embedder.embed_texts(texts)
        points = []
        for i, c in enumerate(chunks):
            chunk_id = _stable_id(str(path), i, fingerprint)
            payload = {
                "source_path": str(path),
                "doc_hash": fingerprint,
                "chunk_index": i,
                "heading": c.heading_path,
                "content_type": parsed.content_type,
                "mtime": int(stat.st_mtime),
                "text": c.text,
            }
            points.append((chunk_id, emb.vectors[i], payload))

        store.upsert(points)
        chunks_upserted += len(points)
        next_state[str(path)] = fingerprint

    if mode == "full":
        alive_hashes = {next_state[str(p)] for p in files if str(p) in next_state}
        store.delete_by_doc_hash_not_in(alive_hashes)

    state_store.save(next_state)
    return IngestResult(
        files_scanned=files_scanned,
        files_skipped=files_skipped,
        chunks_upserted=chunks_upserted,
    )


def _collect_files(root: Path, allowed_exts: Iterable[str]) -> list[Path]:
    allowed = {e.lower().lstrip(".") for e in allowed_exts}
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith("~$"):
            continue
        ext = p.suffix.lower().lstrip(".")
        if ext and ext in allowed:
            out.append(p)
    return sorted(out, key=lambda x: str(x))


def _fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _stable_id(source_path: str, chunk_index: int, doc_hash: str) -> str:
    raw = f"{source_path}::{doc_hash}::{chunk_index}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()
