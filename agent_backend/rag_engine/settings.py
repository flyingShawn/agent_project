from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

AGENT_NAME_DEFAULT = "desk-agent"


def _agent_name_to_dirname(name: str) -> str:
    return name.replace("-", "_")


class RagIngestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAG_", extra="ignore")

    agent_name: str = os.getenv("AGENT_NAME", AGENT_NAME_DEFAULT)

    docs_dir: str = ""
    sql_dir: str = ""

    qdrant_url: str = "http://localhost:6333"
    qdrant_path: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection: str = ""
    qdrant_sql_collection: str = ""

    embedding_model: str = "BAAI/bge-small-zh-v1.5"

    chunk_max_chars: int = 1800
    chunk_overlap_chars: int = 200

    state_path: str = ""
    sql_state_path: str = ""

    allowed_extensions: list[str] = [
        "pdf",
        "docx",
        "pptx",
        "xlsx",
        "md",
        "txt",
        "png",
        "jpg",
        "jpeg",
        "webp",
    ]

    vision_base_url: str = "http://localhost:11434"
    vision_model: str = "qwen2.5-vl:7b"

    def model_post_init(self, __context) -> None:
        dirname = _agent_name_to_dirname(self.agent_name)

        if not self.docs_dir:
            self.docs_dir = f"./data/{self.agent_name}/docs"
        if not self.sql_dir:
            self.sql_dir = f"./data/{self.agent_name}/sql"
        if not self.qdrant_collection:
            self.qdrant_collection = f"{dirname}_docs"
        if not self.qdrant_sql_collection:
            self.qdrant_sql_collection = f"{dirname}_sql"
        if not self.state_path:
            self.state_path = f"./.state/{dirname}_rag_ingest_state.json"
        if not self.sql_state_path:
            self.sql_state_path = f"./.state/{dirname}_rag_sql_ingest_state.json"
