"""
元数据查询工具模块

文件功能：
    定义metadata_query Tool，封装数据库Schema元数据查询流程。
    作为LangGraph Tool注册，由LLM通过Tool Calling自主调用。

在系统架构中的定位：
    位于Agent工具层，为Agent提供数据库结构信息。
    通常在生成SQL前辅助LLM理解表结构和字段含义。

主要使用场景：
    - LLM不确定某个字段属于哪个表时，查询表结构
    - LLM需要了解表间关联关系时
    - 作为SQL生成的辅助信息源

核心函数：
    - metadata_query: LangGraph Tool，查询指定表或全部表的元数据

专有技术说明：
    - 复用config_loader的get_schema_runtime()获取Schema信息
    - table_name为空时返回所有表概览，非空时返回指定表详细字段
    - 返回纯文本格式（非JSON），便于LLM直接理解

关联文件：
    - agent_backend/core/config_loader.py: get_schema_runtime获取Schema运行时
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent_backend.core.config import get_schema_runtime

logger = logging.getLogger(__name__)


class MetadataQueryInput(BaseModel):
    """元数据查询工具入参模型"""
    table_name: str | None = Field(default=None, description="要查询的表名，为空则返回所有表概览")


@tool(args_schema=MetadataQueryInput)
def metadata_query(table_name: str | None = None) -> str:
    """
    查询桌面管理系统的数据库表结构信息。
    当需要了解某个表的字段定义、表间关系、字段含义等元数据时使用此工具。
    通常在生成SQL前辅助理解数据库结构。

    参数：
        table_name: 要查询的表名，为空则返回所有表概览

    返回：
        str: 表结构信息的文本描述，包含表名、说明、字段列表等
    """
    logger.info(f"\n[metadata_query] 查询元数据: table_name={table_name}")

    try:
        runtime = get_schema_runtime()

        if table_name:
            table_data = runtime.tree.get(table_name)
            if not table_data:
                available = sorted(runtime.tree.keys())
                return f"未找到表 '{table_name}'。可用的表有：{', '.join(available)}"

            lines = [f"表: {table_name}"]
            raw_table = None
            for t in runtime.raw.tables:
                if t.name == table_name:
                    raw_table = t
                    break

            if raw_table:
                if raw_table.description:
                    lines.append(f"说明: {raw_table.description}")
                if raw_table.primary_key:
                    lines.append(f"主键: {raw_table.primary_key}")
                if raw_table.join_keys:
                    lines.append(f"关联键: {', '.join(raw_table.join_keys)}")

            lines.append("\n字段列表:")
            for col_name, col_sem in table_data.items():
                comment = f" ({col_sem.comment})" if col_sem.comment else ""
                examples = f" [示例: {', '.join(str(e) for e in col_sem.examples[:3])}]" if col_sem.examples else ""
                lines.append(f"  - {col_name}: {col_sem.type}{comment}{examples}")

            return "\n".join(lines)
        else:
            lines = ["数据库表概览:"]
            for t in runtime.raw.tables:
                desc = f" - {t.description}" if t.description else ""
                col_count = len(t.columns)
                pk = f" (主键: {t.primary_key})" if t.primary_key else ""
                lines.append(f"  - {t.name}{desc}: {col_count}个字段{pk}")

            lines.append(f"\n同义词数量: {sum(len(v) for v in runtime.synonyms.values())}")
            return "\n".join(lines)

    except Exception as e:
        logger.error(f"[metadata_query] 异常: {type(e).__name__}: {e}")
        return f"元数据查询失败: {type(e).__name__}: {e}"
