"""
RAG增量导入状态管理模块

文件功能：
    管理文档增量导入的状态，通过文件SHA256哈希值检测文件变更，
    实现只处理新增或修改的文件，跳过未变更文件。

在系统架构中的定位：
    位于RAG引擎的基础设施层，被 ingest.py 在导入流程中调用。

核心类：
    - IngestStateStore: 增量导入状态管理器，基于JSON文件持久化

工作原理：
    1. 启动时从JSON文件加载 {文件路径: SHA256哈希} 映射
    2. 导入前检查文件哈希是否变化（is_changed）
    3. 导入成功后更新文件哈希（update）
    4. 全部完成后持久化到磁盘（persist）

关联文件：
    - agent_backend/rag_engine/ingest.py: 调用状态管理器进行增量导入
    - agent_backend/rag_engine/settings.py: 提供状态文件路径配置
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class IngestStateStore:
    """增量导入状态管理器

    基于文件SHA256哈希值检测文件变更，实现增量导入。
    状态数据以JSON格式持久化到磁盘。

    参数：
        state_path: 状态文件路径（JSON格式）
    """
    def __init__(self, state_path: str) -> None:
        self.state_path = Path(state_path)
        self._state: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """从磁盘加载状态文件，加载失败时使用空状态"""

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
        """将状态数据写入磁盘JSON文件"""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self._state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def file_hash(file_path: str | Path) -> str:
        """
        计算文件的SHA256哈希值。

        参数：
            file_path: 文件路径

        返回：
            SHA256哈希的十六进制字符串
        """
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def is_changed(self, file_path: str | Path) -> bool:
        """
        检查文件是否发生变更。

        参数：
            file_path: 文件路径

        返回：
            True 表示文件已变更或为新文件，False 表示未变更
        """
        fp = str(file_path)
        current = self.file_hash(fp)
        return self._state.get(fp) != current

    def update(self, file_path: str | Path) -> None:
        """
        更新文件哈希记录。

        参数：
            file_path: 文件路径
        """
        fp = str(file_path)
        self._state[fp] = self.file_hash(fp)

    def persist(self) -> None:
        """将当前状态持久化到磁盘"""
        self._save()
        logger.info(f"\n状态已持久化: {self.state_path} ({len(self._state)} 条记录)")
