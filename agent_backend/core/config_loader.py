"""
Schema元数据配置加载器

文件目的：
    - 加载和解析 schema_metadata.yaml 配置文件
    - 构建内存索引，提供快速查询能力
    - 使用缓存机制避免重复加载

核心功能：
    1. 读取YAML配置文件
    2. 校验配置结构（使用Pydantic模型）
    3. 构建运行时索引（按表、按列路径、按语义键）
    4. 提供单例缓存（lru_cache）

主要类：
    - ColumnSemantic: 列语义信息
    - SchemaRuntime: 运行时索引结构

主要函数：
    - get_schema_runtime(): 获取schema运行时索引（带缓存）

调用流程：
    API请求 -> get_schema_runtime() 
    -> _read_yaml() 读取YAML
    -> _validate() 校验结构
    -> _build_runtime() 构建索引
    -> 返回SchemaRuntime对象

相关文件：
    - agent_backend/core/schema_models.py: Pydantic模型定义
    - agent_backend/configs/schema_metadata.yaml: 配置文件
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from agent_backend.core.errors import AppError
from agent_backend.core.schema_models import DatabaseContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ColumnSemantic:
    """
    列语义信息（内存索引的最小单元）。

    设计目的：
        - 将 YAML 中的 columns 定义归一为可高效检索的结构
        - 支持通过 column_path 或 semantic_key 快速定位列
    """
    table: str
    column: str
    column_path: str
    semantic_key: str
    type: str
    comment: str | None
    examples: list[Any]


@dataclass(frozen=True)
class SchemaRuntime:
    """
    schema_metadata.yaml 解析后的运行时结构（只读）。

    tree:
        table -> column_name -> ColumnSemantic
    by_column_path:
        "table.column" -> ColumnSemantic
    by_semantic:
        semantic_key -> [ColumnSemantic, ...]
    synonyms:
        "table.column" -> [同义词, ...]
    """
    raw: DatabaseContext
    tree: dict[str, dict[str, ColumnSemantic]]
    by_column_path: dict[str, ColumnSemantic]
    by_semantic: dict[str, list[ColumnSemantic]]
    synonyms: dict[str, list[str]]


def _default_metadata_path() -> Path:
    """
    返回默认的 schema_metadata.yaml 路径。

    约定：
        - 后端工程目录：agent_backend/
        - 配置目录：agent_backend/configs/
    """
    return Path(__file__).resolve().parents[1] / "configs" / "schema_metadata.yaml"


def _read_yaml(path: Path) -> dict:
    """
    读取并解析 YAML 文件为 Python dict（仅做语法层解析）。

    参数：
        path: YAML 文件路径。

    返回：
        dict: YAML 根节点映射。

    异常：
        - 配置不存在：抛 AppError(config_not_found)
        - YAML 解析失败：抛 AppError(config_parse_error)
        - 根节点不是 mapping：抛 AppError(config_schema_error)

    说明：
        - 该方法为内部专用方法；结构校验由 _validate 完成。
    """
    if not path.exists():
        raise AppError(
            code="config_not_found",
            message=f"schema metadata not found: {path}",
            http_status=500,
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise AppError(
            code="config_parse_error",
            message=f"failed to parse yaml: {path}",
            http_status=500,
            details={"reason": str(e)},
        ) from e
    if not isinstance(data, dict):
        raise AppError(
            code="config_schema_error",
            message=f"yaml root must be a mapping: {path}",
            http_status=500,
        )
    return data


def _validate(metadata_dict: dict) -> DatabaseContext:
    """
    对 YAML 解析结果进行结构校验并转为强类型对象。

    参数：
        metadata_dict: 来自 _read_yaml 的 dict。

    返回：
        DatabaseContext: 通过 Pydantic 校验后的对象。

    异常：
        - 校验失败：抛 AppError(config_schema_error)，details 中包含原因。
    """
    try:
        return DatabaseContext.model_validate(metadata_dict)
    except Exception as e:
        raise AppError(
            code="config_schema_error",
            message="schema metadata validation failed",
            http_status=500,
            details={"reason": str(e)},
        ) from e


def _build_runtime(raw: DatabaseContext) -> SchemaRuntime:
    """
    基于 DatabaseContext 构建运行时内存索引。

    构建内容：
        - tree：按表聚合列定义
        - by_column_path：按 "table.column" 快速定位
        - by_semantic：按 semantic_key 聚合，便于语义检索

    异常：
        - 表名重复/列名重复：抛 AppError(config_schema_error)

    说明：
        - 该方法为内部专用方法；索引一旦构建完成即作为只读数据使用。
    """
    tree: dict[str, dict[str, ColumnSemantic]] = {}
    by_column_path: dict[str, ColumnSemantic] = {}
    by_semantic: dict[str, list[ColumnSemantic]] = {}

    table_names: set[str] = set()
    for t in raw.tables:
        if t.name in table_names:
            raise AppError(
                code="config_schema_error",
                message=f"duplicate table name: {t.name}",
                http_status=500,
            )
        table_names.add(t.name)

        column_map: dict[str, ColumnSemantic] = {}
        column_names: set[str] = set()
        for c in t.columns:
            if c.name in column_names:
                raise AppError(
                    code="config_schema_error",
                    message=f"duplicate column name: {t.name}.{c.name}",
                    http_status=500,
                )
            column_names.add(c.name)

            column_path = f"{t.name}.{c.name}"
            cs = ColumnSemantic(
                table=t.name,
                column=c.name,
                column_path=column_path,
                semantic_key=c.semantic_key,
                type=c.type,
                comment=c.comment,
                examples=list(c.examples),
            )
            column_map[c.name] = cs
            by_column_path[column_path] = cs
            by_semantic.setdefault(c.semantic_key, []).append(cs)

        tree[t.name] = column_map

    return SchemaRuntime(
        raw=raw,
        tree=tree,
        by_column_path=by_column_path,
        by_semantic=by_semantic,
        synonyms=raw.synonyms,
    )


@lru_cache(maxsize=1)
def get_schema_runtime(path: str | Path | None = None) -> SchemaRuntime:
    """
    加载 schema_metadata.yaml 并返回运行时索引（带进程内缓存）。

    参数：
        path: 可选，自定义 schema_metadata.yaml 路径；为空则使用默认路径。

    返回：
        SchemaRuntime: 构建完成的只读索引对象。

    缓存：
        - 该方法使用 lru_cache(maxsize=1) 做进程内缓存，避免重复解析与校验。
        - 若你在开发期修改了 YAML，需要重启进程才能生效（或手动清理缓存）。
    """
    p = Path(path) if path is not None else _default_metadata_path()
    raw_dict = _read_yaml(p)
    raw = _validate(raw_dict)
    runtime = _build_runtime(raw)
    logger.info(
        "schema_metadata_loaded version=%s tables=%s columns=%s",
        raw.version,
        len(runtime.tree),
        len(runtime.by_column_path),
    )
    return runtime

