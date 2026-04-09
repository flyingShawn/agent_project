"""
Schema元数据Pydantic模型定义

文件目的：
    - 定义数据库schema元数据的结构
    - 提供YAML配置的校验规则
    - 支持权限、关系、查询模式等高级特性

主要模型：
    基础配置：
    - NamingConfig: 命名规范配置
    - SecurityConfig: 安全控制配置
    
    权限相关：
    - PermissionVariable: 权限变量定义
    - PermissionMachineAnchor: 设备维度权限锚点
    - PermissionApplyRule: 权限应用规则
    - PermissionDef: 权限定义
    
    Schema结构：
    - ColumnDef: 列定义
    - TableDef: 表定义
    - RelationshipDef: 表关系定义
    
    查询相关：
    - QueryPatternDef: 查询模式（SQL模板）
    
    顶层模型：
    - DatabaseContext: 数据库上下文配置（根模型）

使用方式：
    1. 在YAML中定义schema元数据
    2. 使用Pydantic模型校验YAML结构
    3. 通过模型访问配置数据

相关文件：
    - agent_backend/core/config_loader.py: 配置加载器
    - agent_backend/configs/schema_metadata.yaml: 配置文件
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NamingConfig(BaseModel):
    """命名规范配置：标识符引用符、大小写规则、列名归一化映射等。"""
    model_config = ConfigDict(extra="forbid")

    identifier_quote: str | None = None
    case_insensitive_identifiers: bool = True
    normalize_columns: dict[str, str] = Field(default_factory=dict)


class SecurityConfig(BaseModel):
    """安全控制配置：限制表、禁止查询返回的敏感列清单等。"""
    model_config = ConfigDict(extra="forbid")

    restricted_tables: list[str] = Field(default_factory=list)
    deny_select_columns: list[str] = Field(default_factory=list)


class PermissionVariable(BaseModel):
    """权限模板变量定义（用于 SQL 模板中的参数占位）。"""
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    example: Any | None = None


class PermissionMachineAnchor(BaseModel):
    """
    设备维度权限锚点定义。

    专用说明：
        该结构用于描述“以 s_machine 为核心”的权限过滤方式，
        便于后续 Text-to-SQL 在涉及 MtID 关联的表时统一追加 join/where 规则。
    """
    model_config = ConfigDict(extra="forbid")

    table: str
    machine_id_column: str
    group_id_column: str
    join_from_mtid_sql: str | None = None


class PermissionApplyRule(BaseModel):
    """
    权限应用规则：在命中某些表时，追加 where/join 片段以完成权限约束。

    专用说明：
        该结构面向后续 Text-to-SQL 的“权限重写/SQL 拼接”阶段使用。
    """
    model_config = ConfigDict(extra="forbid")

    scope_name: str
    when_tables_in_query: list[str] = Field(default_factory=list)
    where_append_sql: str
    machine_anchor: PermissionMachineAnchor | None = None


class PermissionDef(BaseModel):
    """
    权限定义：包含变量、可见范围子查询 SQL 与应用规则。

    专用说明：
        该结构是后续做“按管理员账号限制可见部门/设备”权限体系的核心配置来源。
    """
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    variables: list[PermissionVariable] = Field(default_factory=list)
    allowed_group_ids_sql: str
    apply_rules: list[PermissionApplyRule] = Field(default_factory=list)


class ColumnDef(BaseModel):
    """列定义：类型、注释与语义键（semantic_key）等。"""
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    comment: str | None = None
    semantic_key: str
    examples: list[Any] = Field(default_factory=list)


class TableDef(BaseModel):
    """
    表定义：主键、可用于 join 的键、以及列集合。

    说明：
        - partial=true 表示仅提供最小字段集合（通常用于权限子查询/关联所需）。
    """
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    primary_key: str | None = None
    join_keys: list[str] = Field(default_factory=list)
    partial: bool = False
    columns: list[ColumnDef] = Field(default_factory=list)


class RelationshipDef(BaseModel):
    """表关系定义：用于描述常见外键/关联路径，服务于后续自动 join 推断。"""
    model_config = ConfigDict(extra="forbid")

    from_: str = Field(alias="from")
    to: str
    kind: str
    comment: str | None = None


class QueryPatternDef(BaseModel):
    """查询模式（SQL 模板）：将常见用户意图映射为可执行 SQL。"""
    model_config = ConfigDict(extra="forbid")

    name: str
    user_intent: str
    requires_permission: str | None = None
    sql: str


class DisplayFieldDef(BaseModel):
    """显示字段定义：用于配置不同类型查询应该显示的字段。"""
    model_config = ConfigDict(extra="forbid")

    name: str
    column: str
    display: bool = True
    fallback: str | None = None
    aggregate: bool = False


class PolicyCodeDictionaryItem(BaseModel):
    """
    策略子项字典条目（弱约束）。

    专用说明：
        你的策略 Code/Name1/Name2/Name3/nValue 组合非常多且演进频繁，
        这里使用 extra=allow 来容纳不同结构，避免频繁改模型导致校验失败。
    """
    model_config = ConfigDict(extra="allow")


class PolicyCodeDictionaryDef(BaseModel):
    """策略 Code 字典：描述某个 Code 下子项的字段含义与取值来源。"""
    model_config = ConfigDict(extra="forbid")

    code: str
    description: str | None = None
    items: list[PolicyCodeDictionaryItem] = Field(default_factory=list)


class DatabaseContext(BaseModel):
    """
    数据库上下文配置（schema metadata 的增强版）。

    该模型用于承载：
        - 表/列结构与语义（tables/columns/semantic_key）
        - 同义词（synonyms）
        - 权限模板（permissions/security）
        - 关系描述（relationships）
        - SQL 模板（query_patterns）
        - 显示字段配置（display_fields）
    """
    model_config = ConfigDict(extra="forbid")

    version: str
    db_type: str
    naming: NamingConfig | None = None
    security: SecurityConfig | None = None
    permissions: list[PermissionDef] = Field(default_factory=list)
    synonyms: dict[str, list[str]] = Field(default_factory=dict)
    tables: list[TableDef] = Field(default_factory=list)
    relationships: list[RelationshipDef] = Field(default_factory=list)
    policy_code_dictionary: list[PolicyCodeDictionaryDef] = Field(default_factory=list)
    query_patterns: list[QueryPatternDef] = Field(default_factory=list)
    display_fields: dict[str, list[DisplayFieldDef]] = Field(default_factory=dict)

