"""
聊天处理器模块

文件功能：
    处理不同意图类型的聊天请求，提供 SQL 查询和 RAG 问答两种处理模式，
    并以流式迭代器方式逐步返回 LLM 生成的文本片段。

核心作用与设计目的：
    - SQL 模式：将自然语言问题转为 SQL → 执行查询 → 将结果交给 LLM 生成自然语言总结
    - RAG 模式：通过混合检索获取相关文档片段 → 构建上下文 Prompt → LLM 生成回答
    - 两种模式均通过 Iterator[str] 流式输出，适配 SSE 推送

主要使用场景：
    - 统一聊天 API (/api/v1/chat) 的后端处理核心
    - 可被其他模块直接调用（传入参数即可获取流式输出）

包含的主要函数：
    - _build_markdown_table(): 将查询结果列表转为 Markdown 表格（内部方法）
    - handle_sql_chat(): 处理 SQL 查询聊天，生成 SQL → 执行 → LLM 总结 → 流式返回
    - handle_rag_chat(): 处理 RAG 问答聊天，检索文档 → LLM 生成 → 流式返回

专有技术说明：
    - RAG 检索使用 hybrid_search() 混合检索（向量检索 + BM25 关键词检索加权融合）
    - 向量模型为 FastEmbed (BAAI/bge-small-zh-v1.5)，向量数据库为 Qdrant
    - LLM 调用通过 OllamaChatClient 封装，支持文本模型和视觉模型自动切换

相关联的调用文件：
    - agent_backend/api/v1/chat.py: 调用 handle_sql_chat/handle_rag_chat
    - agent_backend/sql_agent/service.py: SQL 生成服务
    - agent_backend/sql_agent/executor.py: SQL 执行器
    - agent_backend/rag_engine/retrieval.py: 混合检索
    - agent_backend/llm/clients.py: LLM 客户端
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterator

from agent_backend.core.config_helper import get_database_url
from agent_backend.core.config_loader import get_schema_runtime
from agent_backend.llm.clients import OllamaChatClient
from agent_backend.rag_engine.embedding import EmbeddingModel
from agent_backend.rag_engine.qdrant_store import QdrantVectorStore
from agent_backend.rag_engine.retrieval import get_rag_settings, hybrid_search
from agent_backend.sql_agent.executor import execute_sql
from agent_backend.sql_agent.service import generate_secure_sql
from agent_backend.sql_agent.types import SqlGenRequest

logger = logging.getLogger(__name__)

MAX_DISPLAY_ROWS = 50


def _build_markdown_table(rows: list[dict]) -> str:
    """
    将查询结果字典列表转为 Markdown 表格字符串。

    参数：
        rows: 查询结果列表，每个元素为 {列名: 值} 的字典

    返回：
        str: Markdown 格式的表格字符串；rows 为空时返回空字符串

    注意事项：
        - 最多显示 MAX_DISPLAY_ROWS (50) 行，超出部分显示省略提示
        - 单元格中的 | 和换行符会被转义，避免破坏表格格式
        - None 值会被替换为空字符串
    """
    if not rows:
        return ""
    columns = list(rows[0].keys())
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, separator]
    for row in rows[:MAX_DISPLAY_ROWS]:
        cells = []
        for col in columns:
            val = row.get(col, "")
            if val is None:
                val = ""
            val = str(val).replace("|", "\\|").replace("\n", " ").replace("\r", "")
            cells.append(val)
        lines.append("| " + " | ".join(cells) + " |")
    if len(rows) > MAX_DISPLAY_ROWS:
        lines.append(f"| ... | 共 {len(rows)} 条，仅显示前 {MAX_DISPLAY_ROWS} 条 |")
    return "\n".join(lines)


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
    """
    处理 SQL 查询聊天，将自然语言问题转为 SQL 并执行，流式返回自然语言总结。

    处理流程：
        1. 调用 generate_secure_sql() 生成安全的 SQL 语句
        2. 调用 execute_sql() 执行查询获取结果
        3. 若结果为空，LLM 生成"无数据"的友好提示
        4. 若有结果，将 Markdown 表格和字段配置提示交给 LLM 生成自然语言总结
        5. 流式返回 LLM 输出，最后附带 Markdown 表格和推荐追问

    参数：
        question: 用户自然语言问题
        lognum: 用户工号，用于权限过滤
        history: 对话历史列表，格式 [{"role": "user/assistant", "content": "..."}]
        images_base64: Base64 编码图片列表（当前 SQL 模式未使用）
        session_id: 会话 ID，用于数据库连接复用
        execute: 是否执行 SQL，默认 True；为 False 时直接返回提示
        llm_client: LLM 客户端实例，为 None 时自动创建

    返回：
        Iterator[str]: 流式文本片段迭代器，每个元素为 LLM 生成的一段文本

    异常处理：
        - 捕获所有异常后 yield 错误信息字符串，不会向上抛出

    性能考量：
        - SQL 执行可能耗时较长（取决于查询复杂度），建议配合 session_id 复用连接
        - LLM 流式输出可减少用户感知延迟
    """
    logger.info(f"{'=' * 20}【SQL处理流程】开始{'=' * 20}\n会话ID: {session_id[:8] if session_id else 'None'}... | 问题: {question} | 用户ID: {lognum}")

    if llm_client is None:
        llm_client = OllamaChatClient()

    try:
        if not execute:
            yield "SQL查询模式已禁用。"
            return

        sql_req = SqlGenRequest(question=question, lognum=lognum)
        sql_result = generate_secure_sql(sql_req, llm=llm_client)
        logger.info(f"SQL生成结果: {sql_result.sql}")

        db_url = get_database_url()
        exec_result = execute_sql(
            sql=sql_result.sql,
            params=sql_result.params,
            database_url=db_url,
            session_id=session_id,
        )
        logger.info(f"SQL执行结果: {len(exec_result) if exec_result else 0} 行")

        if not exec_result or len(exec_result) == 0:
            answer_prompt = f"""你是一个专业且友好的桌管系统AI助手。

用户问题：{question}

数据库查询结果为空，没有找到匹配的数据。

请用自然语言告知用户查询结果为空，并提供可能的原因或后续建议。要求：
1. 回答要友好、自然，富有同理心
2. 不要编造任何数据
3. 请直接回答，不要生成表格"""
            messages = [
                {"role": "system", "content": "你是一个专业且友好的桌管系统AI助手。"},
                {"role": "user", "content": answer_prompt},
            ]
            for chunk in llm_client.chat_stream(messages):
                yield chunk
            return

        # 这是我生成表格的地方,非大模型生成的,之前大模型给的不标准
        # 检查如果数据只有一列,就不生成表格了
        if len(exec_result) == 1 and len(exec_result[0]) == 1:
            data_table = ""
        else:
            data_table = _build_markdown_table(exec_result)
        columns = list(exec_result[0].keys())
      
        fields_hint = ""
        try:
            schema_runtime = get_schema_runtime()
            parts = []
            for field_type, group in schema_runtime.raw.display_fields.items():
                if group.fields:
                    parts.append(f"{field_type}类型：{', '.join(f'{f.name}({f.note})' if f.note else f.name for f in group.fields)}")
            if schema_runtime.raw.required_fields:
                parts.append(f"必须字段：{', '.join(schema_runtime.raw.required_fields)}")
            if parts:
                fields_hint = "\n字段配置参考：\n" + "\n".join(f"- {p}" for p in parts)
        except Exception:
            pass

        answer_prompt = f"""你是一个专业且友好的桌管系统AI助手，需要基于数据库查询结果回答用户问题。

用户问题：{question}

查询结果（共 {len(exec_result)} 条记录，列名：{', '.join(columns)}）：

{data_table}
{fields_hint}

请用自然语言回答用户的问题，要求：
1. 回答要友好、自然，富有同理心，避免生硬的表达方式
2. 严格基于上面的查询结果表格生成回答，不得编造任何数据或信息
3. 如果是统计类问题（比如问"多少个"），先简洁回答具体数字
4. 对于查询结果中缺失的字段，显示为空或"未查询到"
5. 不要暴露数据库表名、列名等技术细节
6. 绝对不要编造示例数据，只根据查询结果生成回答
7. 不要重复输出上面的数据表格，只做文字总结即可，数据表格会在你回答后自动展示
8. 只输出文字总结，不要在末尾添加追问、建议或询问用户是否需要更多信息

请直接回答。"""
# 出现查询全部或者要求列表时,一定要将数据结果展示成列表
        messages = [
            {"role": "system", "content": "你是一个专业且友好的桌管系统AI助手，善于用自然语言总结数据库查询结果。严格基于查询结果生成回答，不得编造任何数据或信息。不要重复输出数据表格，只做文字总结，数据表格会在你回答后自动展示给用户。只输出文字总结，不要在末尾添加追问或建议。"},
            {"role": "user", "content": answer_prompt},
        ]

        for chunk in llm_client.chat_stream(messages):
            yield chunk

        if data_table:
            yield f"\n\n{data_table}\n\n---\n\n💡 **您可能还想了解：**\n- 查看更详细的设备信息\n- 查询设备硬件配置\n- 其他请求"

        logger.info("SQL处理流程完成")

    except Exception as e:
        logger.error(f"SQL处理异常: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        yield f"处理过程中发生错误：{type(e).__name__}: {e}"

    logger.info("SQL处理流程结束")


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
    """
    处理 RAG 问答聊天，检索相关文档片段后由 LLM 生成回答，流式返回。

    处理流程：
        1. 初始化 QdrantVectorStore 和 EmbeddingModel（若未传入）
        2. 调用 hybrid_search() 进行混合检索（向量 + BM25），获取相关文档片段
        3. 若无检索结果，直接将问题交给 LLM 作为普通对话处理
        4. 若有结果，将文档片段作为上下文构建 Prompt，交给 LLM 生成回答
        5. 流式返回 LLM 输出，最后附带参考来源列表

    参数：
        question: 用户问题
        history: 对话历史列表
        images_base64: Base64 编码图片列表，用于多模态输入
        session_id: 会话 ID（当前 RAG 模式未使用数据库连接）
        llm_client: LLM 客户端实例，为 None 时自动创建
        store: Qdrant 向量存储实例，为 None 时自动创建
        embedding_model: 向量模型实例，为 None 时自动创建

    返回：
        Iterator[str]: 流式文本片段迭代器

    专有技术说明：
        - 混合检索使用 hybrid_search()，融合向量检索（FastEmbed BAAI/bge-small-zh-v1.5）
          和 BM25 关键词检索，alpha 参数控制权重配比
        - 向量数据库为 Qdrant，使用 COSINE 距离度量
        - 检索阈值：min_score=0.5, vector_min_score 由环境变量配置

    异常处理：
        - 检索失败时退化为普通对话模式（无上下文）
    """
    logger.info(f"{'=' * 20}【RAG处理流程】开始{'=' * 20}\n问题: {question} | 历史消息数: {len(history)} | 图片数量: {len(images_base64) if images_base64 else 0}")

    if llm_client is None:
        llm_client = OllamaChatClient()

    if store is None or embedding_model is None:
        qdrant_url, qdrant_path, qdrant_api_key, collection, embedding_model_name, top_k, vector_min_score = get_rag_settings()

        if embedding_model is None:
            embedding_model = EmbeddingModel(model_name=embedding_model_name)

        if store is None:
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
    logger.info(f"RAG检索完成，找到 {len(chunks) if chunks else 0} 个相关文档片段 (vector_min_score={vector_min_score})")

    if not chunks:
        messages = [
            {"role": "system", "content": "你是一个有帮助的AI助手。"},
            *history,
            {"role": "user", "content": question},
        ]
        for chunk in llm_client.chat_stream(messages, images_base64=images_base64):
            yield chunk
        return

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        logger.info(f"片段{i}: {chunk.source_path} (原始向量分: {chunk.raw_vector_score:.4f}, 混合分: {chunk.score:.4f})")
        context_parts.append(f"【文档片段 {i}】\n来源：{chunk.source_path}\n{chunk.text}\n")

    context = "\n".join(context_parts)

    system_prompt = f"""你是一个专业的AI助手，基于以下文档内容回答用户问题。

文档内容：
{context}

请基于以上文档内容回答用户问题。如果文档中没有相关信息，请如实告知。"""

    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": question},
    ]

    for chunk in llm_client.chat_stream(messages, images_base64=images_base64):
        yield chunk

    references = []
    seen_sources = set()
    for chunk in chunks:
        if chunk.source_path and chunk.source_path not in seen_sources:
            source_name = Path(chunk.source_path).name
            ref_line = f"- {source_name}"
            if chunk.heading:
                ref_line += f"（{chunk.heading}）"
            references.append(ref_line)
            seen_sources.add(chunk.source_path)

    if references:
        yield "\n\n---\n\n**📚 参考来源：**\n"
        yield "\n".join(references)

    logger.info("RAG处理流程结束")
