from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SqlGenRequest:
    question: str
    lognum: str
    permission_name: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SqlGenResult:
    sql: str
    params: dict[str, Any]
    used_template: str | None = None
    warnings: list[str] = field(default_factory=list)
