"""
文本向量化模块

文件功能：
    封装FastEmbed文本嵌入模型，提供文本到向量的转换能力。
    为RAG混合检索（向量检索+BM25）提供向量生成支持。

在系统架构中的定位：
    位于RAG引擎基础设施层，是向量检索的数据准备环节。
    retrieval.py的hybrid_search()通过EmbeddingModel将查询文本转为向量，
    再由QdrantVectorStore执行向量相似度搜索。

主要使用场景：
    - RAG文档检索时将查询文本向量化
    - SQL样本检索时将用户问题向量化
    - 文档导入时将文档片段向量化写入Qdrant

核心类：
    - EmbeddingModel: 文本嵌入模型封装，支持FastEmbed和随机向量回退

专有技术说明：
    - 默认模型：BAAI/bge-small-zh-v1.5（中文向量模型，维度384）
    - 通过RAG_EMBEDDING_MODEL环境变量切换模型
    - 懒加载设计：首次调用embed()时才加载模型，避免启动时阻塞
    - 优雅降级：fastembed未安装或加载失败时使用numpy随机向量回退
    - dimension属性自动检测：通过嵌入"test"文本获取实际维度

性能注意事项：
    - 首次调用embed()有模型加载开销（需下载模型文件）
    - FastEmbed使用ONNX Runtime推理，CPU友好
    - 批量文本向量化效率高于逐条调用

关联文件：
    - agent_backend/rag_engine/retrieval.py: hybrid_search()调用embed()
    - agent_backend/rag_engine/qdrant_store.py: 向量写入和检索
"""
from __future__ import annotations

import logging

from agent_backend.core.config import get_settings
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, "EmbeddingModel"] = {}


class EmbeddingModel:
    """
    文本嵌入模型封装，支持FastEmbed和随机向量回退。

    懒加载设计：模型在首次调用embed()时才初始化，
    避免应用启动时因模型下载/加载而阻塞。

    属性：
        model_name: 模型名称，默认BAAI/bge-small-zh-v1.5
        dimension: 向量维度，默认384（加载模型后自动检测）

    优雅降级策略：
        - fastembed未安装 → 使用随机向量回退（维度384）
        - 模型加载失败 → 使用随机向量回退
        - 向量化运行时异常 → 降级为随机向量
    """

    def __init__(self, model_name: str | None = None) -> None:
        """
        初始化嵌入模型。

        参数：
            model_name: 模型名称，为None时从RAG_EMBEDDING_MODEL环境变量读取，
                       默认BAAI/bge-small-zh-v1.5
        """
        self.model_name = model_name or get_settings().rag.rag_embedding_model
        self._model = None
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        """
        获取向量维度。

        若模型未加载则先触发加载，加载后自动检测实际维度。
        回退模式下默认维度为384。

        返回：
            int: 向量维度
        """
        if self._dimension is not None:
            return self._dimension
        self._ensure_loaded()
        return self._dimension or 384

    def _ensure_loaded(self) -> None:
        """
        确保模型已加载，懒加载实现。

        加载流程：
            1. 检查_model是否已初始化，已初始化则直接返回
            2. 尝试导入fastembed并加载TextEmbedding模型
            3. 嵌入"test"文本获取实际维度
            4. 加载失败时降级为随机向量回退（维度384）

        异常处理：
            - ImportError: fastembed未安装，降级为随机向量
            - 其他异常: 模型加载失败，降级为随机向量
        """
        if self._model is not None:
            return
        try:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
            test_embedding = list(self._model.embed(["test"]))[0]
            self._dimension = len(test_embedding)
            logger.info(
                f"\nEmbeddingModel已加载: {self.model_name}, 维度: {self._dimension}"
            )
        except ImportError:
            logger.warning("fastembed未安装，使用随机向量回退")
            self._dimension = 384
            self._model = None
        except Exception as e:
            logger.warning(f"\nEmbeddingModel加载失败: {e}，使用随机向量回退")
            self._dimension = 384
            self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        将文本列表转换为向量列表。

        优先使用FastEmbed模型进行向量化，失败时降级为numpy随机向量。
        随机向量仅用于开发测试，生产环境应安装fastembed。

        参数：
            texts: 待向量化的文本列表

        返回：
            list[list[float]]: 向量列表，每个向量的维度由模型决定

        性能注意事项：
            - FastEmbed支持批量推理，建议批量调用而非逐条调用
            - 随机向量回退模式下每次调用生成不同向量，不可用于实际检索
        """
        self._ensure_loaded()
        if self._model is not None:
            try:
                embeddings = list(self._model.embed(texts))
                return [e.tolist() for e in embeddings]
            except Exception as e:
                logger.warning(f"\n向量化失败: {e}，使用随机向量回退")
        dim = self._dimension or 384
        return [np.random.randn(dim).tolist() for _ in texts]
