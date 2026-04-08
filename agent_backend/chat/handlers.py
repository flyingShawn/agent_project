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

import yaml
from pathlib import Path
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
    session_id: str | None = None,
    *,
    execute: bool = True,
    llm_client: OllamaChatClient | None = None,
) -> Iterator[str]:
    logger.info(f"{'=' * 20 + '【SQL处理流程】开始' + '=' * 20} + '\n - 会话ID: {session_id[:8] if session_id else 'None'}... | 问题: {question} | 用户ID: {lognum} | 是否执行SQL: {execute}")
    
    if llm_client is None:
        logger.info("\n【SQL处理】创建新的LLM客户端")
        llm_client = OllamaChatClient()
    
    try:
        if execute:
            logger.info("\n【SQL处理】===== 开始真正的SQL处理流程 步骤1: 生成SQL查询=====")
           
            sql_req = SqlGenRequest(
                question=question,
                lognum=lognum,
            )
            logger.info(f"\n【SQL处理】SQL生成请求: {sql_req}")
            
            sql_result = generate_secure_sql(sql_req, llm=llm_client)
            logger.info(f"\n【SQL处理】SQL生成结果 - SQL: {sql_result.sql} \n【SQL处理】步骤2: 执行SQL查询...")
            db_url = get_database_url()
            logger.info(f"\n【SQL处理】数据库URL: {db_url}")
            
            exec_result = execute_sql(
                sql=sql_result.sql, 
                params=sql_result.params, 
                database_url=db_url,
                session_id=session_id
            )
            logger.info(f"\n【SQL处理】SQL执行结果:\n  - 列名: {list(exec_result[0].keys()) if exec_result else []}\n  - 行数: {len(exec_result)}") if exec_result else logger.info(f"\n【SQL处理】SQL执行结果:\n  - 结果为空")
            
            logger.info("\n【SQL处理】步骤3: 用自然语言总结查询结果...")
            
            data_summary = ""
            data_table = ""
            if exec_result and len(exec_result) > 0:
                columns = list(exec_result[0].keys())
                data_summary = f"查询到 {len(exec_result)} 条记录，列名：{', '.join(columns)}\n"
                
                # 构建简单的数据表格，用固定宽度格式
                # 先计算每列的最大宽度
                col_widths = {}
                for col in columns:
                    col_widths[col] = len(col)
                    for row in exec_result:
                        val = row.get(col, "")
                        val_str = str(val) if val is not None else ""
                        col_widths[col] = max(col_widths[col], len(val_str))
                        # 限制最大宽度，防止过长
                        col_widths[col] = min(col_widths[col], 30)
                
                # 构建表头
                header = "| " + " | ".join(col.ljust(col_widths[col])[:col_widths[col]] for col in columns) + " |"
                separator = "| " + " | ".join("-" * col_widths[col] for col in columns) + " |"
                
                data_table = header + "\n" + separator + "\n"
                
                # 添加所有数据行
                for row in exec_result:
                    row_str = "| " + " | ".join(
                        (str(row.get(col, "")) if row.get(col, "") is not None else "").ljust(col_widths[col])[:col_widths[col]]
                        for col in columns
                    ) + " |"
                    data_table += row_str + "\n"
            else:
                data_summary = "查询结果为空。"
            
            # 加载提示词配置文件
            prompt_config_path = Path(__file__).resolve().parents[1] / "configs" / "prompt_config.yaml"
            with open(prompt_config_path, 'r', encoding='utf-8') as f:
                prompt_config = yaml.safe_load(f)
            
            # 构建字段配置提示
            fields_prompt = "\n字段配置：\n"
            for field_type, config in prompt_config.items():
                if field_type != 'required_fields' and 'fields' in config:
                    fields_prompt += f"{field_type}类型查询应显示的字段：\n"
                    for field in config['fields']:
                        fields_prompt += f"- {field['name']}"
                        if 'note' in field:
                            fields_prompt += f" ({field['note']})"
                        fields_prompt += "\n"
            
            # 添加强调必须的字段配置
            if 'required_fields' in prompt_config:
                fields_prompt += "\n强调必须的字段：\n"
                for field in prompt_config['required_fields']:
                    fields_prompt += f"- {field}\n"
            
            answer_prompt = f"""你是一个专业且友好的桌管系统AI助手，需要基于数据库查询结果以人性化的方式回答用户问题。

用户问题：{question}

查询结果：
{data_summary}

请用自然语言回答用户的问题，要求：
1. 回答要友好、自然，富有同理心，避免生硬的表达方式
2. 严格基于查询结果生成回答，不得编造任何数据或信息
3. 如果是统计类问题（比如问"多少个"），先简洁回答具体数字
4. 不要暴露数据库表名、列名等技术细节，保持回答的专业性和易懂性
5. 如果查询结果为空，如实告知用户并提供可能的原因或后续建议
6. 使用自然的口语化表达，让对话感觉更像人与人之间的交流
7. 回答简洁一些，不要超过3句话

请直接回答。"""

            
            answer_messages = [
                # {"role": "system", "content": "你是一个专业且友好的桌管系统AI助手，善于用自然语言总结数据库查询结果，回答时要人性化、富有同理心，避免生硬的表达方式。当用户要求列出详细信息时，必须使用Markdown表格格式展示所有相关字段，并参考字段配置来确保展示正确的信息。严格基于查询结果生成回答，不得编造任何数据或信息。对于查询结果中缺失的字段，显示为空或'未查询到'。对于强调必须的字段，如果未查询到，必须显示'未查询到，存在异常'。根据用户查询的类型，按照配置文件中的字段顺序和要求来展示信息，特别是查询部门信息时只显示部门名称、父部门和直属于部门下的机器数。"},
                {"role": "system", "content": "你是一个专业且友好的桌管系统AI助手，善于用自然语言总结数据库查询结果，回答时要人性化、富有同理心，避免生硬的表达方式。当用户要求列出详细信息时，必须使用Markdown表格格式展示所有相关字段，并参考字段配置来确保展示正确的信息。严格基于查询结果生成回答，不得编造任何数据或信息。对于查询结果中缺失的字段，显示为空或'未查询到'。对于强调必须的字段，如果未查询到，必须显示'未查询到，存在异常'。根据用户查询的类型，严格按照配置文件中的字段顺序和要求来展示信息，只展示与查询类型相关的信息，不要提及其他类型的信息。表格格式必须完整且正确，确保表头和数据行对齐，不要出现格式混乱的情况。对于部门信息查询，确保正确处理直属机器数的显示，根据查询结果中的实际值展示。"},
                {"role": "user", "content": answer_prompt}
            ]
            
            logger.info("\n【SQL处理】调用LLM生成自然语言回答...")
            for chunk in llm_client.chat_stream(answer_messages):
                yield chunk
            
            # 如果有数据表格，直接追加到回答中
            if data_table:
                yield "\n\n```\n"
                yield data_table
                yield "```\n"
            
            logger.info("\n【SQL处理】===== SQL处理流程完成 =====")
        else:
            logger.info("\n【SQL处理】execute=False，不执行SQL")
            yield "SQL查询模式已禁用。"
            
    except Exception as e:
        logger.error(f"\n【SQL处理】发生异常: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        yield f"处理过程中发生错误：{type(e).__name__}: {e}"
    
    logger.info("\n【SQL处理流程】结束")
    logger.info("=" * 60)


def handle_rag_chat(
    question: str,
    history: list[dict],
    images_base64: list[str] | None = None,
    session_id: str | None = None,
    *,
    llm_client: OllamaChatClient | None = None,
    store: QdrantVectorStore | None = None,
    embedding_model: EmbeddingModel | None = None,
) -> Iterator[str]:
    logger.info("=" * 20 + "【RAG处理流程】开始" + "=" * 20 + f"\n - 问题: {question} | 历史消息数: {len(history)} | 图片数量: {len(images_base64) if images_base64 else 0}")
    
    if llm_client is None:
        logger.info("\n【RAG处理】创建新的LLM客户端")
        llm_client = OllamaChatClient()

    if store is None or embedding_model is None:
        logger.info("\n【RAG处理】加载RAG配置...")
        qdrant_url, qdrant_path, qdrant_api_key, collection, embedding_model_name, top_k = (
            get_rag_settings()
        )
        logger.info(f"\n - Qdrant URL: {qdrant_url} | Qdrant Path: {qdrant_path} | Collection: {collection} | Embedding模型: {embedding_model_name} | Top-K: {top_k}")

        if embedding_model is None:
            logger.info("\n【RAG处理】创建Embedding模型...")
            embedding_model = EmbeddingModel(model_name=embedding_model_name)

        if store is None:
            logger.info("\n【RAG处理】创建Qdrant向量存储...")
            dim = embedding_model.dimension
            store = QdrantVectorStore(
                url=qdrant_url,
                path=qdrant_path,
                api_key=qdrant_api_key,
                collection=collection,
                dim=dim,
            )
            store.ensure_collection()

    logger.info("\n【RAG处理】执行混合检索...")
    chunks = hybrid_search(
        query_text=question,
        store=store,
        embedding_model=embedding_model,
        top_k=top_k,
    )
    logger.info(f"\n【RAG处理】检索完成，找到 {len(chunks) if chunks else 0} 个相关文档片段")

    if not chunks:
        logger.info("\n【RAG处理】无相关文档，使用普通对话模式")
        messages = [
            {"role": "system", "content": "你是一个有帮助的AI助手。"},
            *history,
            {"role": "user", "content": question},
        ]
        logger.info("\n【RAG处理】调用LLM生成回答...")
        chunk_count = 0
        for chunk in llm_client.chat_stream(messages, images_base64=images_base64):
            chunk_count += 1
            yield chunk
        logger.info(f"\n【RAG处理】LLM回答完成，共 {chunk_count} 个文本块")
        logger.info("\n【RAG处理流程】结束")
        logger.info("=" * 60)
        return

    logger.info("\n【RAG处理】构建上下文...")
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        logger.info(f"\n - 片段{i}: {chunk.source_path} (相似度: {chunk.score if hasattr(chunk, 'score') else 'N/A'})")
        context_parts.append(f"\n【文档片段 {i}】\n来源：{chunk.source_path}\n{chunk.text}\n")

    context = "\n".join(context_parts)
    logger.info(f"\n【RAG处理】上下文构建完成，总长度: {len(context)} 字符")

    system_prompt = f"""你是一个专业的AI助手，基于以下文档内容回答用户问题。

文档内容：
{context}

请基于以上文档内容回答用户问题。如果文档中没有相关信息，请如实告知。"""

    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": question},
    ]
    
    logger.info("\n【RAG处理】调用LLM生成回答...")
    chunk_count = 0
    for chunk in llm_client.chat_stream(messages, images_base64=images_base64):
        chunk_count += 1
        yield chunk
    logger.info(f"\n【RAG处理】LLM回答完成，共 {chunk_count} 个文本块")

    references = []
    seen_sources = set()
    for chunk in chunks:
        if chunk.source_path and chunk.source_path not in seen_sources:
            from pathlib import Path
            source_name = Path(chunk.source_path).name
            ref_line = f"- {source_name}"
            if chunk.heading:
                ref_line += f"（{chunk.heading}）"
            references.append(ref_line)
            seen_sources.add(chunk.source_path)
    
    if references:
        yield "\n\n---\n\n**📚 参考来源：**\n"
        yield "\n".join(references)
    
    logger.info("\n【RAG处理流程】结束")
    logger.info("=" * 60)
