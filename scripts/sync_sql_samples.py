"""
SQL 样本知识库同步脚本。

用法：
    python scripts/sync_sql_samples.py
    python scripts/sync_sql_samples.py --mode full
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_backend.rag_engine.ingest import ingest_directory
from agent_backend.rag_engine.settings import RagIngestSettings
from agent_backend.rag_engine.state import IngestStateStore


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 SQL 样本知识库到向量数据库")
    parser.add_argument("--sql-dir", default=None, help="SQL 目录，默认读取 RAG_SQL_DIR")
    parser.add_argument(
        "--mode",
        choices=["full", "incremental"],
        default="incremental",
        help="同步模式，默认 incremental",
    )
    args = parser.parse_args()

    settings = RagIngestSettings()
    sql_dir = args.sql_dir or settings.resolve_path(settings.sql_dir)

    print(f"SQL 目录: {sql_dir}")
    print(f"向量集合: {settings.qdrant_sql_collection}")
    print(f"同步模式: {args.mode}")
    print()

    state_path = settings.resolve_path(settings.sql_state_path)
    state = IngestStateStore(state_path)
    result = ingest_directory(
        docs_dir=sql_dir,
        settings=settings,
        state_store=state,
        mode=args.mode,
        kb_type="sql",
    )

    print(
        f"同步完成: 扫描={result.files_scanned}, 跳过={result.files_skipped}, "
        f"处理={result.files_processed}, 写入={result.chunks_upserted}"
    )
    if result.errors:
        print(f"错误: {len(result.errors)}")
        for error in result.errors:
            print(f"  - {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
