"""
文档知识库同步脚本

用法：
    python scripts/sync_docs.py              # 增量同步
    python scripts/sync_docs.py --mode full   # 全量同步
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
    parser = argparse.ArgumentParser(description="同步文档知识库到向量数据库")
    parser.add_argument("--docs-dir", default=None, help="文档目录（默认读取配置）")
    parser.add_argument("--mode", choices=["full", "incremental"], default="full", help="同步模式")
    args = parser.parse_args()

    settings = RagIngestSettings()
    docs_dir = args.docs_dir or settings.resolve_path(settings.docs_dir)

    print(f"文档目录: {docs_dir}")
    print(f"向量集合: {settings.qdrant_collection}")
    print(f"同步模式: {args.mode}")
    print()

    state_path = settings.resolve_path(settings.docs_state_path)
    state = IngestStateStore(state_path)
    result = ingest_directory(
        docs_dir=docs_dir,
        settings=settings,
        state_store=state,
        mode=args.mode,
        kb_type="docs",
    )

    print(f"同步完成: 扫描={result.files_scanned}, 跳过={result.files_skipped}, 写入={result.chunks_upserted}")
    if result.errors:
        print(f"错误: {len(result.errors)}")
        for e in result.errors:
            print(f"  - {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
