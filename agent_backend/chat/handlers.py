"""
聊天处理器模块

文件目的：
    - 处理不同类型的聊天请求
    - 支持SQL查询和RAG问答两种模式
    - 提供流式响应生成

核心功能：
    1. SQL聊天处理：生成SQL、执行查询、格式化结果
    2. RAG聊天处理：检索文档、生成回答
    3. 流式输出：逐步返回结果

主要函数：
    - handle_sql_chat(): 处理SQL查询聊天
    - handle_rag_chat(): 处理RAG问答聊天

SQL聊天流程：
    1. 生成SQL -> generate_secure_sql()
    2. 执行SQL -> execute_sql()
    3. 格式化结果为Markdown表格
    4. 流式返回

RAG聊天流程：
    1. 检索相关文档 -> hybrid_search()
    2. 构建prompt（问题+上下文）
    3. 调用LLM生成回答
    4. 流式返回

使用场景：
    - 统一聊天API的后端处理
    - 多模式问答系统

相关文件：
    - agent_backend/chat/router.py: 意图识别
    - agent_backend/sql_agent/service.py: SQL生成
    - agent_backend/rag_engine/retrieval.py: 文档检索
"""
from __future__ import annotations

import logging
import os
from typing import Any, Iterator

from agent_backend.core.config_helper import get_database_url
from agent_backend.llm.clients import OllamaChatClient
from agent_backend.rag_engine.embedding import EmbeddingModel
from agent_backend.rag_engine.qdrant_store import QdrantVectorStore
from agent_backend.rag_engine.retrieval import get_rag_settings, hybrid_search
from agent_backend.sql_agent.executor import execute_sql
from agent_backend.sql_agent.service import generate_secure_sql
from agent_backend.sql_agent.types import SqlGenRequest

logger = logging.getLogger(__name__)


def handle_sql_chat(
    question: str,
    lognum: str,
    history: list[dict],
    images_base64: list[str] | None = None,
    *,
    execute: bool = True,
    llm_client: OllamaChatClient | None = None,
) -> Iterator[str]:
    logger.info("=" * 60)
    logger.info("【SQL处理流程】开始")
    logger.info(f"  - 问题: {question}")
    logger.info(f"  - 用户ID: {lognum}")
    
    if llm_client is None:
        logger.info("【SQL处理】创建新的LLM客户端")
        llm_client = OllamaChatClient()

    logger.info("【SQL处理】调用generate_secure_sql生成SQL...")
    result = generate_secure_sql(
        SqlGenRequest(question=question, lognum=lognum),
    )

    sql = result.sql
    params = result.params
    logger.info(f"【SQL处理】SQL生成完成")
    logger.info(f"【SQL处理】SQL: {sql}")
    logger.info(f"【SQL处理】参数: {params}")

    yield f"**生成的 SQL：**\n\n```sql\n{sql}\n```\n\n"

    if not execute:
        logger.info("【SQL处理】execute=False，跳过执行")
        yield "（未执行 SQL，DATABASE_URL 未配置）\n"
        return

    database_url = get_database_url()
    if not database_url:
        logger.warning("【SQL处理】DATABASE_URL未配置，跳过执行")
        yield "（未执行 SQL，DATABASE_URL 未配置）\n"
        return

    logger.info("【SQL处理】开始执行SQL...")
    try:
        rows = execute_sql(sql=sql, params=params, max_rows=200)
        logger.info(f"【SQL处理】执行成功，返回 {len(rows) if rows else 0} 行数据")

        if not rows:
            yield "查询结果为空。\n"
            return

        yield "**查询结果：**\n\n"
        yield "| " + " | ".join(rows[0].keys()) + " |\n"
        yield "| " + " | ".join(["---"] * len(rows[0])) + " |\n"
        for row in rows:
            yield "| " + " | ".join(str(v) for v in row.values()) + " |\n"

        yield f"\n共 {len(rows)} 行数据。\n"
        logger.info("【SQL处理】结果格式化完成")

    except Exception as e:
        logger.error(f"【SQL处理】执行出错: {type(e).__name__}: {e}")
        error_msg = str(e)
        if hasattr(e, 'details') and e.details:
            error_msg = f"{e}\n详细信息: {e.details}"
        yield f"\n**执行 SQL 出错：**\n\n```\n{error_msg}\n```\n"
    
    logger.info("【SQL处理流程】结束")
    logger.info("=" * 60)


def handle_rag_chat(
    question: str,
    history: list[dict],
    images_base64: list[str] | None = None,
    *,
    llm_client: OllamaChatClient | None = None,
    store: QdrantVectorStore | None = None,
    embedding_model: EmbeddingModel | None = None,
) -> Iterator[str]:
    logger.info("=" * 60)
    logger.info("【RAG处理流程】开始")
    logger.info(f"  - 问题: {question}")
    logger.info(f"  - 历史消息数: {len(history)}")
    logger.info(f"  - 图片数量: {len(images_base64) if images_base64 else 0}")
    
    if llm_client is None:
        logger.info("【RAG处理】创建新的LLM客户端")
        llm_client = OllamaChatClient()

    if store is None or embedding_model is None:
        logger.info("【RAG处理】加载RAG配置...")
        qdrant_url, qdrant_path, qdrant_api_key, collection, embedding_model_name, top_k = (
            get_rag_settings()
        )
        logger.info(f"  - Qdrant URL: {qdrant_url}")
        logger.info(f"  - Qdrant Path: {qdrant_path}")
        logger.info(f"  - Collection: {collection}")
        logger.info(f"  - Embedding模型: {embedding_model_name}")
        logger.info(f"  - Top-K: {top_k}")

        if embedding_model is None:
            logger.info("【RAG处理】创建Embedding模型...")
            embedding_model = EmbeddingModel(model_name=embedding_model_name)

        if store is None:
            logger.info("【RAG处理】创建Qdrant向量存储...")
            dim = embedding_model.dimension
            store = QdrantVectorStore(
                url=qdrant_url,
                path=qdrant_path,
                api_key=qdrant_api_key,
                collection=collection,
                dim=dim,
            )

    logger.info("【RAG处理】执行混合检索...")
    chunks = hybrid_search(
        query_text=question,
        store=store,
        embedding_model=embedding_model,
        top_k=top_k,
    )
    logger.info(f"【RAG处理】检索完成，找到 {len(chunks) if chunks else 0} 个相关文档片段")

    if not chunks:
        logger.info("【RAG处理】无相关文档，使用普通对话模式")
        messages = [
            {"role": "system", "content": "你是一个有帮助的AI助手。"},
            *history,
            {"role": "user", "content": question},
        ]
        logger.info("【RAG处理】调用LLM生成回答...")
        chunk_count = 0
        for chunk in llm_client.chat_stream(messages, images_base64=images_base64):
            chunk_count += 1
            yield chunk
        logger.info(f"【RAG处理】LLM回答完成，共 {chunk_count} 个文本块")
        logger.info("【RAG处理流程】结束")
        logger.info("=" * 60)
        return

    logger.info("【RAG处理】构建上下文...")
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        logger.info(f"  - 片段{i}: {chunk.source_path} (相似度: {chunk.score if hasattr(chunk, 'score') else 'N/A'})")
        context_parts.append(f"【文档片段 {i}】\n来源：{chunk.source_path}\n{chunk.text}\n")

    context = "\n".join(context_parts)
    logger.info(f"【RAG处理】上下文构建完成，总长度: {len(context)} 字符")

    system_prompt = f"""你是一个专业的AI助手，基于以下文档内容回答用户问题。

文档内容：
{context}

请基于以上文档内容回答用户问题，并在回答中引用相关文档来源。如果文档中没有相关信息，请如实告知。"""

    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": question},
    ]
    
    logger.info("【RAG处理】调用LLM生成回答...")
    chunk_count = 0
    for chunk in llm_client.chat_stream(messages, images_base64=images_base64):
        chunk_count += 1
        yield chunk
    logger.info(f"【RAG处理】LLM回答完成，共 {chunk_count} 个文本块")

    yield "\n\n**参考来源：**\n"
    seen_sources = set()
    for chunk in chunks:
        if chunk.source_path and chunk.source_path not in seen_sources:
            yield f"- {chunk.source_path}"
            if chunk.heading:
                yield f"（{chunk.heading}）"
            yield "\n"
            seen_sources.add(chunk.source_path)
    
    logger.info("【RAG处理流程】结束")
    logger.info("=" * 60)
