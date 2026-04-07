from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


class RagIngestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAG_", extra="ignore")

    docs_dir: str = "./data/docs"
    qdrant_url: str = "http://localhost:6333"
    qdrant_path: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection: str = "desk_agent_docs"

    embedding_model: str = "BAAI/bge-small-zh-v1.5"

    chunk_max_chars: int = 1800
    chunk_overlap_chars: int = 200

    state_path: str = "./.state/rag_ingest_state.json"
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
