"""
统一配置加载模块

文件功能：
    合并原 config_helper.py（环境变量配置）和 config_loader.py（Schema YAML加载），
    提供项目所有配置的统一访问接口。

    环境变量部分：
    - 封装dotenv加载逻辑，确保环境变量在首次访问前初始化
    - 提供数据库连接URL构建、SQL查询行数限制等配置访问

    Schema元数据部分：
    - 加载schema_metadata.yaml配置文件，构建内存索引（SchemaRuntime）
    - 为SQL生成、元数据查询、模板匹配等模块提供统一的Schema数据访问接口

在系统架构中的定位：
    位于核心基础层，是整个后端配置的唯一入口点。
    所有需要读取环境变量或Schema元数据的模块均依赖此模块。

核心函数：
    - load_env_file: 加载项目根目录.env文件，幂等设计
    - get_database_url: 构建数据库连接URL，支持MySQL和PostgreSQL
    - get_max_rows: 获取SQL查询最大行数限制
    - get_schema_runtime: 获取SchemaRuntime单例（lru_cache缓存）

核心类：
    - ColumnSemantics: 列语义信息模型
    - SchemaRuntime: Schema运行时索引

关联文件：
    - agent_backend/core/schema_models.py: SchemaRoot等Pydantic模型定义
    - agent_backend/configs/schema_metadata.yaml: Schema元数据YAML配置
    - agent_backend/llm/factory.py: 调用load_env_file()加载LLM配置
    - agent_backend/sql_agent/executor.py: 调用get_database_url()和get_max_rows()
    - agent_backend/agent/tools/sql_tool.py: 调用get_database_url()和get_max_rows()
    - agent_backend/agent/tools/metadata_tool.py: 调用get_schema_runtime()
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

from agent_backend.core.schema_models import SchemaRoot

logger = logging.getLogger(__name__)

_env_loaded = False


def load_env_file() -> None:
    """
    加载项目根目录的.env环境变量文件。

    幂等设计：使用全局标志_env_loaded确保.env文件仅加载一次，
    后续调用直接返回，避免重复解析开销。

    加载逻辑：
        1. 检查_env_loaded标志，已加载则直接返回
        2. 定位项目根目录的.env文件（相对于本文件的上上上级目录）
        3. 若.env文件存在则调用load_dotenv加载
        4. 设置_env_loaded=True标记已加载
    """
    global _env_loaded
    if _env_loaded:
        return
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"\n环境变量已加载: {env_path}")
    _env_loaded = True


def get_database_url() -> str | None:
    """
    获取数据库连接URL。

    优先级：
        1. DATABASE_URL环境变量（完整连接串，优先级最高）
        2. 从DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD组件变量拼接

    参数：
        无（从环境变量读取）

    返回：
        str | None: 数据库连接URL，未配置时返回None

    支持的数据库类型：
        - mysql: 拼接为 mysql+pymysql://user:pass@host:port/db
        - postgresql: 拼接为 postgresql+psycopg2://user:pass@host:port/db

    安全注意事项：
        - 密码中的特殊字符需要URL编码
        - 未配置必要参数时返回None而非抛异常，由调用方决定处理方式
    """
    load_env_file()
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    db_type = os.getenv("DB_TYPE", "mysql").lower()
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    if not all([host, name, user]):
        return None
    if db_type == "postgresql":
        port = port or "5432"
        return f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"
    port = port or "3306"
    return f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"


def get_max_rows() -> int:
    """
    获取SQL查询最大返回行数限制。

    从SQL_MAX_ROWS环境变量读取，默认500行。
    该限制用于防止SQL查询返回过多数据导致内存溢出。

    参数：
        无（从环境变量读取）

    返回：
        int: 最大行数限制，默认500
    """
    load_env_file()
    return int(os.getenv("SQL_MAX_ROWS", "500"))


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
        synonyms: dict[str, list[str]]，同义词映射
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
