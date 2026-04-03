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
    logger.info(f"  - 是否执行SQL: {execute}")
    
    if llm_client is None:
        logger.info("【SQL处理】创建新的LLM客户端")
        llm_client = OllamaChatClient(use_mock=None)
    
    try:
        if execute:
            logger.info("【SQL处理】===== 开始真正的SQL处理流程 =====")
            
            logger.info("【SQL处理】步骤1: 生成SQL查询...")
            sql_req = SqlGenRequest(
                question=question,
                lognum=lognum,
            )
            logger.info(f"【SQL处理】SQL生成请求: {sql_req}")
            
            sql_result = generate_secure_sql(sql_req, llm=llm_client)
            logger.info(f"【SQL处理】SQL生成结果:")
            logger.info(f"  - SQL: {sql_result.sql}")
            
            logger.info("【SQL处理】步骤2: 执行SQL查询...")
            db_url = get_database_url()
            logger.info(f"【SQL处理】数据库URL: {db_url}")
            
            exec_result = execute_sql(
                sql=sql_result.sql, 
                params=sql_result.params, 
                database_url=db_url
            )
            logger.info(f"【SQL处理】SQL执行结果:")
            if exec_result:
                logger.info(f"  - 列名: {list(exec_result[0].keys()) if exec_result else []}")
                logger.info(f"  - 行数: {len(exec_result)}")
            else:
                logger.info("  - 结果为空")
            
            logger.info("【SQL处理】步骤3: 格式化查询结果...")
            yield "**查询结果：**\n\n"
            
            if exec_result and len(exec_result) > 0:
                columns = list(exec_result[0].keys())
                yield "| " + " | ".join(columns) + " |\n"
                yield "| " + " | ".join(["---------"] * len(columns)) + " |\n"
                
                for row in exec_result:
                    yield "| " + " | ".join(str(cell) if cell is not None else "" for cell in row.values()) + " |\n"
                
                yield f"\n共查询到 **{len(exec_result)}** 条记录。\n"
            else:
                yield "查询结果为空。\n"
            
            logger.info("【SQL处理】===== SQL处理流程完成 =====")
        else:
            logger.info("【SQL处理】execute=False，不执行SQL")
            yield "SQL查询模式已禁用。"
            
    except Exception as e:
        logger.error(f"【SQL处理】发生异常: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        yield f"处理过程中发生错误：{type(e).__name__}: {e}"
    
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
        llm_client = OllamaChatClient(use_mock=None)

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
