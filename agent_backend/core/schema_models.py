"""
Schema元数据Pydantic模型定义模块

文件功能：
    定义schema_metadata.yaml配置文件的完整Pydantic模型体系，
    提供YAML数据到Python对象的类型安全转换和校验。

在系统架构中的定位：
    位于核心基础层，是config_loader加载数据的类型基础。
    所有需要访问Schema元数据的模块最终通过这些模型获取结构化数据。

主要使用场景：
    - config_loader加载YAML后用SchemaRoot校验和转换数据
    - SQL Prompt构建时遍历TableDef和ColumnDef获取表结构信息
    - 模板匹配时读取QueryPattern获取预定义SQL模板
    - 安全校验时读取SecurityDef获取敏感列和受限表配置

核心模型：
    - ColumnDef: 列定义（名称/类型/注释/语义键/示例值）
    - TableDef: 表定义（名称/描述/主键/关联键/列列表）
    - SecurityDef: 安全配置（受限表/禁止查询列/权限规则）
    - NamingDef: 命名配置（标识符引用符）
    - QueryPattern: 查询模板（名称/用户意图/权限要求/SQL模板）
    - RelationshipDef: 表关联关系（来源字段/目标字段/关联类型）
    - DisplayFieldDef: 展示字段定义（名称/列/是否必需/聚合标记）
    - DisplayGroupDef: 展示字段分组（提示词/字段列表）
    - SchemaRoot: 根模型，包含所有Schema元数据

专有技术说明：
    - RelationshipDef使用from_field替代Python保留字from，通过Config.populate_by_name支持YAML中的from字段
    - 所有字段使用Optional类型，YAML中可省略非必要配置
    - QueryPattern.sql存储含参数占位符的SQL模板（如:ip, :limit）

关联文件：
    - agent_backend/core/config_loader.py: 使用SchemaRoot解析YAML数据
    - agent_backend/configs/schema_metadata.yaml: YAML配置文件
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ColumnDef(BaseModel):
    """列定义模型，描述数据库表中单个列的元数据"""
    name: str
    type: str = ""
    comment: str | None = None
    semantic_key: str | None = None
    examples: list[str] | None = None


class TableDef(BaseModel):
    """表定义模型，描述数据库中单个表的元数据"""
    name: str
    description: str | None = None
    primary_key: str | None = None
    join_keys: list[str] | None = None
    columns: list[ColumnDef] = []
    partial: bool | None = None


class SecurityDef(BaseModel):
    """安全配置模型，定义SQL查询的安全约束规则"""
    restricted_tables: list[str] | None = None
    deny_select_columns: list[str] | None = None
    permissions: list[dict[str, Any]] | None = None


class NamingDef(BaseModel):
    """命名配置模型，定义数据库标识符引用规则"""
    identifier_quote: str | None = None


class QueryPattern(BaseModel):
    """
    查询模板模型，定义预审核的SQL模板。

    模板匹配命中时直接返回预定义SQL，绕过LLM生成，
    获得更稳定和安全的查询结果。

    属性：
        name: 模板名称
        user_intent: 用户意图描述，用于关键字评分匹配
        requires_permission: 所需权限规则名称
        sql: SQL模板，支持:ip, :limit等参数占位符
    """
    name: str
    user_intent: str | None = None
    requires_permission: str | None = None
    sql: str = ""


class RelationshipDef(BaseModel):
    """
    表关联关系模型，描述数据库表之间的外键关联。

    专有技术说明：
        - 使用from_field替代Python保留字from
        - 通过Config.populate_by_name=True支持YAML中的from字段自动映射
    """
    from_field: str = ""
    to: str = ""
    kind: str = ""
    comment: str | None = None

    class Config:
        populate_by_name = True

    def __init__(self, **data: Any) -> None:
        if "from" in data:
            data["from_field"] = data.pop("from")
        super().__init__(**data)


class DisplayFieldDef(BaseModel):
    """展示字段定义模型，描述前端展示时需要的字段映射"""
    name: str = ""
    column: str = ""
    display: bool | None = None
    required: bool | None = None
    aggregate: bool | None = None
    fallback: str | None = None
    note: str | None = None


class DisplayGroupDef(BaseModel):
    """展示字段分组模型，按业务场景组织展示字段"""
    prompt: str | None = None
    fields: list[DisplayFieldDef] = []


class SchemaRoot(BaseModel):
    """
    Schema元数据根模型，对应schema_metadata.yaml的完整结构。

    包含数据库类型、命名规则、安全配置、同义词、表定义、
    关联关系、查询模板、展示字段等所有元数据。
    """
    db_type: str | None = None
    naming: NamingDef | None = None
    security: SecurityDef | None = None
    synonyms: dict[str, list[str]] | None = None
    tables: list[TableDef] = []
    relationships: list[RelationshipDef] = []
    query_patterns: list[QueryPattern] | None = None
    display_fields: dict[str, DisplayGroupDef] | None = None
    required_fields: list[str] | None = None
