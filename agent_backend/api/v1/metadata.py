"""
元数据查询 API 端点

文件目的：
    - 提供数据库schema元数据查询接口
    - 返回表、列、语义键、同义词等摘要信息
    - 用于验证配置文件加载和索引构建状态

API端点：
    GET /api/v1/metadata/summary
    返回: {
        "tables": [...],           # 表名列表
        "column_count": int,       # 列总数
        "semantic_keys": [...],    # 语义键列表
        "synonym_count": int,      # 同义词总数
        "db_type": str             # 数据库类型
    }

调用流程：
    客户端 -> GET /api/v1/metadata/summary 
    -> metadata_summary() 
    -> get_schema_runtime() 
    -> 返回摘要信息

相关文件：
    - agent_backend/core/config_loader.py: schema配置加载器
    - database_context.yaml: schema元数据配置文件
"""
from __future__ import annotations

from fastapi import APIRouter

from agent_backend.core.config_loader import get_schema_runtime

router = APIRouter(tags=["metadata"])


@router.get("/metadata/summary")
def metadata_summary() -> dict:
    """
    返回数据库上下文（schema metadata）的摘要信息。

    这是一个用于快速自检的接口，通常用于：
    - 验证 schema_metadata.yaml 是否可被成功加载与校验
    - 验证内存索引是否构建成功（表数量、列数量、semantic_key 数量、同义词数量）

    说明：
        - 该接口仅返回摘要，不返回全量 schema，避免体积过大与敏感信息扩散。
    """
    runtime = get_schema_runtime()
    return {
        "tables": sorted(runtime.tree.keys()),
        "column_count": len(runtime.by_column_path),
        "semantic_keys": sorted(runtime.by_semantic.keys()),
        "synonym_count": sum(len(v) for v in runtime.synonyms.values()),
        "db_type": runtime.raw.db_type,
    }

