"""
SQL 样本知识库同步脚本。

用法：
    python scripts/sync_sql_samples.py
    python scripts/sync_sql_samples.py --agent-type desk-agent
    python scripts/sync_sql_samples.py --agent-type ticket-agent --mode full
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_backend.core.config import load_env_file
from agent_backend.rag_engine.ingest import ingest_directory
from agent_backend.rag_engine.settings import RagIngestSettings
from agent_backend.rag_engine.state import IngestStateStore


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 SQL 样本知识库到向量数据库")
    parser.add_argument(
        "--agent-type",
        default=None,
        help="智能体类型，如 desk-agent、ticket-agent。不指定则从 .env 读取默认配置",
    )
    parser.add_argument("--sql-dir", default=None, help="SQL 目录，覆盖配置文件中的值")
    parser.add_argument(
        "--mode",
        choices=["full", "incremental"],
        default="incremental",
        help="同步模式，默认 incremental",
    )
    args = parser.parse_args()

    if args.agent_type:
        load_env_file()
        from agent_backend.agent.registry import get_registry
        registry = get_registry()
        if not registry.has_agent(args.agent_type):
            print(f"未找到智能体: {args.agent_type}，可用: {list(registry._agents.keys())}")
            return 1
        rag_config = registry.get_rag_config(args.agent_type)
        settings = RagIngestSettings()
        if rag_config.sql_dir:
            settings.sql_dir = rag_config.sql_dir
        if rag_config.sql_collection:
            settings.qdrant_sql_collection = rag_config.sql_collection
        sql_dir = args.sql_dir or rag_config.sql_dir or settings.sql_dir
        collection = rag_config.sql_collection or settings.qdrant_sql_collection
        print(f"智能体: {args.agent_type}")
    else:
        settings = RagIngestSettings()
        sql_dir = args.sql_dir or settings.sql_dir
        collection = settings.qdrant_sql_collection

    resolved_sql_dir = settings.resolve_path(sql_dir)

    print(f"SQL 目录: {resolved_sql_dir}")
    print(f"向量集合: {collection}")
    print(f"同步模式: {args.mode}")
    print()

    state_path = settings.resolve_path(settings.sql_state_path)
    state = IngestStateStore(state_path)
    result = ingest_directory(
        docs_dir=resolved_sql_dir,
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
