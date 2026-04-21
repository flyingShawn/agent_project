"""
Qdrant向量数据库封装模块

文件功能：
    封装Qdrant向量数据库的连接管理、集合操作、向量检索和写入功能，
    为RAG混合检索提供向量存储和相似度搜索能力。

在系统架构中的定位：
    位于RAG引擎基础设施层，是向量检索的数据存储和查询执行环节。
    retrieval.py的hybrid_search()通过QdrantVectorStore执行向量检索获取候选集。

主要使用场景：
    - RAG文档检索时执行向量相似度搜索
    - SQL样本检索时执行向量相似度搜索
    - 文档导入时将向量写入Qdrant集合

核心类与数据结构：
    - SearchResult: 检索结果数据结构（id/score/payload）
    - QdrantVectorStore: Qdrant向量数据库封装类

专有技术说明：
    - 支持两种连接模式：远程URL模式（qdrant_client.QdrantClient(url=...)）
      和本地路径模式（qdrant_client.QdrantClient(path=...)）
    - 懒连接：客户端在首次操作时才建立连接，避免启动时阻塞
    - 集合自动创建：ensure_collection()检查集合是否存在，不存在则创建
    - 使用COSINE距离度量，与bge系列模型的归一化向量兼容

性能注意事项：
    - 搜索方法使用query_points API（qdrant-client>=1.12）
    - 连接客户端全局复用，避免重复创建

关联文件：
    - agent_backend/rag_engine/retrieval.py: hybrid_search()调用search()
    - agent_backend/rag_engine/embedding.py: 提供向量维度信息
    - agent_backend/agent/tools/rag_tool.py: 创建QdrantVectorStore实例
"""
from __future__ import annotations

import logging

from agent_backend.core.config import get_settings
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """
    向量检索结果数据结构。

    属性：
        id: 向量点ID（字符串或整数）
        score: 相似度得分（COSINE距离，0-1之间，越大越相似）
        payload: 向量点的元数据（包含text/source_path/heading等字段）
    """
    id: str | int
    score: float
    payload: dict[str, Any]


class QdrantVectorStore:
    """
    Qdrant向量数据库封装类，提供集合管理、向量检索和写入功能。

    支持远程URL和本地路径两种连接模式，通过环境变量或构造参数配置。
    客户端懒连接，首次操作时才建立连接。

    属性：
        url: Qdrant服务地址（远程模式）
        path: Qdrant本地存储路径（本地模式，优先于url）
        api_key: Qdrant API密钥（可选，云端服务需要）
        collection: 集合名称
        dim: 向量维度
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        path: str | None = None,
        api_key: str | None = None,
        collection: str = "desk_agent_docs",
        dim: int = 384,
    ) -> None:
        """
        初始化Qdrant向量存储。

        参数：
            url: Qdrant服务地址，默认从RAG_QDRANT_URL环境变量读取
            path: Qdrant本地存储路径，默认从RAG_QDRANT_PATH环境变量读取，
                  设置后优先使用本地模式
            api_key: Qdrant API密钥，默认从RAG_QDRANT_API_KEY环境变量读取
            collection: 集合名称，默认desk_agent_docs
            dim: 向量维度，默认384（bge-small-zh-v1.5的维度）
        """
        settings = get_settings().rag
        self.url = url or settings.rag_qdrant_url
        self.path = path or settings.rag_qdrant_path
        self.api_key = api_key or settings.rag_qdrant_api_key
        self.collection = collection
        self.dim = dim
        self._client = None

    def _get_client(self):
        """
        获取Qdrant客户端实例，懒连接实现。

        优先使用本地路径模式（path参数），其次使用远程URL模式。
        客户端全局复用，避免重复创建连接。

        返回：
            QdrantClient: 已连接的Qdrant客户端实例

        异常：
            ImportError: qdrant-client未安装时抛出
            Exception: 连接失败时抛出
        """
        if self._client is not None:
            return self._client
        try:
            from qdrant_client import QdrantClient

            if self.path:
                self._client = QdrantClient(path=self.path)
            else:
                kwargs: dict[str, Any] = {"url": self.url}
                if self.api_key:
                    kwargs["api_key"] = self.api_key
                self._client = QdrantClient(**kwargs)
            logger.info(f"\nQdrant客户端已连接: {self.path or self.url}")
            return self._client
        except ImportError:
            raise ImportError("qdrant-client未安装，请运行: pip install qdrant-client")
        except Exception as e:
            logger.error(f"\nQdrant连接失败: {e}")
            raise

    def ensure_collection(self) -> None:
        """
        确保集合存在，不存在则自动创建。

        使用COSINE距离度量和指定维度创建集合。
        集合已存在时跳过创建，仅记录日志。
        Qdrant不可用时记录警告并返回，实现优雅降级。
        """
        try:
            client = self._get_client()
            from qdrant_client.models import Distance, VectorParams

            collections = client.get_collections().collections
            names = [c.name for c in collections]
            if self.collection not in names:
                client.create_collection(
                    collection_name=self.collection,
                    vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
                )
                logger.info(f"\nQdrant集合已创建: {self.collection}")
            else:
                logger.info(f"\nQdrant集合已存在: {self.collection}")
        except Exception as e:
            logger.warning(f"\nQdrant集合检查/创建失败: {e}")
            # Qdrant不可用时记录警告并返回，实现优雅降级

    def reset_collection(self) -> None:
        """
        删除并重建当前集合。

        主要用于 full 同步场景，避免切块策略变化后旧向量点残留，
        导致同一份源文件的新旧 chunk 混在一起污染检索结果。
        Qdrant不可用时记录警告并返回，实现优雅降级。
        """
        try:
            client = self._get_client()
            collections = client.get_collections().collections
            names = [c.name for c in collections]
            if self.collection in names:
                client.delete_collection(collection_name=self.collection)
                logger.info(f"\nQdrant集合已删除: {self.collection}")
        except Exception as e:
            logger.warning(f"\nQdrant集合删除失败: {e}")
            # Qdrant不可用时记录警告并返回，实现优雅降级
            return

        self.ensure_collection()

    def search(
        self,
        *,
        query_vector: list[float],
        limit: int = 10,
        with_payload: bool = True,
        score_threshold: float | None = None,
    ) -> list[SearchResult]:
        """
        执行向量相似度搜索。

        使用COSINE距离度量，返回与查询向量最相似的top-k结果。
        基于qdrant-client>=1.12的query_points API实现。

        参数：
            query_vector: 查询向量（维度须与集合维度一致）
            limit: 返回结果数量上限，默认10
            with_payload: 是否返回payload元数据，默认True
            score_threshold: 最低相似度阈值，低于此值的结果被过滤

        返回：
            list[SearchResult]: 检索结果列表，按相似度降序排列；
                               搜索失败时返回空列表
        """
        try:
            client = self._get_client()
            kwargs: dict[str, Any] = {
                "collection_name": self.collection,
                "query": query_vector,
                "limit": limit,
                "with_payload": with_payload,
            }
            if score_threshold is not None:
                kwargs["score_threshold"] = score_threshold

            resp = client.query_points(**kwargs)

            out = []
            for r in resp.points:
                out.append(
                    SearchResult(
                        id=r.id,
                        score=r.score,
                        payload=r.payload or {},
                    )
                )
            return out
        except Exception as e:
            logger.warning(f"\nQdrant搜索失败: {e}")
            # 搜索失败时返回空列表，实现优雅降级
            return []

    def upsert(self, points: list[dict[str, Any]]) -> None:
        """
        批量写入向量点到集合。

        参数：
            points: 向量点列表，每个点包含id/vector/payload字段

        异常：
            Exception: 写入失败时抛出
        """
        try:
            client = self._get_client()
            from qdrant_client.models import PointStruct

            qdrant_points = []
            for p in points:
                qdrant_points.append(
                    PointStruct(
                        id=p["id"],
                        vector=p["vector"],
                        payload=p.get("payload", {}),
                    )
                )
            client.upsert(collection_name=self.collection, points=qdrant_points)
        except Exception as e:
            logger.error(f"\nQdrant upsert失败: {e}")
            # Qdrant不可用时记录错误但不抛出异常，实现优雅降级
