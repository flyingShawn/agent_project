from __future__ import annotations

import argparse

from agent_backend.rag_engine.ingest import ingest_directory
from agent_backend.rag_engine.settings import RagIngestSettings
from agent_backend.rag_engine.state import IngestStateStore


def main() -> int:
    parser = argparse.ArgumentParser(prog="rag-ingest")
    parser.add_argument("--docs-dir", default=None)
    parser.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    args = parser.parse_args()

    settings = RagIngestSettings()
    state = IngestStateStore(settings.state_path)
    result = ingest_directory(
        docs_dir=args.docs_dir or settings.docs_dir,
        settings=settings,
        state_store=state,
        mode=args.mode,
    )
    print(
        {
            "files_scanned": result.files_scanned,
            "files_skipped": result.files_skipped,
            "chunks_upserted": result.chunks_upserted,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
