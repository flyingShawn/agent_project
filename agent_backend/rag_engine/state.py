"""
增量导入状态管理模块

文件功能：
    管理 RAG 文档导入的增量状态，以 JSON 文件持久化每个文件的 SHA-256 指纹，
    用于增量同步时判断文件是否变更。

核心作用与设计目的：
    - 存储文件路径到指纹的映射，支持增量模式下跳过未变更文件
    - 状态文件为 JSON 格式，便于人工检查和调试
    - 自动创建状态文件所在目录

主要使用场景：
    - RAG 文档导入流程中的增量状态读取与保存

包含的主要类：
    - IngestStateStore: 增量状态存储类

相关联的调用文件：
    - agent_backend/rag_engine/ingest.py: 导入流程读写状态
    - agent_backend/api/v1/rag.py: API 端点初始化状态存储
    - agent_backend/rag_engine/cli.py: CLI 工具初始化状态存储
"""
from __future__ import annotations

import json
from pathlib import Path


class IngestStateStore:
    """
    增量导入状态存储，以 JSON 文件持久化文件路径到 SHA-256 指纹的映射。

    状态文件格式：
        {"文件路径1": "sha256指纹1", "文件路径2": "sha256指纹2", ...}
    """

    def __init__(self, path: str) -> None:
        """
        初始化状态存储。

        参数：
            path: 状态文件路径（JSON 格式）
        """
        self._path = Path(path)

    def load(self) -> dict[str, str]:
        """
        加载状态文件，返回文件路径到指纹的映射。

        返回：
            dict[str, str]: 文件路径 → SHA-256 指纹映射；
                文件不存在或格式错误时返回空字典

        说明：
            - 仅保留键和值均为字符串的条目，过滤非法数据
        """
        if not self._path.exists():
            return {}
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        out: dict[str, str] = {}
        for k, v in data.items():
            if isinstance(k, str) and isinstance(v, str):
                out[k] = v
        return out

    def save(self, state: dict[str, str]) -> None:
        """
        保存状态到 JSON 文件。

        参数：
            state: 文件路径 → SHA-256 指纹映射

        说明：
            - 自动创建状态文件所在目录
            - 使用 UTF-8 编码和缩进格式写入，便于人工查看
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
