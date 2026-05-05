"""
懒人同步入口。

用法：
    python scripts/sync.py
    python scripts/sync.py desk-agent
    python scripts/sync.py ticket-agent inc
    python scripts/sync.py desk-agent docs full
    python scripts/sync.py ticket-agent sql
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sync_rag

_MODE_ALIASES = {
    "inc": "incremental",
    "incremental": "incremental",
    "full": "full",
}

_TARGET_ALIASES = {
    "all": "all",
    "docs": "docs",
    "doc": "docs",
    "sql": "sql",
}


def _usage() -> str:
    return (
        "用法:\n"
        "  python scripts/sync.py\n"
        "  python scripts/sync.py desk-agent\n"
        "  python scripts/sync.py ticket-agent inc\n"
        "  python scripts/sync.py desk-agent docs full\n"
        "  python scripts/sync.py ticket-agent sql\n"
    )


def _normalize_cli(argv: list[str]) -> list[str]:
    agent_type = None
    target = "all"
    mode = "incremental"
    args = [arg.lower() for arg in argv[1:]]

    if not args:
        return ["sync_rag.py", "--target", target, "--mode", mode]

    first = args[0]
    if first not in _MODE_ALIASES and first not in _TARGET_ALIASES:
        agent_type = args.pop(0)

    for arg in args:
        if arg in _MODE_ALIASES:
            mode = _MODE_ALIASES[arg]
        elif arg in _TARGET_ALIASES:
            target = _TARGET_ALIASES[arg]
        else:
            raise SystemExit(f"不支持的参数: {arg}\n\n{_usage()}")

    result = ["sync_rag.py", "--target", target, "--mode", mode]
    if agent_type:
        result.extend(["--agent-type", agent_type])
    return result


def main() -> int:
    sys.argv = _normalize_cli(sys.argv)
    return sync_rag.main()


if __name__ == "__main__":
    raise SystemExit(main())
