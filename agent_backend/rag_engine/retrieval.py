from __future__ import annotations

import math
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from collections import Counter
from dataclasses import dataclass
from typing import Any

env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from agent_backend.rag_engine.embedding import EmbeddingModel
from agent_backend.rag_engine.qdrant_store import QdrantVectorStore, SearchResult


@dataclass
class RetrievedChunk:
    text: str
    source_path: str
    heading: str
    score: float
    metadata: dict[str, Any]


class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_freqs: dict[str, int] = {}
        self.doc_len: int = 0
        self.avgdl: float = 0.0
        self.n_docs: int = 0

    def fit(self, documents: list[str]) -> None:
        self.n_docs = len(documents)
        total_len = 0

        for doc in documents:
            tokens = self._tokenize(doc)
            total_len += len(tokens)
            unique_tokens = set(tokens)
            for token in unique_tokens:
                self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1

        self.doc_len = total_len
        self.avgdl = total_len / self.n_docs if self.n_docs > 0 else 0.0

    def _tokenize(self, text: str) -> list[str]:
        text = text.lower()
        tokens = []
        current_token = ""
        
        for char in text:
            if char.isalpha() and not ('\u4e00' <= char <= '\u9fa5'):
                current_token += char
            elif char.isdigit():
                current_token += char
            elif '\u4e00' <= char <= '\u9fa5':
                if current_token:
                    tokens.append(current_token)
                    current_token = ""
                tokens.append(char)
            else:
                if current_token:
                    tokens.append(current_token)
                    current_token = ""
        
        if current_token:
            tokens.append(current_token)
        
        return tokens

    def score(self, query: str, documents: list[str]) -> list[float]:
        query_tokens = self._tokenize(query)
        scores = []

        for doc in documents:
            doc_tokens = self._tokenize(doc)
            score = 0.0
            doc_len = len(doc_tokens)
            token_freqs = Counter(doc_tokens)

            for token in query_tokens:
                if token not in self.doc_freqs:
                    continue

                freq = token_freqs.get(token, 0)
                df = self.doc_freqs[token]
                idf = math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1)

                numerator = freq * (self.k1 + 1)
                denominator = freq + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
                score += idf * numerator / denominator

            scores.append(score)

        return scores


def hybrid_search(
    query_text: str,
    *,
    store: QdrantVectorStore,
    embedding_model: EmbeddingModel,
    top_k: int = 5,
    candidate_k: int = 30,
    alpha: float = 0.7,
    min_score: float = 0.0,
) -> list[RetrievedChunk]:
    query_vector = embedding_model.embed([query_text])[0]

    candidates = store.search(
        query_vector=query_vector,
        limit=candidate_k,
        with_payload=True,
    )

    if not candidates:
        return []

    documents = [c.payload.get("text", "") for c in candidates]
    bm25 = BM25()
    bm25.fit(documents)
    bm25_scores = bm25.score(query_text, documents)

    max_vector_score = max(c.score for c in candidates) if candidates else 1.0
    max_bm25_score = max(bm25_scores) if bm25_scores else 1.0

    combined_results = []
    for i, candidate in enumerate(candidates):
        vector_score_norm = candidate.score / max_vector_score if max_vector_score > 0 else 0.0
        bm25_score_norm = bm25_scores[i] / max_bm25_score if max_bm25_score > 0 else 0.0

        combined_score = alpha * vector_score_norm + (1 - alpha) * bm25_score_norm

        combined_results.append(
            (
                combined_score,
                candidate,
            )
        )

    combined_results.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, candidate in combined_results[:top_k]:
        if score < min_score:
            continue
        payload = candidate.payload
        results.append(
            RetrievedChunk(
                text=payload.get("text", ""),
                source_path=payload.get("source_path", ""),
                heading=payload.get("heading", ""),
                score=score,
                metadata=payload,
            )
        )

    return results


def get_rag_settings() -> tuple[str, str, str | None, str | None, str, int]:
    qdrant_url = os.getenv("RAG_QDRANT_URL", "http://localhost:6333")
    qdrant_path = os.getenv("RAG_QDRANT_PATH")
    qdrant_api_key = os.getenv("RAG_QDRANT_API_KEY")
    collection = os.getenv("RAG_QDRANT_COLLECTION", "desk_agent_docs")
    embedding_model_name = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    top_k = int(os.getenv("RAG_TOP_K", "5"))

    return qdrant_url, qdrant_path, qdrant_api_key, collection, embedding_model_name, top_k


def get_sql_rag_settings() -> tuple[str, str, str | None, str | None, str, int, int, float]:
    qdrant_url = os.getenv("RAG_QDRANT_URL", "http://localhost:6333")
    qdrant_path = os.getenv("RAG_QDRANT_PATH")
    qdrant_api_key = os.getenv("RAG_QDRANT_API_KEY")
    collection = os.getenv("RAG_SQL_QDRANT_COLLECTION", "desk_agent_sql")
    embedding_model_name = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    top_k = int(os.getenv("RAG_SQL_TOP_K", "3"))
    candidate_k = int(os.getenv("RAG_SQL_CANDIDATE_K", "15"))
    alpha = float(os.getenv("RAG_SQL_HYBRID_ALPHA", "0.8"))

    return qdrant_url, qdrant_path, qdrant_api_key, collection, embedding_model_name, top_k, candidate_k, alpha


def search_sql_samples(
    query_text: str,
    *,
    store: QdrantVectorStore | None = None,
    embedding_model: EmbeddingModel | None = None,
    min_score: float = 0.8,
) -> list[RetrievedChunk]:
    if store is None or embedding_model is None:
        qdrant_url, qdrant_path, qdrant_api_key, collection, embedding_model_name, top_k, candidate_k, alpha = (
            get_sql_rag_settings()
        )

        if embedding_model is None:
            embedding_model = EmbeddingModel(model_name=embedding_model_name)

        if store is None:
            dim = embedding_model.dimension
            store = QdrantVectorStore(
                url=qdrant_url,
                path=qdrant_path,
                api_key=qdrant_api_key,
                collection=collection,
                dim=dim,
            )
            store.ensure_collection()
    else:
        top_k = int(os.getenv("RAG_SQL_TOP_K", "3"))
        candidate_k = int(os.getenv("RAG_SQL_CANDIDATE_K", "15"))
        alpha = float(os.getenv("RAG_SQL_HYBRID_ALPHA", "0.8"))

    return hybrid_search(
        query_text=query_text,
        store=store,
        embedding_model=embedding_model,
        top_k=top_k,
        candidate_k=candidate_k,
        alpha=alpha,
        min_score=min_score,
    )
