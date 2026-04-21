"""
懒人同步入口。

用法：
    python scripts/sync.py
    python scripts/sync.py inc
    python scripts/sync.py full
    python scripts/sync.py docs
    python scripts/sync.py sql full
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
        "  python scripts/sync.py inc\n"
        "  python scripts/sync.py full\n"
        "  python scripts/sync.py docs\n"
        "  python scripts/sync.py sql inc\n"
    )


def _normalize_cli(argv: list[str]) -> list[str]:
    target = "all"
    mode = "incremental"
    args = [arg.lower() for arg in argv[1:]]

    if not args:
        return ["sync_rag.py", "--target", target, "--mode", mode]

    first = args[0]
    if first in _MODE_ALIASES:
        mode = _MODE_ALIASES[first]
    elif first in _TARGET_ALIASES:
        target = _TARGET_ALIASES[first]
        if len(args) > 1:
            second = args[1]
            if second not in _MODE_ALIASES:
                raise SystemExit(f"不支持的同步模式: {args[1]}\n\n{_usage()}")
            mode = _MODE_ALIASES[second]
    else:
        raise SystemExit(f"不支持的参数: {argv[1]}\n\n{_usage()}")

    return ["sync_rag.py", "--target", target, "--mode", mode]


def main() -> int:
    sys.argv = _normalize_cli(sys.argv)
    return sync_rag.main()


if __name__ == "__main__":
    raise SystemExit(main())
