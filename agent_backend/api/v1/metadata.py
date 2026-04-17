"""
数据库元数据摘要API接口模块

文件功能：
    提供数据库Schema元数据摘要查询端点，返回所有表的名称、描述、字段数等信息。

在系统架构中的定位：
    位于API层，通过config_loader获取Schema元数据并格式化返回。

主要使用场景：
    - 前端展示数据库表概览信息
    - 调试和排查Schema配置问题
    - 了解当前系统连接的数据库结构

核心端点：
    - GET /api/v1/metadata/summary: 返回所有表的摘要信息

关联文件：
    - agent_backend/core/config_loader.py: get_schema_runtime()获取Schema运行时
    - agent_backend/api/routes.py: 路由注册
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from agent_backend.core.config import get_schema_runtime

logger = logging.getLogger(__name__)

router = APIRouter(tags=["metadata"])


@router.get("/metadata/summary")
def metadata_summary() -> dict:
    """
    获取数据库元数据摘要。

    返回所有表的名称、描述、字段数、主键信息，以及同义词总数。

    参数：
        无

    返回：
        dict: 包含table_count/tables/synonym_count字段的摘要信息；
              查询失败时包含error字段
    """
    try:
        runtime = get_schema_runtime()
        tables = []
        for t in runtime.raw.tables:
            tables.append({
                "name": t.name,
                "description": t.description,
                "column_count": len(t.columns),
                "primary_key": t.primary_key,
            })
        return {
            "table_count": len(tables),
            "tables": tables,
            "synonym_count": sum(len(v) for v in runtime.synonyms.values()),
        }
    except Exception as e:
        logger.error(f"元数据摘要查询失败: {e}")
        return {"error": str(e)}
