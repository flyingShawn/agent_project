"""
RAG 混合检索模块

文件功能：
    实现向量检索与 BM25 关键词检索的加权融合（Hybrid Search），为 RAG 问答和
    SQL 样本检索提供统一的检索入口。

核心作用与设计目的：
    - 向量检索捕获语义相似性，BM25 检索捕获关键词精确匹配
    - 通过 alpha 参数控制两种检索策略的权重配比
    - 先从 Qdrant 获取候选集，再对候选集做 BM25 重排序，避免全库 BM25 计算

主要使用场景：
    - RAG 文档问答：检索与用户问题语义相关的文档片段
    - SQL 样本检索：为 NL2SQL 提供相似 SQL 写法参考

包含的主要类与函数：
    - RetrievedChunk: 检索结果数据结构（文本、来源、标题、混合分数、原始向量分数）
    - BM25: BM25 关键词检索实现，支持中英文混合分词
    - hybrid_search(): 混合检索主函数，融合向量检索与 BM25 检索结果
    - get_rag_settings(): 获取 RAG 文档检索配置
    - get_sql_rag_settings(): 获取 SQL 样本检索配置
    - search_sql_samples(): SQL 样本检索便捷入口

专有技术说明：
    - 向量模型：FastEmbed (BAAI/bge-small-zh-v1.5)，维度 384
    - 向量数据库：Qdrant，使用 COSINE 距离度量
    - BM25 实现：Okapi BM25 算法，参数 k1=1.5, b=0.75
    - 分词策略：中文按单字切分，英文按空格/标点切分
    - 融合公式：combined_score = alpha * vector_score_norm + (1 - alpha) * bm25_score_norm

相关联的调用文件：
    - agent_backend/chat/handlers.py: RAG 问答调用 hybrid_search()
    - agent_backend/sql_agent/service.py: SQL 生成调用 search_sql_samples()
    - agent_backend/rag_engine/qdrant_store.py: Qdrant 向量检索
    - agent_backend/rag_engine/embedding.py: 文本向量化
"""
from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from agent_backend.core.config import load_env_file, get_settings, get_sql_log_full_prompt

load_env_file()

from agent_backend.rag_engine.embedding import EmbeddingModel
from agent_backend.rag_engine.qdrant_store import QdrantVectorStore, SearchResult


import logging

logger = logging.getLogger(__name__)

_embedding_model_cache: dict[str, EmbeddingModel] = {}
_store_cache: dict[str, QdrantVectorStore] = {}


def get_or_create_embedding(model_name: str) -> EmbeddingModel:
    if model_name not in _embedding_model_cache:
        _embedding_model_cache[model_name] = EmbeddingModel(model_name=model_name)
    return _embedding_model_cache[model_name]


def get_or_create_store(
    url: str | None,
    path: str | None,
    api_key: str | None,
    collection: str,
    dim: int,
) -> QdrantVectorStore:
    key = f"{collection}:{path or url}"
    if key not in _store_cache:
        store = QdrantVectorStore(
            url=url, path=path, api_key=api_key, collection=collection, dim=dim,
        )
        store.ensure_collection()
        _store_cache[key] = store
    return _store_cache[key]


@dataclass
class RetrievedChunk:
    """
    检索结果数据结构，表示一个从向量数据库中检索到的文档片段。

    属性：
        text: 文档片段的文本内容
        source_path: 源文件路径
        heading: 片段所属的标题路径（Markdown 标题层级）
        score: 混合检索得分（向量分数与 BM25 分数的加权融合）
        raw_vector_score: 原始向量检索得分（COSINE 相似度）
        metadata: 完整的 Qdrant payload 元数据
    """
    text: str
    source_path: str
    heading: str
    score: float
    raw_vector_score: float
    metadata: dict[str, Any]
    raw_bm25_score: float = 0.0
    vector_score_norm: float = 0.0
    bm25_score_norm: float = 0.0


class BM25:
    """
    Okapi BM25 关键词检索实现，支持中英文混合分词。

    算法原理：
        BM25 是基于词频和文档频率的经典信息检索算法，通过 IDF（逆文档频率）
        和 TF（词频）的变体计算查询与文档的相关性得分。

    参数：
        k1: 词频饱和参数，控制词频对得分的影响程度，默认 1.5
        b: 文档长度归一化参数，控制长文档的惩罚力度，默认 0.75

    专有技术说明：
        - 分词策略：中文按单字切分（\u4e00-\u9fa5），英文按连续字母/数字切分
        - 需先调用 fit() 建立索引，再调用 score() 计算得分
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_freqs: dict[str, int] = {}
        self.doc_len: int = 0
        self.avgdl: float = 0.0
        self.n_docs: int = 0

    def fit(self, documents: list[str]) -> None:
        """
        建立文档索引，计算文档频率和平均文档长度。

        参数：
            documents: 待索引的文档文本列表

        说明：
            - 必须在 score() 之前调用
            - 计算每个 token 在多少个文档中出现（文档频率）
            - 计算所有文档的平均 token 数（avgdl）
        """
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
        """
        计算查询与每个文档的 BM25 相关性得分。

        参数：
            query: 查询文本
            documents: 待评分的文档列表（应与 fit() 使用的列表相同顺序）

        返回：
            list[float]: 每个文档的 BM25 得分，与 documents 列表一一对应

        算法：
            score = Σ IDF(token) * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * doc_len / avgdl))
        """
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
    vector_min_score: float = 0.0,
    log_scores: bool = False,
    log_label: str = "[hybrid_search]",
) -> list[RetrievedChunk]:
    """
    混合检索主函数：融合向量检索与 BM25 关键词检索的加权结果。

    检索流程：
        1. 将查询文本向量化，从 Qdrant 获取 candidate_k 个候选结果
        2. 按 vector_min_score 过滤低分候选
        3. 对候选集建立 BM25 索引并计算 BM25 得分
        4. 分别归一化向量分数和 BM25 分数到 [0, 1] 区间
        5. 加权融合：combined_score = alpha * vector_norm + (1 - alpha) * bm25_norm
        6. 按 combined_score 降序排列，取 top_k 个结果
        7. 过滤低于 min_score 的结果

    参数：
        query_text: 查询文本
        store: Qdrant 向量存储实例
        embedding_model: 向量模型实例
        top_k: 最终返回的最大结果数，默认 5
        candidate_k: 向量检索的候选集大小，默认 30
        alpha: 向量分数权重（0-1），1.0 为纯向量检索，0.0 为纯 BM25，默认 0.7
        min_score: 混合分数最低阈值，低于此值的结果被过滤，默认 0.0
        vector_min_score: 向量分数最低阈值，低于此值的候选被过滤，默认 0.0

    返回：
        list[RetrievedChunk]: 检索结果列表，按混合分数降序排列

    专有技术说明：
        - 向量检索使用 Qdrant query_points API，距离度量为 COSINE
        - BM25 在候选集上实时计算，避免全库扫描
        - 归一化采用 max-min 方式（除以最大值），确保两种分数可比
    """
    query_vector = embedding_model.embed([query_text])[0]

    candidates = store.search(
        query_vector=query_vector,
        limit=candidate_k,
        with_payload=True,
        score_threshold=vector_min_score if vector_min_score > 0 else None,
    )

    if not candidates:
        if log_scores:
            logger.info(
                "\n%s query=%s | candidates=0 | vector_min=%.4f | min_score=%.4f",
                log_label,
                query_text,
                vector_min_score,
                min_score,
            )
        return []

    pre_filter_count = len(candidates)
    candidates = [c for c in candidates if c.score >= vector_min_score]
    if len(candidates) < pre_filter_count:
        logger.info(
            f"\n向量分数预过滤: {pre_filter_count} -> {len(candidates)} "
            f"(vector_min_score={vector_min_score})"
        )

    if not candidates:
        if log_scores:
            logger.info(
                "\n%s query=%s | candidates=0_after_vector_filter | vector_min=%.4f | min_score=%.4f",
                log_label,
                query_text,
                vector_min_score,
                min_score,
            )
        return []

    documents = [c.payload.get("text", "") for c in candidates]
    bm25 = BM25()
    bm25.fit(documents)
    bm25_scores = bm25.score(query_text, documents)

    max_vector_score = max(c.score for c in candidates) if candidates else 1.0
    max_bm25_score = max(bm25_scores) if bm25_scores else 1.0

    combined_results: list[dict[str, Any]] = []
    for i, candidate in enumerate(candidates):
        vector_score_norm = candidate.score / max_vector_score if max_vector_score > 0 else 0.0
        bm25_score_norm = bm25_scores[i] / max_bm25_score if max_bm25_score > 0 else 0.0

        combined_score = alpha * vector_score_norm + (1 - alpha) * bm25_score_norm

        combined_results.append(
            {
                "combined_score": combined_score,
                "candidate": candidate,
                "raw_bm25_score": bm25_scores[i],
                "vector_score_norm": vector_score_norm,
                "bm25_score_norm": bm25_score_norm,
            }
        )

    combined_results.sort(key=lambda x: x["combined_score"], reverse=True)

    if log_scores:
        logger.info(
            "\n%s query=%s | candidates=%s | top_k=%s | alpha=%.2f | vector_min=%.4f | min_score=%.4f",
            log_label,
            query_text,
            len(combined_results),
            top_k,
            alpha,
            vector_min_score,
            min_score,
        )
        for rank, item in enumerate(combined_results, start=1):
            payload = item["candidate"].payload or {}
            source = payload.get("heading") or payload.get("source_path") or "unknown"
            chunk_index = payload.get("chunk_index", "-")
            logger.info(
                "%s %s. source=%s | chunk_index=%s | raw_vector=%.4f | vector_norm=%.4f | bm25_raw=%.4f | bm25_norm=%.4f | combined=%.4f | in_top_k=%s | passed_min_score=%s",
                log_label,
                rank,
                source,
                chunk_index,
                item["candidate"].score,
                item["vector_score_norm"],
                item["raw_bm25_score"],
                item["bm25_score_norm"],
                item["combined_score"],
                "yes" if rank <= top_k else "no",
                "yes" if item["combined_score"] >= min_score else "no",
            )

    results = []
    for item in combined_results[:top_k]:
        score = item["combined_score"]
        candidate = item["candidate"]
        if score < min_score:
            continue
        payload = candidate.payload
        results.append(
            RetrievedChunk(
                text=payload.get("text", ""),
                source_path=payload.get("source_path", ""),
                heading=payload.get("heading", ""),
                score=score,
                raw_vector_score=candidate.score,
                raw_bm25_score=item["raw_bm25_score"],
                vector_score_norm=item["vector_score_norm"],
                bm25_score_norm=item["bm25_score_norm"],
                metadata=payload,
            )
        )

    return results


def get_rag_settings() -> tuple[str, str, str | None, str | None, str, int, float, int, float]:
    rag = get_settings().rag
    return (
        rag.rag_qdrant_url,
        rag.rag_qdrant_path,
        rag.rag_qdrant_api_key,
        rag.rag_qdrant_collection,
        rag.rag_embedding_model,
        rag.rag_top_k,
        rag.rag_vector_min_score,
        rag.rag_candidate_k,
        rag.rag_hybrid_alpha,
    )


def get_sql_rag_settings() -> tuple[str, str, str | None, str | None, str, int, int, float]:
    rag = get_settings().rag
    return (
        rag.rag_qdrant_url,
        rag.rag_qdrant_path,
        rag.rag_qdrant_api_key,
        rag.rag_sql_qdrant_collection,
        rag.rag_embedding_model,
        rag.rag_sql_top_k,
        rag.rag_sql_candidate_k,
        rag.rag_sql_hybrid_alpha,
    )


def search_sql_samples(
    query_text: str,
    *,
    store: QdrantVectorStore | None = None,
    embedding_model: EmbeddingModel | None = None,
    min_score: float = 0.8,
    vector_min_score: float = 0.6,
) -> list[RetrievedChunk]:
    """
    SQL 样本检索便捷入口，为 NL2SQL 提供相似 SQL 写法参考。

    参数：
        query_text: 用户自然语言问题
        store: Qdrant 向量存储实例，为 None 时自动创建（使用 SQL 样本集合）
        embedding_model: 向量模型实例，为 None 时自动创建
        min_score: 混合分数最低阈值，默认 0.8（较高阈值确保 SQL 样本质量）
        vector_min_score: 向量分数最低阈值，默认 0.6

    返回：
        list[RetrievedChunk]: 相似 SQL 样本列表

    专有技术说明：
        - 使用 SQL 专用集合（desk_agent_sql），与文档集合隔离
        - alpha 默认 0.8，偏向向量检索（SQL 语义匹配比关键词更重要）
        - min_score 较高（0.8），确保只返回高度相关的 SQL 样本
    """
    if store is None or embedding_model is None:
        qdrant_url, qdrant_path, qdrant_api_key, collection, embedding_model_name, top_k, candidate_k, alpha = (
            get_sql_rag_settings()
        )

        if embedding_model is None:
            embedding_model = get_or_create_embedding(embedding_model_name)

        if store is None:
            dim = embedding_model.dimension
            store = get_or_create_store(
                url=qdrant_url,
                path=qdrant_path,
                api_key=qdrant_api_key,
                collection=collection,
                dim=dim,
            )
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
        vector_min_score=vector_min_score,
        log_scores=get_sql_log_full_prompt(),
        log_label="[sql_query] [SQL样本得分]",
    )
