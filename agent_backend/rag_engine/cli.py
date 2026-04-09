from __future__ import annotations

import argparse

from agent_backend.rag_engine.ingest import ingest_directory
from agent_backend.rag_engine.settings import RagIngestSettings
from agent_backend.rag_engine.state import IngestStateStore


def main() -> int:
    parser = argparse.ArgumentParser(prog="rag-ingest")
    parser.add_argument("--docs-dir", default=None, help="文档知识库目录")
    parser.add_argument("--sql-dir", default=None, help="SQL样本库目录")
    parser.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    args = parser.parse_args()

    settings = RagIngestSettings()

    if args.sql_dir:
        state = IngestStateStore(settings.sql_state_path)
        result = ingest_directory(
            docs_dir=args.sql_dir,
            settings=settings,
            state_store=state,
            mode=args.mode,
            kb_type="sql",
        )
        print(f"[SQL样本库同步] scanned={result.files_scanned}, skipped={result.files_skipped}, upserted={result.chunks_upserted}")
    elif args.docs_dir:
        state = IngestStateStore(settings.state_path)
        result = ingest_directory(
            docs_dir=args.docs_dir,
            settings=settings,
            state_store=state,
            mode=args.mode,
            kb_type="docs",
        )
        print(f"[文档知识库同步] scanned={result.files_scanned}, skipped={result.files_skipped}, upserted={result.chunks_upserted}")
    else:
        docs_state = IngestStateStore(settings.state_path)
        docs_result = ingest_directory(
            docs_dir=settings.docs_dir,
            settings=settings,
            state_store=docs_state,
            mode=args.mode,
            kb_type="docs",
        )
        print(f"[文档知识库同步] scanned={docs_result.files_scanned}, skipped={docs_result.files_skipped}, upserted={docs_result.chunks_upserted}")

        sql_state = IngestStateStore(settings.sql_state_path)
        sql_result = ingest_directory(
            docs_dir=settings.sql_dir,
            settings=settings,
            state_store=sql_state,
            mode=args.mode,
            kb_type="sql",
        )
        print(f"[SQL样本库同步] scanned={sql_result.files_scanned}, skipped={sql_result.files_skipped}, upserted={sql_result.chunks_upserted}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
