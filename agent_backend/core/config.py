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
from pydantic_settings import BaseSettings

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


class LlmSettings(BaseSettings):
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    chat_model: str = "qwen3.5:9b"
    vision_model: str = "qwen3.5:9b"
    ollama_base_url: str = "http://localhost:11434"

    model_config = {"env_file": ".env", "extra": "ignore"}


class DatabaseSettings(BaseSettings):
    database_url: str = ""
    db_type: str = "mysql"
    db_host: str = ""
    db_port: str = ""
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""
    sql_max_rows: int = 500

    model_config = {"env_file": ".env", "extra": "ignore"}


class RagSettings(BaseSettings):
    rag_qdrant_url: str = "http://localhost:6333"
    rag_qdrant_path: str | None = None
    rag_qdrant_api_key: str | None = None
    rag_qdrant_collection: str = "desk_agent_docs"
    rag_sql_qdrant_collection: str = "desk_agent_sql"
    rag_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    rag_top_k: int = 5
    rag_vector_min_score: float = 0.5
    rag_hybrid_alpha: float = 0.7
    rag_candidate_k: int = 30
    rag_sql_top_k: int = 3
    rag_sql_candidate_k: int = 15
    rag_sql_hybrid_alpha: float = 0.8

    model_config = {"env_file": ".env", "extra": "ignore"}


class MiscSettings(BaseSettings):
    chat_db_path: str = "data/chat_history.db"
    cors_origins: str = "http://localhost:3000"
    agent_name: str = "desk-agent"
    tavily_api_key: str = ""
    web_search_max_results: int = 5
    sql_log_full_prompt: bool = True
    external_entry_secret: str = ""
    external_entry_ttl_seconds: int = 28800
    third_party_chat_history_base_url: str = ""
    third_party_chat_history_timeout_seconds: float = 3

    model_config = {"env_file": ".env", "extra": "ignore"}


class AppSettings(BaseModel):
    llm: LlmSettings = LlmSettings()
    database: DatabaseSettings = DatabaseSettings()
    rag: RagSettings = RagSettings()
    misc: MiscSettings = MiscSettings()

    def build_database_url(self) -> str | None:
        if self.database.database_url:
            return self.database.database_url
        db = self.database
        if not all([db.db_host, db.db_name, db.db_user]):
            return None
        db_type = db.db_type.lower()
        if db_type == "postgresql":
            port = db.db_port or "5432"
            return f"postgresql+psycopg2://{quote_plus(db.db_user)}:{quote_plus(db.db_password)}@{db.db_host}:{port}/{db.db_name}"
        port = db.db_port or "3306"
        return f"mysql+pymysql://{quote_plus(db.db_user)}:{quote_plus(db.db_password)}@{db.db_host}:{port}/{db.db_name}"


_settings_instance: AppSettings | None = None


def get_settings() -> AppSettings:
    global _settings_instance
    if _settings_instance is None:
        load_env_file()
        _settings_instance = AppSettings()
        logger.info("\n已生效配置摘要:")
        logger.info(f"  LLM: base_url={_settings_instance.llm.llm_base_url}, model={_settings_instance.llm.chat_model}")
        logger.info(f"  DB: type={_settings_instance.database.db_type}, host={_settings_instance.database.db_host}")
        logger.info(f"  RAG: qdrant_url={_settings_instance.rag.rag_qdrant_url}, collection={_settings_instance.rag.rag_qdrant_collection}")
        logger.info(f"  Misc: agent_name={_settings_instance.misc.agent_name}, cors={_settings_instance.misc.cors_origins}")
    return _settings_instance


def get_database_url() -> str | None:
    load_env_file()
    return get_settings().build_database_url()


def get_max_rows() -> int:
    load_env_file()
    return get_settings().database.sql_max_rows


_SCHEMA_YAML_PATH = Path(__file__).parent.parent / "configs" / "schema_metadata.yaml"
_PROMPTS_YAML_PATH = Path(__file__).parent.parent / "configs" / "prompts.yaml"

_DEFAULT_SYSTEM_PROMPT = """你是一个专业的桌面管理系统AI助手，拥有以下工具能力：\n\n（默认提示词，请配置 configs/prompts.yaml）"""
_DEFAULT_SQL_SYSTEM_PROMPT = "你是一个专业的数据库查询助手，只返回 SQL 语句，不要包含任何解释或其他内容。"
_DEFAULT_SUMMARY_PROMPT = "你已达到最大工具调用次数限制，无法再调用任何工具。请基于已收集到的工具执行结果，为用户生成一个完整、有用的最终回答。如果已有查询结果数据，请务必在回答中包含具体的数据内容。"
_DEFAULT_SQL_PROMPT_INSTRUCTIONS = """你是一个严谨的数据库 SQL 助手。
只输出 SQL 本体，不要输出解释、不要 Markdown。
只使用 SELECT 语句，禁止 INSERT/UPDATE/DELETE/DROP 等。
禁止返回敏感列。

【重要】表别名规则（必须严格遵守）：
1. 定义别名后，整个SQL中必须使用别名，不能再用原表名
2. 示例：FROM s_group g 之后，必须用 g.id，不能用 s_group.id
3. 常用别名：s_machine 用 m，s_group 用 g，s_user 用 u，admininfo 用 a
4. 其他表用单字母别名，且全程保持一致

【重要】SQL生成原则：
1. 优先使用简单的SQL，避免不必要的子查询
2. 如果只是统计数量，用 SELECT COUNT(*) FROM 表名 即可
3. 如果只是查询所有某个表数据，用 SELECT * FROM 表名 即可

【重要】列别名规则（必须严格遵守）：
SELECT 中的每个列必须使用 AS 设置中文别名，别名来源于下方「数据库表与列」中该列的 comment（括号内的语义说明）或「参考SQL样本」中的别名写法。
中文别名必须用双引号包裹，示例：SELECT m.Name_C AS "设备名称", m.Ip_C AS "IP地址", g.GroupName AS "部门名称"
聚合函数同样需要中文别名：SELECT COUNT(*) AS "数量", SUM(h.Memory) AS "内存合计"

【重要】字段使用约束（必须严格遵守）：
禁止使用任何未在下方「数据库表与列」或「参考SQL样本」中出现的字段名。
只能使用以下来源中明确列出的字段：
  - 「数据库表与列」中列出的列名（括号内为语义别名）
  - 「参考SQL样本」中出现的列名
如果用户问题涉及的字段不在上述来源中，只使用最接近的已知字段，绝不编造不存在的字段。

【重要】禁止重复字段（必须严格遵守）：
SELECT子句中禁止出现重复的字段或别名，每个字段只选一次。
如果多个表有同名字段，只选择最相关的那一个，不要重复选取。
生成SQL后请自查：如果SELECT中有两个以上相同或语义重复的列，删除多余的。
示例错误：SELECT m.Name_C AS "设备名称", m.Name_C AS "设备名" ← 同一字段重复
示例正确：SELECT m.Name_C AS "设备名称" ← 只选一次

【最重要】【参考SQL样本（必须严格模仿）最优先参考】
如果有参考SQL样本，你必须严格模仿其写法风格，包括：
- 表关联方式（JOIN条件和关联表）
- 别名规则（s_machine用m，s_group用g等）
- 列别名写法（AS "中文别名"，中文别名必须用双引号包裹）
- WHERE条件构建方式
- 聚合函数使用方式
如果没有参考SQL样本，请按照最简洁规范的SQL写法生成。

【再次强调】SELECT中禁止重复字段！每个列只选一次，不要出现同名字段或语义重复的列。"""

_SQL_QUERY_RESULT_GUIDANCE = """【sql_query 结果解读补充规则】
- `rows` 字段最多只包含前 20 条预览，不代表全部结果。
- 回答前优先查看 `row_count`、`preview_row_count`、`export_row_count`、`has_more`、`overflow_capped` 和 `summary_hint`。
- 当 `row_count=0`，或 `result_state=empty`，或 `summary_hint` 已明确说明“暂未查询到相关数据”时，请直接用友好语气告知用户当前未查询到相关数据，不要继续调用 `sql_query` 反复验证。
- 当结果是单行单值且值为 `0`（例如 `COUNT(*)=0`）时，也按“未查询到相关数据”处理，不要因为 `row_count=1` 误判为查到了业务数据。
- 当 `has_more=true` 且 `overflow_capped=false` 时，先明确总量，再只概括前 20 条预览里的主要信息，不要把 20 条预览当成全部结果。
- 当 `overflow_capped=true` 时，不要声称知道精确总数，统一表述为“数据量过大，当前已导出前5000条”，并只基于前 20 条预览做概括。
- 当结果里已有 `download_url` 时，不要再次追问用户是否需要表格或下载链接，系统会自动展示。"""


@lru_cache(maxsize=1)
def _load_prompts_yaml() -> dict:
    yaml_path = _PROMPTS_YAML_PATH
    if not yaml_path.exists():
        logger.warning(f"\n提示词配置文件不存在: {yaml_path}，使用默认值")
        return {}
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    logger.info(f"\n提示词配置已加载: {yaml_path}")
    return data or {}


def get_system_prompt() -> str:
    data = _load_prompts_yaml()
    prompt = data.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT
    return f"{prompt}\n\n{_SQL_QUERY_RESULT_GUIDANCE}"


def get_sql_system_prompt() -> str:
    data = _load_prompts_yaml()
    return data.get("sql_system_prompt") or _DEFAULT_SQL_SYSTEM_PROMPT


def get_summary_prompt() -> str:
    data = _load_prompts_yaml()
    prompt = data.get("summary_prompt") or _DEFAULT_SUMMARY_PROMPT
    return f"{prompt}\n\n{_SQL_QUERY_RESULT_GUIDANCE}"


def get_sql_prompt_instructions() -> str:
    data = _load_prompts_yaml()
    return data.get("sql_prompt_instructions") or _DEFAULT_SQL_PROMPT_INSTRUCTIONS


def get_sql_log_full_prompt() -> bool:
    load_env_file()
    return bool(get_settings().misc.sql_log_full_prompt)


def reload_prompts() -> dict:
    _load_prompts_yaml.cache_clear()
    logger.info("\n提示词配置缓存已清除，重新加载...")
    return _load_prompts_yaml()


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


_schema_runtime_cache: SchemaRuntime | None = None


def get_schema_runtime() -> SchemaRuntime:
    global _schema_runtime_cache
    if _schema_runtime_cache is not None:
        return _schema_runtime_cache

    yaml_path = _SCHEMA_YAML_PATH
    if not yaml_path.exists():
        raise FileNotFoundError(f"Schema元数据文件不存在: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    raw = SchemaRoot(**data)
    runtime = SchemaRuntime(raw=raw)
    _schema_runtime_cache = runtime
    logger.info(f"\nSchema元数据已加载: {len(raw.tables)} 个表, {len(raw.synonyms or {})} 组同义词")
    return runtime


def reload_schema_runtime() -> SchemaRuntime:
    global _schema_runtime_cache
    _schema_runtime_cache = None
    logger.info("\nSchema元数据缓存已清除，重新加载...")
    return get_schema_runtime()
