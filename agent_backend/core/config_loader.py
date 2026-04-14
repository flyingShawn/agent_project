"""
Schema元数据加载与索引构建模块

文件功能：
    加载schema_metadata.yaml配置文件，构建内存索引（SchemaRuntime），
    为SQL生成、元数据查询、模板匹配等模块提供统一的Schema数据访问接口。

在系统架构中的定位：
    位于核心基础层，是数据库元数据的唯一数据源。
    SQL Agent、元数据工具、模板匹配等模块均通过get_schema_runtime()获取Schema信息。

主要使用场景：
    - SQL生成时获取表结构、同义词、安全规则和查询模板
    - 元数据查询工具获取表字段定义和注释
    - 模板匹配模块获取query_patterns进行关键字评分

核心类与函数：
    - ColumnSemantics: 列语义信息模型，包含类型/注释/语义键/示例
    - SchemaRuntime: Schema运行时索引，包含tree(表→列映射)和synonyms(同义词映射)
    - get_schema_runtime: 获取SchemaRuntime单例（lru_cache缓存，仅加载一次YAML）

专有技术说明：
    - 使用lru_cache(maxsize=1)实现单例缓存，YAML仅解析一次
    - SchemaRuntime._build_index()将Pydantic模型转为dict索引，优化查询性能
    - tree结构为 {表名: {列名: ColumnSemantics}}，O(1)查找列信息

关联文件：
    - agent_backend/core/schema_models.py: SchemaRoot等Pydantic模型定义
    - agent_backend/configs/schema_metadata.yaml: Schema元数据YAML配置
    - agent_backend/agent/tools/metadata_tool.py: 调用get_schema_runtime()
    - agent_backend/agent/tools/sql_tool.py: 调用get_schema_runtime()
    - agent_backend/sql_agent/patterns.py: 使用SchemaRuntime进行模板匹配
    - agent_backend/sql_agent/prompt_builder.py: 使用SchemaRuntime构建SQL Prompt
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from agent_backend.core.schema_models import SchemaRoot

logger = logging.getLogger(__name__)

_SCHEMA_YAML_PATH = Path(__file__).parent.parent / "configs" / "schema_metadata.yaml"


class ColumnSemantics(BaseModel):
    """列语义信息模型，用于SchemaRuntime内存索引中的列级信息存储"""
    type: str = ""
    comment: str = ""
    semantic_key: str = ""
    examples: list[str] = []


class SchemaRuntime:
    """
    Schema运行时索引，提供表结构和同义词的快速查询能力。

    将SchemaRoot Pydantic模型转换为dict索引结构，
    支持O(1)复杂度的表名→列信息查找。

    属性：
        raw: SchemaRoot原始Pydantic模型，保留完整YAML数据
        tree: dict[str, dict[str, ColumnSemantics]]，表名→列名→列语义的二级索引
        synonyms: dict[str, list[str]]，同义词映射（如 s_machine.Ip_C → ["IP", "ip", "设备IP"]）
    """

    def __init__(self, raw: SchemaRoot) -> None:
        self.raw = raw
        self.tree: dict[str, dict[str, ColumnSemantics]] = {}
        self.synonyms: dict[str, list[str]] = {}
        self._build_index()

    def _build_index(self) -> None:
        """
        从SchemaRoot构建内存索引。

        遍历所有表和列，将Pydantic模型转为ColumnSemantics字典索引，
        同时提取同义词映射。构建完成后tree和synonyms可直接O(1)查找。
        """
        for table in self.raw.tables:
            col_map: dict[str, ColumnSemantics] = {}
            for col in table.columns:
                col_map[col.name] = ColumnSemantics(
                    type=col.type,
                    comment=col.comment or "",
                    semantic_key=col.semantic_key or "",
                    examples=col.examples or [],
                )
            self.tree[table.name] = col_map
        if self.raw.synonyms:
            self.synonyms = {k: list(v) for k, v in self.raw.synonyms.items()}


@lru_cache(maxsize=1)
def get_schema_runtime() -> SchemaRuntime:
    """
    获取SchemaRuntime单例实例。

    使用lru_cache(maxsize=1)实现单例缓存，首次调用时加载YAML并构建索引，
    后续调用直接返回缓存实例。YAML文件仅解析一次，避免重复IO和解析开销。

    参数：
        无

    返回：
        SchemaRuntime: 包含完整Schema索引的运行时实例

    异常：
        FileNotFoundError: schema_metadata.yaml文件不存在时抛出

    性能注意事项：
        - 首次调用有YAML解析和索引构建开销
        - lru_cache确保全局仅解析一次
    """
    yaml_path = _SCHEMA_YAML_PATH
    if not yaml_path.exists():
        raise FileNotFoundError(f"Schema元数据文件不存在: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    raw = SchemaRoot(**data)
    runtime = SchemaRuntime(raw=raw)
    logger.info(f"\nSchema元数据已加载: {len(raw.tables)} 个表, {len(raw.synonyms or {})} 组同义词")
    return runtime
