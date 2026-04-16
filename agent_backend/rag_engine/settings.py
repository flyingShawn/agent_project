from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class RagIngestSettings(BaseSettings):
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
        base = Path(__file__).resolve().parent.parent.parent
        resolved = Path(p)
        if not resolved.is_absolute():
            resolved = base / resolved
        return str(resolved)
