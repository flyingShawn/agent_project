"""
RAG检索工具模块

文件功能：
    定义rag_search Tool，封装知识库混合检索（向量+BM25）流程。
    作为LangGraph Tool注册，由LLM通过Tool Calling自主调用。

在系统架构中的定位：
    位于Agent工具层，是Agent与知识库交互的唯一入口。
    复用现有rag_engine/retrieval.py的hybrid_search能力。

主要使用场景：
    - LLM判断用户问题需要文档检索时，通过Tool Calling调用
    - tool_result_node解析tool_calls后执行

核心函数：
    - rag_search: LangGraph Tool，接收查询文本，返回JSON格式检索结果

专有技术说明：
    - 使用hybrid_search实现向量+BM25混合检索，提升召回率
    - 每次调用初始化EmbeddingModel和QdrantVectorStore（轻量操作）
    - 检索结果包含context（文档片段文本）、chunk_count、sources（参考来源）

关联文件：
    - agent_backend/rag_engine/retrieval.py: hybrid_search和get_rag_settings
    - agent_backend/rag_engine/embedding.py: EmbeddingModel本地嵌入
    - agent_backend/rag_engine/qdrant_store.py: QdrantVectorStore向量存储
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent_backend.rag_engine.embedding import EmbeddingModel
from agent_backend.rag_engine.qdrant_store import QdrantVectorStore
from agent_backend.rag_engine.retrieval import get_rag_settings, hybrid_search

logger = logging.getLogger(__name__)


class RagSearchInput(BaseModel):
    """RAG检索工具入参模型"""
    question: str = Field(description="用于检索的查询文本，应与用户问题语义一致")


@tool(args_schema=RagSearchInput)
def rag_search(question: str) -> str:
    """
    从桌面管理系统知识库中检索文档。
    当用户问题涉及操作方法、配置步骤、故障排查、使用指南、权限设置等
    需要参考文档的问题时使用此工具。

    参数：
        question: 用于检索的查询文本，应与用户问题语义一致

    返回：
        str: JSON格式字符串，包含context/chunk_count/sources字段；
             检索失败时包含error字段
    """
    logger.info(f"\n[rag_search] 开始检索: {question}")

    try:
        qdrant_url, qdrant_path, qdrant_api_key, collection, embedding_model_name, top_k, vector_min_score = get_rag_settings()

        embedding_model = EmbeddingModel(model_name=embedding_model_name)

        dim = embedding_model.dimension
        store = QdrantVectorStore(
            url=qdrant_url,
            path=qdrant_path,
            api_key=qdrant_api_key,
            collection=collection,
            dim=dim,
        )
        store.ensure_collection()

        chunks = hybrid_search(
            query_text=question,
            store=store,
            embedding_model=embedding_model,
            top_k=top_k,
            min_score=0.5,
            vector_min_score=vector_min_score,
        )
        logger.info(f"\n[rag_search] 检索到 {len(chunks) if chunks else 0} 个文档片段")

        if not chunks:
            return "未检索到相关文档片段。请直接根据你的知识回答用户问题，并告知用户未找到相关文档参考。"

        context_parts = []
        sources = []
        seen_sources = set()

        for i, chunk in enumerate(chunks, 1):
            logger.info(f"\n[rag_search] 片段{i}: {chunk.source_path} (混合分: {chunk.score:.4f})")
            context_parts.append(f"【文档片段 {i}】\n来源：{chunk.source_path}\n{chunk.text}\n")

            if chunk.source_path and chunk.source_path not in seen_sources:
                source_name = Path(chunk.source_path).name
                ref_line = f"- {source_name}"
                if chunk.heading:
                    ref_line += f"（{chunk.heading}）"
                sources.append(ref_line)
                seen_sources.add(chunk.source_path)

        result = {
            "context": "\n".join(context_parts),
            "chunk_count": len(chunks),
            "sources": sources,
        }

        import json
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[rag_search] 异常: {type(e).__name__}: {e}")
        import json
        return json.dumps({"error": f"检索失败: {type(e).__name__}: {e}"}, ensure_ascii=False)
