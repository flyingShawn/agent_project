from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class IngestStateStore:
    def __init__(self, state_path: str) -> None:
        self.state_path = Path(state_path)
        self._state: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.state_path.exists():
            try:
                self._state = json.loads(self.state_path.read_text(encoding="utf-8"))
                logger.info(f"\n已加载状态文件: {self.state_path} ({len(self._state)} 条记录)")
            except Exception as e:
                logger.warning(f"\n状态文件加载失败: {e}，使用空状态")
                self._state = {}
        else:
            self._state = {}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self._state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def file_hash(file_path: str | Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def is_changed(self, file_path: str | Path) -> bool:
        fp = str(file_path)
        current = self.file_hash(fp)
        return self._state.get(fp) != current

    def update(self, file_path: str | Path) -> None:
        fp = str(file_path)
        self._state[fp] = self.file_hash(fp)

    def persist(self) -> None:
        self._save()
        logger.info(f"\n状态已持久化: {self.state_path} ({len(self._state)} 条记录)")
