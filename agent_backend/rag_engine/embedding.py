"""
文本向量化模块

文件目的：
    - 将文本转换为向量表示
    - 支持多种embedding模型
    - 提供统一的向量化接口

核心功能：
    1. 加载embedding模型
    2. 批量文本向量化
    3. 返回向量维度信息

主要类：
    - Embedder: 向量化基类
    - FastEmbedBgeM3: FastEmbed实现（默认）
    - EmbeddingResult: 向量化结果

主要函数：
    - build_default_embedder(): 构建默认向量化器

支持的模型：
    - BAAI/bge-m3: 多语言模型（默认）
    - BAAI/bge-small-zh-v1.5: 中文小模型（备用）

使用场景：
    - RAG文档导入时的向量化
    - 查询文本的向量化

相关文件：
    - agent_backend/rag_engine/ingest.py: 文档导入
    - agent_backend/rag_engine/retrieval.py: 检索
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    dim: int


class Embedder:
    def embed_texts(self, texts: Iterable[str]) -> EmbeddingResult:
        raise NotImplementedError


class FastEmbedBgeM3(Embedder):
    def __init__(self, model_name: str = "BAAI/bge-m3") -> None:
        from fastembed import TextEmbedding

        supported = {m["model"] for m in TextEmbedding.list_supported_models()}
        actual = model_name
        if actual not in supported:
            if actual == "BAAI/bge-m3":
                actual = "BAAI/bge-small-zh-v1.5"
            else:
                raise ValueError(
                    f"fastembed 不支持模型: {actual}. 可用模型示例: BAAI/bge-small-zh-v1.5"
                )

        self._model_name = actual
        self._model = TextEmbedding(model_name=actual)
        self._dim = self._model.embedding_size

    @property
    def dim(self) -> int:
        return self._dim

    def embed_texts(self, texts: Iterable[str]) -> EmbeddingResult:
        vectors = [list(v) for v in self._model.embed(list(texts))]
        return EmbeddingResult(vectors=vectors, dim=self._dim)


def build_default_embedder(model_name: str = "BAAI/bge-m3") -> Embedder:
    try:
        from fastembed import TextEmbedding  # 确保 fastembed 可用

        return FastEmbedBgeM3(model_name=model_name)
    except Exception as e:
        raise RuntimeError(f"Embedding 依赖不可用: {type(e).__name__}: {e}")


class EmbeddingModel:
    def __init__(self, model_name: str = "BAAI/bge-m3") -> None:
        self.embedder = build_default_embedder(model_name)
    
    @property
    def dimension(self) -> int:
        return self.embedder.dim
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        result = self.embedder.embed_texts(texts)
        return result.vectors
