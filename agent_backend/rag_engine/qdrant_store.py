"""
Qdrant向量数据库存储模块

文件目的：
    - 封装Qdrant向量数据库操作
    - 提供向量存储、检索、删除功能
    - 支持本地和远程Qdrant服务

核心功能：
    1. 创建和管理collection
    2. 向量数据upsert（插入/更新）
    3. 向量检索（相似度搜索）
    4. 按条件删除向量

主要类：
    - QdrantVectorStore: 向量存储类
    - QdrantPoint: 向量点数据结构
    - SearchResult: 检索结果

主要方法：
    - ensure_collection(): 确保collection存在
    - upsert(): 批量插入/更新向量
    - search(): 向量相似度搜索
    - delete_by_source_path(): 按源文件路径删除
    - delete_by_doc_hash_not_in(): 删除不在指定hash集合中的文档

使用场景：
    - RAG文档向量存储
    - 语义检索

相关文件：
    - agent_backend/rag_engine/ingest.py: 文档导入
    - agent_backend/rag_engine/retrieval.py: 检索
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class QdrantPoint:
    point_id: str
    vector: list[float]
    payload: dict


@dataclass
class SearchResult:
    point_id: str
    score: float
    payload: dict[str, Any]


class QdrantVectorStore:
    def __init__(
        self,
        *,
        url: str,
        path: str | None,
        api_key: str | None,
        collection: str,
        dim: int,
    ) -> None:
        from qdrant_client import QdrantClient

        self._url = url
        self._path = path
        self._api_key = api_key
        self._collection = collection
        self._dim = dim
        if path:
            self._client = QdrantClient(path=path)
        else:
            self._client = QdrantClient(url=url, api_key=api_key)

    @property
    def collection(self) -> str:
        return self._collection

    def ensure_collection(self) -> None:
        from qdrant_client.http.models import Distance, VectorParams

        if self._client.collection_exists(self._collection):
            return
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
        )

    def upsert(self, points: Iterable[tuple[str, list[float], dict]]) -> None:
        from qdrant_client.http.models import PointStruct

        batch = [PointStruct(id=pid, vector=vec, payload=payload) for pid, vec, payload in points]
        self._client.upsert(collection_name=self._collection, points=batch)

    def delete_by_source_path(self, source_path: str) -> None:
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue

        flt = Filter(
            must=[
                FieldCondition(
                    key="source_path",
                    match=MatchValue(value=source_path),
                )
            ]
        )
        self._client.delete(collection_name=self._collection, points_selector=flt)

    def delete_by_doc_hash_not_in(self, alive_hashes: set[str]) -> None:
        from qdrant_client.http.models import FieldCondition, Filter, MatchAny

        if not alive_hashes:
            self._client.delete_collection(collection_name=self._collection)
            self.ensure_collection()
            return
        flt = Filter(
            must_not=[
                FieldCondition(
                    key="doc_hash",
                    match=MatchAny(any=list(alive_hashes)),
                )
            ]
        )
        self._client.delete(collection_name=self._collection, points_selector=flt)

    def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        filter_: dict[str, Any] | None = None,
        with_payload: bool = True,
        score_threshold: float | None = None,
    ) -> list[SearchResult]:
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue

        flt = None
        if filter_:
            conditions = []
            for key, value in filter_.items():
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
            if conditions:
                flt = Filter(must=conditions)

        results = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=limit,
            query_filter=flt,
            with_payload=with_payload,
            score_threshold=score_threshold,
        )

        return [
            SearchResult(
                point_id=str(hit.id),
                score=hit.score,
                payload=hit.payload or {},
            )
            for hit in results.points
        ]
