"""
混合检索模块（向量检索 + BM25）

文件目的：
    - 实现混合检索策略（Hybrid Search）
    - 结合向量检索和关键词检索
    - 提供更准确的检索结果

核心功能：
    1. 向量检索（语义相似度）
    2. BM25检索（关键词匹配）
    3. 检索结果融合（RRF算法）
    4. 结果重排序

主要类：
    - BM25: BM25检索算法实现
    - RetrievedChunk: 检索结果数据结构

主要函数：
    - hybrid_search(): 混合检索主函数

检索流程：
    1. 向量检索 -> 获取top-k候选
    2. BM25检索 -> 获取top-k候选
    3. 结果融合 -> RRF算法合并
    4. 返回最终结果

使用场景：
    - RAG查询检索
    - 语义搜索

相关文件：
    - agent_backend/rag_engine/qdrant_store.py: 向量存储
    - agent_backend/rag_engine/embedding.py: 向量化
"""
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
        # 简单的中文分词实现
        # 对于英文和数字，按单词分割
        # 对于中文，按字符分割
        tokens = []
        current_token = ""
        
        for char in text:
            if char.isalpha() and not ('\u4e00' <= char <= '\u9fa5'):
                # 英文，继续积累
                current_token += char
            elif char.isdigit():
                # 数字，继续积累
                current_token += char
            elif '\u4e00' <= char <= '\u9fa5':
                # 中文字符，单独作为一个词
                if current_token:
                    tokens.append(current_token)
                    current_token = ""
                tokens.append(char)
            else:
                # 其他字符，作为分隔符
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
