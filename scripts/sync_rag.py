"""
统一的 RAG 同步脚本。

用法：
    python scripts/sync_rag.py
    python scripts/sync_rag.py --target docs
    python scripts/sync_rag.py --target sql --mode full
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_backend.rag_engine.ingest import ingest_directory
from agent_backend.rag_engine.settings import RagIngestSettings
from agent_backend.rag_engine.state import IngestStateStore


def _run_sync(
    *,
    source_dir: str,
    state_path: str,
    mode: str,
    kb_type: str,
    label: str,
    collection: str,
    settings: RagIngestSettings,
) -> int:
    resolved_source_dir = settings.resolve_path(source_dir)
    resolved_state_path = settings.resolve_path(state_path)

    print(f"{label}目录: {resolved_source_dir}")
    print(f"{label}集合: {collection}")
    print(f"{label}模式: {mode}")
    print()

    state_store = IngestStateStore(resolved_state_path)
    result = ingest_directory(
        docs_dir=resolved_source_dir,
        settings=settings,
        state_store=state_store,
        mode=mode,
        kb_type=kb_type,
    )

    print(
        f"{label}完成: 扫描={result.files_scanned}, 跳过={result.files_skipped}, "
        f"处理={result.files_processed}, 写入={result.chunks_upserted}"
    )
    if result.errors:
        print(f"{label}错误: {len(result.errors)}")
        for error in result.errors:
            print(f"  - {error}")
        return 1

    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="统一同步文档知识库和 SQL 样本知识库")
    parser.add_argument(
        "--target",
        choices=["docs", "sql", "all"],
        default="all",
        help="同步目标，默认 all",
    )
    parser.add_argument("--docs-dir", default=None, help="文档目录，默认读取 RAG_DOCS_DIR")
    parser.add_argument("--sql-dir", default=None, help="SQL 目录，默认读取 RAG_SQL_DIR")
    parser.add_argument(
        "--mode",
        choices=["full", "incremental"],
        default="incremental",
        help="同步模式，默认 incremental",
    )
    args = parser.parse_args()

    settings = RagIngestSettings()
    exit_code = 0

    if args.target in ("docs", "all"):
        exit_code = max(
            exit_code,
            _run_sync(
                source_dir=args.docs_dir or settings.docs_dir,
                state_path=settings.docs_state_path,
                mode=args.mode,
                kb_type="docs",
                label="文档知识库",
                collection=settings.qdrant_collection,
                settings=settings,
            ),
        )

    if args.target in ("sql", "all"):
        exit_code = max(
            exit_code,
            _run_sync(
                source_dir=args.sql_dir or settings.sql_dir,
                state_path=settings.sql_state_path,
                mode=args.mode,
                kb_type="sql",
                label="SQL 样本库",
                collection=settings.qdrant_sql_collection,
                settings=settings,
            ),
        )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
