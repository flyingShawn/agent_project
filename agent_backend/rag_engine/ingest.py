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
    kb_type: Literal["docs", "sql"] = "docs",
) -> IngestResult:
    root = Path(docs_dir)
    if not root.exists() or not root.is_dir():
        raise AppError(code="docs_dir_invalid", message=f"docs_dir 不存在或不是目录: {root}", http_status=400)

    if kb_type == "sql":
        collection = settings.qdrant_sql_collection
    else:
        collection = settings.qdrant_collection

    files = _collect_files(root, settings.allowed_extensions)
    files_scanned = len(files)
    prev = state_store.load()
    next_state = prev.copy()

    embedder = build_default_embedder(settings.embedding_model)
    store = QdrantVectorStore(
        url=settings.qdrant_url,
        path=settings.qdrant_path,
        api_key=settings.qdrant_api_key,
        collection=collection,
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
                "kb_type": kb_type,
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
