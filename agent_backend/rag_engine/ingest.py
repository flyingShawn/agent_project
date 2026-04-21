"""
RAG文档导入模块

文件功能：
    实现文档目录的扫描、解析、分块、向量化和入库的完整导入流程。
    支持增量导入（基于文件哈希变更检测）和全量导入两种模式。

在系统架构中的定位：
    位于RAG引擎的核心处理层，串联分块(chunking)→向量化(embedding)→存储(qdrant_store)→状态(state)四个子模块。

主要使用场景：
    - API /api/v1/rag/sync 触发文档同步
    - API /api/v1/rag/sql-sync 触发SQL样本同步
    - 定时任务自动同步文档

核心类与函数：
    - IngestResult: 导入结果统计（扫描数、跳过数、处理数、写入数、错误列表）
    - ingest_directory: 导入主函数，执行完整的文档导入流程
    - _is_valid_sql_chunk: SQL样本块有效性过滤
    - _collect_files: 按扩展名递归扫描目录
    - _parse_file: 多格式文件解析（md/txt/docx/xlsx/pdf/pptx）
    - _stable_id: 基于文件路径+块索引生成稳定的UUID

专有技术说明：
    - 文件解析使用 docling 库处理 Office/PDF 格式，需额外安装
    - 增量导入通过 IngestStateStore 基于SHA256文件哈希检测变更
    - SQL知识库模式会额外过滤不含SQL关键字的无效块
    - 向量点ID使用 MD5(文件路径:块索引) 转 UUID 确保稳定且唯一

关联文件：
    - agent_backend/rag_engine/chunking.py: 文档分块
    - agent_backend/rag_engine/embedding.py: 文本向量化
    - agent_backend/rag_engine/qdrant_store.py: Qdrant向量存储
    - agent_backend/rag_engine/settings.py: 导入配置
    - agent_backend/rag_engine/state.py: 增量导入状态管理
    - agent_backend/api/v1/rag.py: REST API 调用入口
"""
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
    """文档导入结果统计

    参数：
        files_scanned: 扫描到的文件总数
        files_skipped: 跳过的文件数（未变更或内容为空）
        files_processed: 成功处理的文件数
        chunks_upserted: 成功写入Qdrant的向量点数
        errors: 处理过程中的错误信息列表
    """
    files_scanned: int = 0
    files_skipped: int = 0
    files_processed: int = 0
    chunks_upserted: int = 0
    errors: list[str] = field(default_factory=list)


def _is_valid_sql_chunk(chunk: Chunk) -> bool:
    """
    判断分块是否包含有效的SQL样本内容。

    过滤规则：
        - 文本长度不足20字符的块视为无效
        - 包含 ```sql 或 SELECT 关键字的块视为有效SQL
        - 包含"关键表"标记的块视为有效
        - 包含"适用场景"且长度>=40的块视为有效

    参数：
        chunk: 待判断的文档分块

    返回：
        True 表示有效SQL样本块，False 表示无效
    """
    text = chunk.text.strip()
    if len(text) < 20:
        return False

    lower_text = text.lower()
    if "```sql" in lower_text or "select" in lower_text:
        return True
    if "关键表：" in text or "关键表:" in text:
        return True
    if "适用场景：" in text and len(text) >= 40:
        return True
    return False


def _collect_files(docs_dir: str, extensions: list[str]) -> list[Path]:
    """
    递归扫描目录，收集指定扩展名的文件。

    参数：
        docs_dir: 文档目录路径
        extensions: 允许的文件扩展名列表（如 [".md", ".txt"]）

    返回：
        匹配文件的Path列表，按路径排序
    """
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
    """
    解析文件内容为Markdown文本。

    支持格式：
        - .md/.txt: 直接读取UTF-8文本
        - .docx/.xlsx/.pdf/.pptx: 使用docling库转换为Markdown

    参数：
        file_path: 文件路径

    返回：
        解析后的Markdown文本，解析失败返回空字符串
    """
    suffix = file_path.suffix.lower()
    if suffix in (".md", ".txt"):
        return file_path.read_text(encoding="utf-8", errors="replace")

    if suffix in (".docx", ".xlsx", ".pdf", ".pptx"):
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
    """
    基于文件路径和块索引生成稳定的UUID。

    使用MD5哈希确保相同文件路径+块索引始终生成相同ID，
    保证增量导入时向量点可被正确覆盖更新。

    参数：
        file_path: 文件路径字符串
        chunk_index: 分块索引

    返回：
        UUID格式的字符串
    """
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
    """
    文档目录导入主函数，执行完整的扫描→解析→分块→向量化→入库流程。

    执行流程：
        1. 初始化Embedding模型和Qdrant存储
        2. 全量模式重置集合，增量模式确保集合存在
        3. 递归扫描目录收集文件
        4. 逐文件处理：增量模式跳过未变更文件
        5. 解析文件→分块→（SQL模式过滤有效块）→向量化→写入Qdrant
        6. 持久化导入状态

    参数：
        docs_dir: 文档目录路径
        settings: RAG导入配置
        state_store: 增量导入状态管理器
        mode: 导入模式，"incremental"（增量）或 "full"（全量）
        kb_type: 知识库类型，"docs"（通用文档）或 "sql"（SQL样本）

    返回：
        IngestResult: 导入结果统计
    """
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
    if mode == "full":
        store.reset_collection()
    else:
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

        if kb_type == "sql":
            before_count = len(chunks)
            chunks = [chunk for chunk in chunks if _is_valid_sql_chunk(chunk)]
            if len(chunks) < before_count:
                logger.info(f"\nSQL样本块过滤: {fp.name} {before_count} -> {len(chunks)}")

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
