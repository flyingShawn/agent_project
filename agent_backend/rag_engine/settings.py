"""
RAG引擎配置模块

文件功能：
    定义RAG引擎的所有配置项，使用pydantic-settings从环境变量和.env文件加载配置。
    涵盖Qdrant连接、Embedding模型、文档目录、分块参数等完整配置。

在系统架构中的定位：
    位于RAG引擎的配置层，被 ingest.py、retrieval.py、api/v1/rag.py 等模块引用。

核心类：
    - RagIngestSettings: RAG导入配置，支持 RAG_ 前缀环境变量覆盖

配置分组：
    - Qdrant连接: qdrant_url, qdrant_path, qdrant_api_key
    - Embedding模型: embedding_model
    - 通用文档库: docs_dir, qdrant_collection, docs_state_path
    - SQL样本库: sql_dir, qdrant_sql_collection, sql_state_path
    - 分块参数: chunk_max_chars, chunk_overlap, supported_extensions

关联文件：
    - agent_backend/rag_engine/ingest.py: 使用配置进行文档导入
    - agent_backend/rag_engine/retrieval.py: 使用配置进行向量检索
    - agent_backend/api/v1/rag.py: 构造配置实例
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class RagIngestSettings(BaseSettings):
    """RAG导入配置

    通过 RAG_ 前缀的环境变量覆盖默认值，如 RAG_QDRANT_URL。
    配置项同时从 .env 文件加载。

    参数：
        qdrant_url: Qdrant服务URL
        qdrant_path: Qdrant本地存储路径（优先于URL模式）
        qdrant_api_key: Qdrant API密钥
        embedding_model: Embedding模型名称，默认BAAI/bge-small-zh-v1.5
        docs_dir: 通用文档目录路径
        qdrant_collection: 通用文档Qdrant集合名
        docs_state_path: 通用文档导入状态文件路径
        sql_dir: SQL样本目录路径
        qdrant_sql_collection: SQL样本Qdrant集合名
        sql_state_path: SQL样本导入状态文件路径
        chunk_max_chars: 每块最大字符数
        chunk_overlap: 相邻块重叠字符数
        supported_extensions: 支持的文件扩展名列表
    """
    qdrant_url: str = "http://localhost:6333"
    qdrant_path: str | None = None
    qdrant_api_key: str | None = None
    embedding_model: str = "BAAI/bge-small-zh-v1.5"

    docs_dir: str = "./data/desk-agent/docs"
    qdrant_collection: str = "desk_agent_docs"
    docs_state_path: str = "./.rag_state/docs_state.json"

    sql_dir: str = "./data/desk-agent/sql"
    qdrant_sql_collection: str = "desk_agent_sql"
    sql_state_path: str = "./.rag_state/sql_state.json"

    chunk_max_chars: int = 800
    chunk_overlap: int = 100
    supported_extensions: list[str] = [".md", ".txt", ".docx", ".xlsx", ".pdf", ".pptx"]

    model_config = {"env_prefix": "RAG_", "env_file": ".env", "extra": "ignore"}

    def resolve_path(self, p: str) -> str:
        """
        将相对路径解析为基于项目根目录的绝对路径。

        参数：
            p: 待解析的路径字符串

        返回：
            绝对路径字符串
        """
        base = Path(__file__).resolve().parent.parent.parent
        resolved = Path(p)
        if not resolved.is_absolute():
            resolved = base / resolved
        return str(resolved)
