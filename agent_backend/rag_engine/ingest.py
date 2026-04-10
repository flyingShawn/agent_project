"""
RAG 文档导入模块

文件功能：
    将文档目录中的文件解析、分块、向量化并写入 Qdrant 向量数据库，
    支持全量和增量两种同步模式。

核心作用与设计目的：
    - 全量模式：重新处理所有文件，并删除已不存在文件的向量数据
    - 增量模式：基于文件 SHA-256 指纹跳过未变更文件，仅处理新增或修改的文件
    - 文件变更时自动删除旧向量数据后重新入库

主要使用场景：
    - RAG 知识库同步 API (/api/v1/rag/sync) 的核心执行逻辑
    - CLI 命令行工具的文档导入
    - CI/CD 流程中的知识库自动更新

包含的主要函数：
    - ingest_directory(): 文档导入主入口，编排解析→分块→向量化→入库全流程
    - _collect_files(): 递归收集目录中符合扩展名过滤的文件列表
    - _fingerprint(): 计算文件的 SHA-256 哈希指纹
    - _stable_id(): 基于文件路径+哈希+索引生成稳定的向量点 ID

相关联的调用文件：
    - agent_backend/api/v1/rag.py: 通过 API 触发文档同步
    - agent_backend/rag_engine/cli.py: 通过 CLI 触发文档同步
    - agent_backend/rag_engine/docling_parser.py: 文档解析
    - agent_backend/rag_engine/chunking.py: Markdown 分块
    - agent_backend/rag_engine/embedding.py: 文本向量化
    - agent_backend/rag_engine/qdrant_store.py: 向量数据库操作
    - agent_backend/rag_engine/state.py: 增量同步状态管理
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
    kb_type: Literal["docs", "sql"] = "docs",
) -> IngestResult:
    """
    文档导入主入口，编排解析→分块→向量化→入库全流程。

    处理流程：
        1. 校验文档目录有效性
        2. 根据 kb_type 选择 Qdrant 集合（文档集合或 SQL 样本集合）
        3. 递归收集目录中所有符合扩展名过滤的文件
        4. 初始化向量化器和 Qdrant 存储实例
        5. 逐文件处理：
           a. 计算文件 SHA-256 指纹
           b. 增量模式下跳过指纹未变的文件
           c. 文件变更时删除旧向量数据
           d. 解析文档 → 分块 → 向量化 → upsert 到 Qdrant
        6. 全量模式下删除已不存在文件的向量数据
        7. 保存增量状态

    参数：
        docs_dir: 文档目录路径
        settings: RAG 导入配置
        state_store: 增量状态存储
        mode: 同步模式，"full" 全量或 "incremental" 增量
        kb_type: 知识库类型，"docs" 文档或 "sql" SQL 样本

    返回：
        IngestResult: 导入结果（扫描文件数、跳过文件数、入库分块数）

    异常：
        AppError(400): docs_dir 不存在或不是目录

    性能考量：
        - 文件指纹计算使用流式读取（1MB 分块），避免大文件占用过多内存
        - 向量化使用批量 embed_texts()，减少模型调用开销
    """
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
