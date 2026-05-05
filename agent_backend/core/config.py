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
from dotenv import dotenv_values
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from agent_backend.core.schema_models import SchemaRoot

logger = logging.getLogger(__name__)

_env_loaded = False


def _apply_dotenv_values(env_path: Path) -> list[str]:
    """将 .env 中的键值写入进程环境，并在 Windows 下跳过会扰乱本地时区的 TZ。"""
    skipped_keys: list[str] = []
    for key, value in dotenv_values(env_path).items():
        if value is None or key in os.environ:
            continue
        if os.name == "nt" and key.upper() == "TZ":
            skipped_keys.append(key)
            continue
        os.environ[key] = value
    return skipped_keys


def load_env_file() -> None:
    """
    加载项目根目录的.env环境变量文件。

    幂等设计：使用全局标志_env_loaded确保.env文件仅加载一次，
    后续调用直接返回，避免重复解析开销。

    加载逻辑：
        1. 检查_env_loaded标志，已加载则直接返回
        2. 定位项目根目录的.env文件（相对于本文件的上上上级目录）
        3. 若.env文件存在则按当前平台规则写入进程环境
        4. 设置_env_loaded=True标记已加载
    """
    global _env_loaded
    if _env_loaded:
        return
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        skipped_keys = _apply_dotenv_values(env_path)
        if skipped_keys:
            logger.info("  Windows 跳过 TZ，避免本地时区错乱")
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
    rag_qdrant_collection: str = ""
    rag_sql_qdrant_collection: str = ""
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
    agent_name: str = ""
    tavily_api_key: str = ""
    web_search_max_results: int = 5
    sql_log_full_prompt: bool = True
    external_entry_secret: str = ""
    external_entry_ttl_seconds: int = 28800
    third_party_chat_history_base_url: str = ""
    third_party_chat_history_timeout_seconds: float = 3
    chat_max_history_rounds: int = 6
    chat_history_compress_threshold: int = 500
    chat_topic_shift_threshold: float = 0.15

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


def get_database_url(agent_type: str | None = None) -> str | None:
    if agent_type is not None:
        try:
            from agent_backend.agent.registry import get_registry
            registry = get_registry()
            if registry.has_agent(agent_type):
                url = registry.get_database_url(agent_type)
                if url:
                    return url
        except Exception:
            pass
    load_env_file()
    return get_settings().build_database_url()


def get_max_rows() -> int:
    load_env_file()
    return get_settings().database.sql_max_rows


_DEFAULT_SYSTEM_PROMPT = "你是一个专业的AI助手，拥有以下工具能力：\n\n（默认提示词，请配置 configs/{config_dir}/prompts.yaml）"
_DEFAULT_SQL_SYSTEM_PROMPT = "你是一个专业的数据库查询助手，只返回 SQL 语句，不要包含任何解释或其他内容。"
_DEFAULT_SUMMARY_PROMPT = "你已达到最大工具调用次数限制，无法再调用任何工具。请基于已收集到的工具执行结果，为用户生成一个完整、有用的最终回答。如果已有查询结果数据，请务必在回答中包含具体的数据内容。"
_DEFAULT_SQL_PROMPT_INSTRUCTIONS = """你是一个严谨的数据库 SQL 助手。
只输出 SQL 本体，不要输出解释、不要 Markdown。
只使用 SELECT 语句，禁止 INSERT/UPDATE/DELETE/DROP 等。
禁止返回敏感列。

【重要】表别名规则（必须严格遵守）：
1. 定义别名后，整个SQL中必须使用别名，不能再用原表名
2. 示例：FROM table_name t 之后，必须用 t.id，不能用 table_name.id
3. 所有表用单字母别名，且全程保持一致

【重要】SQL生成原则：
1. 优先使用简单的SQL，避免不必要的子查询
2. 如果只是统计数量，用 SELECT COUNT(*) FROM 表名 即可
3. 如果只是查询所有某个表数据，用 SELECT * FROM 表名 即可

【重要】列别名规则（必须严格遵守）：
SELECT 中的每个列必须使用 AS 设置中文别名，别名来源于下方「数据库表与列」中该列的 comment（括号内的语义说明）或「参考SQL样本」中的别名写法。
中文别名必须用双引号包裹，示例：SELECT t.name AS "名称", t.ip AS "IP地址"
聚合函数同样需要中文别名：SELECT COUNT(*) AS "数量", SUM(t.value) AS "合计"

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

【最重要】【参考SQL样本（必须严格模仿）最优先参考】
如果有参考SQL样本，你必须严格模仿其写法风格，包括：
- 表关联方式（JOIN条件和关联表）
- 别名规则
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
    return {}


def get_system_prompt(agent_type: str | None = None) -> str:
    if agent_type is not None:
        try:
            from agent_backend.agent.registry import get_registry
            registry = get_registry()
            if registry.has_agent(agent_type):
                return registry.get_system_prompt(agent_type)
        except Exception:
            pass
    data = _load_prompts_yaml()
    prompt = data.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT
    return f"{prompt}\n\n{_SQL_QUERY_RESULT_GUIDANCE}"


def get_sql_system_prompt(agent_type: str | None = None) -> str:
    if agent_type is not None:
        try:
            from agent_backend.agent.registry import get_registry
            registry = get_registry()
            if registry.has_agent(agent_type):
                return registry.get_sql_system_prompt(agent_type)
        except Exception:
            pass
    data = _load_prompts_yaml()
    return data.get("sql_system_prompt") or _DEFAULT_SQL_SYSTEM_PROMPT


def get_summary_prompt(agent_type: str | None = None) -> str:
    if agent_type is not None:
        try:
            from agent_backend.agent.registry import get_registry
            registry = get_registry()
            if registry.has_agent(agent_type):
                return registry.get_summary_prompt(agent_type)
        except Exception:
            pass
    data = _load_prompts_yaml()
    prompt = data.get("summary_prompt") or _DEFAULT_SUMMARY_PROMPT
    return f"{prompt}\n\n{_SQL_QUERY_RESULT_GUIDANCE}"


def get_sql_prompt_instructions(agent_type: str | None = None) -> str:
    if agent_type is not None:
        try:
            from agent_backend.agent.registry import get_registry
            registry = get_registry()
            if registry.has_agent(agent_type):
                instructions = registry.get_sql_prompt_instructions(agent_type)
                if instructions:
                    return instructions
        except Exception:
            pass
    data = _load_prompts_yaml()
    return data.get("sql_prompt_instructions") or _DEFAULT_SQL_PROMPT_INSTRUCTIONS


def get_sql_log_full_prompt() -> bool:
    load_env_file()
    return bool(get_settings().misc.sql_log_full_prompt)


def get_chat_max_history_rounds() -> int:
    load_env_file()
    return get_settings().misc.chat_max_history_rounds


def get_chat_history_compress_threshold() -> int:
    load_env_file()
    return get_settings().misc.chat_history_compress_threshold


def get_chat_topic_shift_threshold() -> float:
    load_env_file()
    return get_settings().misc.chat_topic_shift_threshold


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


def get_schema_runtime(agent_type: str | None = None) -> SchemaRuntime:
    if agent_type is not None:
        try:
            from agent_backend.agent.registry import get_registry
            registry = get_registry()
            if registry.has_agent(agent_type):
                return registry.get_schema_runtime(agent_type)
        except Exception:
            pass
    try:
        from agent_backend.agent.registry import get_registry
        registry = get_registry()
        default_type = registry.get_default_agent_type()
        return registry.get_schema_runtime(default_type)
    except Exception:
        pass
    raise FileNotFoundError("Schema元数据未找到：请配置 agents.yaml 和 configs/{agent_type}/schema_metadata.yaml")


def reload_schema_runtime() -> SchemaRuntime:
    logger.info("\nSchema元数据缓存已清除，重新加载...")
    return get_schema_runtime()


class AgentLlmConfig(BaseModel):
    llm_base_url: str = ""
    llm_api_key: str = ""
    chat_model: str = ""
    vision_model: str = ""


class AgentDatabaseConfig(BaseModel):
    db_type: str = "mysql"
    db_host: str = ""
    db_port: str = ""
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""

    def build_url(self) -> str | None:
        if not all([self.db_host, self.db_name, self.db_user]):
            return None
        db_type = self.db_type.lower()
        if db_type == "postgresql":
            port = self.db_port or "5432"
            return f"postgresql+psycopg2://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}@{self.db_host}:{port}/{self.db_name}"
        port = self.db_port or "3306"
        return f"mysql+pymysql://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}@{self.db_host}:{port}/{self.db_name}"


class AgentRagConfig(BaseModel):
    docs_dir: str = ""
    docs_collection: str = ""
    sql_dir: str = ""
    sql_collection: str = ""


class AgentReportConfig(BaseModel):
    enabled: bool = False


class AgentTaskConfig(BaseModel):
    enabled: bool = False
    api_base_url: str = ""


class AgentConfig(BaseModel):
    agent_type: str
    display_name: str = ""
    enabled: bool = True
    config_dir: str = ""
    llm: AgentLlmConfig = AgentLlmConfig()
    database: AgentDatabaseConfig = AgentDatabaseConfig()
    rag: AgentRagConfig = AgentRagConfig()
    reports: AgentReportConfig = AgentReportConfig()
    tasks: AgentTaskConfig = AgentTaskConfig()

    def model_post_init(self, __context: object) -> None:
        if not self.config_dir:
            self.config_dir = self.agent_type


_AGENTS_YAML_PATH = Path(__file__).parent.parent / "configs" / "agents.yaml"
_agents_config_cache: list[AgentConfig] | None = None


def _expand_env_vars(value: str) -> str:
    return os.path.expandvars(value)


def _expand_config_env(obj: dict) -> dict:
    result = {}
    for key, value in obj.items():
        if isinstance(value, str):
            result[key] = _expand_env_vars(value)
        elif isinstance(value, dict):
            result[key] = _expand_config_env(value)
        else:
            result[key] = value
    return result


def load_agents_yaml() -> list[AgentConfig]:
    global _agents_config_cache
    if _agents_config_cache is not None:
        return _agents_config_cache

    load_env_file()

    yaml_path = _AGENTS_YAML_PATH
    if not yaml_path.exists():
        logger.warning(f"\n智能体总控配置文件不存在: {yaml_path}")
        return []

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    agents_data = data.get("agents") or []
    configs: list[AgentConfig] = []
    for item in agents_data:
        expanded = _expand_config_env(item)
        config = AgentConfig(**expanded)
        if config.enabled:
            configs.append(config)
            logger.info(f"\n已加载智能体配置: {config.agent_type} ({config.display_name})")
        else:
            logger.info(f"\n跳过已禁用智能体: {config.agent_type}")

    _agents_config_cache = configs
    logger.info(f"\n共加载 {len(configs)} 个启用的智能体")
    return configs


def reload_agents_yaml() -> list[AgentConfig]:
    global _agents_config_cache
    _agents_config_cache = None
    logger.info("\n智能体总控配置缓存已清除，重新加载...")
    return load_agents_yaml()
