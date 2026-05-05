"""
统一的 RAG 同步脚本。

用法：
    python scripts/sync_rag.py
    python scripts/sync_rag.py --agent-type desk-agent
    python scripts/sync_rag.py --agent-type ticket-agent --target docs
    python scripts/sync_rag.py --agent-type desk-agent --target sql --mode full
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_backend.core.config import load_env_file
from agent_backend.rag_engine.ingest import ingest_directory
from agent_backend.rag_engine.settings import RagIngestSettings
from agent_backend.rag_engine.state import IngestStateStore


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _ensure_docling_available() -> bool:
    try:
        from docling.document_converter import DocumentConverter  # noqa: F401
    except Exception as e:
        print(f"docling不可用: {e}")
        print("请先重建文档同步基础镜像：powershell -ExecutionPolicy Bypass -File docker/build-docling-sync.ps1")
        return False
    return True


def _get_rag_settings_for_agent(agent_type: str) -> tuple[RagIngestSettings, str, str, str, str]:
    load_env_file()
    from agent_backend.agent.registry import get_registry
    registry = get_registry()
    if not registry.has_agent(agent_type):
        raise SystemExit(f"未找到智能体: {agent_type}，可用: {list(registry._agents.keys())}")

    rag_config = registry.get_rag_config(agent_type)
    settings = RagIngestSettings()

    if rag_config.docs_dir:
        settings.docs_dir = rag_config.docs_dir
    if rag_config.docs_collection:
        settings.qdrant_collection = rag_config.docs_collection
    if rag_config.sql_dir:
        settings.sql_dir = rag_config.sql_dir
    if rag_config.sql_collection:
        settings.qdrant_sql_collection = rag_config.sql_collection

    docs_dir = rag_config.docs_dir or settings.docs_dir
    sql_dir = rag_config.sql_dir or settings.sql_dir
    docs_collection = rag_config.docs_collection or settings.qdrant_collection
    sql_collection = rag_config.sql_collection or settings.qdrant_sql_collection

    return settings, docs_dir, sql_dir, docs_collection, sql_collection


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
        "--agent-type",
        default=None,
        help="智能体类型，如 desk-agent、ticket-agent。不指定则从 .env 读取默认配置",
    )
    parser.add_argument(
        "--target",
        choices=["docs", "sql", "all"],
        default="all",
        help="同步目标，默认 all",
    )
    parser.add_argument("--docs-dir", default=None, help="文档目录，覆盖配置文件中的值")
    parser.add_argument("--sql-dir", default=None, help="SQL 目录，覆盖配置文件中的值")
    parser.add_argument(
        "--mode",
        choices=["full", "incremental"],
        default="incremental",
        help="同步模式，默认 incremental",
    )
    args = parser.parse_args()

    if args.agent_type:
        settings, docs_dir, sql_dir, docs_collection, sql_collection = _get_rag_settings_for_agent(args.agent_type)
        print(f"智能体: {args.agent_type}")
    else:
        settings = RagIngestSettings()
        docs_dir = settings.docs_dir
        sql_dir = settings.sql_dir
        docs_collection = settings.qdrant_collection
        sql_collection = settings.qdrant_sql_collection
        print("使用 .env 默认配置")

    exit_code = 0

    if args.target in ("docs", "all") and _truthy_env("RAG_REQUIRE_DOCLING"):
        if not _ensure_docling_available():
            return 1

    if args.target in ("docs", "all"):
        exit_code = max(
            exit_code,
            _run_sync(
                source_dir=args.docs_dir or docs_dir,
                state_path=settings.docs_state_path,
                mode=args.mode,
                kb_type="docs",
                label="文档知识库",
                collection=docs_collection,
                settings=settings,
            ),
        )

    if args.target in ("sql", "all"):
        exit_code = max(
            exit_code,
            _run_sync(
                source_dir=args.sql_dir or sql_dir,
                state_path=settings.sql_state_path,
                mode=args.mode,
                kb_type="sql",
                label="SQL 样本库",
                collection=sql_collection,
                settings=settings,
            ),
        )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
