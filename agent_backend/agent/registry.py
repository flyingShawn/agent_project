"""
智能体注册表模块

文件功能：
    管理所有已启用智能体的配置、提示词和 Schema 运行时索引。
    启动时从 agents.yaml 加载智能体列表，为每个智能体加载
    独立的配置文件（prompts.yaml、schema_metadata.yaml、ops_reports.yaml）。

在系统架构中的定位：
    位于 Agent 编排层的基础设施，被 API 层、工具层、配置层等
    全局依赖，是智能体配置的唯一来源。

核心类：
    - AgentRegistry: 智能体注册表单例

使用方式：
    - registry = get_registry()
    - config = registry.get_agent_config("desk-agent")
    - prompt = registry.get_system_prompt("desk-agent")
    - schema = registry.get_schema_runtime("desk-agent")

关联文件：
    - agent_backend/configs/agents.yaml: 总控配置
    - agent_backend/configs/{config_dir}/prompts.yaml: 智能体提示词
    - agent_backend/configs/{config_dir}/schema_metadata.yaml: 数据库元数据
    - agent_backend/configs/{config_dir}/ops_reports.yaml: 运维简报配置
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from agent_backend.core.config import (
    AgentConfig,
    AgentLlmConfig,
    AgentRagConfig,
    SchemaRuntime,
    load_agents_yaml,
    reload_agents_yaml,
)
from agent_backend.core.schema_models import SchemaRoot

logger = logging.getLogger(__name__)

_CONFIGS_DIR = Path(__file__).parent.parent / "configs"

_DEFAULT_SYSTEM_PROMPT = "你是一个专业的AI助手，拥有以下工具能力：\n\n（默认提示词，请配置 configs/{config_dir}/prompts.yaml）"
_DEFAULT_SQL_SYSTEM_PROMPT = "你是一个专业的数据库查询助手，只返回 SQL 语句，不要包含任何解释或其他内容。"
_DEFAULT_SUMMARY_PROMPT = "你已达到最大工具调用次数限制，无法再调用任何工具。请基于已收集到的工具执行结果，为用户生成一个完整、有用的最终回答。如果已有查询结果数据，请务必在回答中包含具体的数据内容。"

_SQL_QUERY_RESULT_GUIDANCE = """【sql_query 结果解读补充规则】
- `rows` 字段最多只包含前 20 条预览，不代表全部结果。
- 回答前优先查看 `row_count`、`preview_row_count`、`export_row_count`、`has_more`、`overflow_capped` 和 `summary_hint`。
- 当 `row_count=0`，或 `result_state=empty`，或 `summary_hint` 已明确说明"暂未查询到相关数据"时，请直接用友好语气告知用户当前未查询到相关数据，不要继续调用 `sql_query` 反复验证。
- 当结果是单行单值且值为 `0`（例如 `COUNT(*)=0`）时，也按"未查询到相关数据"处理，不要因为 `row_count=1` 误判为查到了业务数据。
- 当 `has_more=true` 且 `overflow_capped=false` 时，先明确总量，再只概括前 20 条预览里的主要信息，不要把 20 条预览当成全部结果。
- 当 `overflow_capped=true` 时，不要声称知道精确总数，统一表述为"数据量过大，当前已导出前5000条"，并只基于前 20 条预览做概括。
- 当结果里已有 `download_url` 时，不要再次追问用户是否需要表格或下载链接，系统会自动展示。"""


class AgentRegistry:
    """
    智能体注册表

    启动时加载 agents.yaml，为每个启用的智能体加载独立配置，
    提供按 agent_type 查询配置、提示词、Schema 的接口。
    """

    _instance: AgentRegistry | None = None

    def __new__(cls) -> AgentRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._agents: dict[str, AgentConfig] = {}
        self._prompts: dict[str, dict] = {}
        self._schema_runtimes: dict[str, SchemaRuntime] = {}
        self._reports_configs: dict[str, dict] = {}
        self._load_all()

    def _load_all(self) -> None:
        agents = load_agents_yaml()
        for config in agents:
            self._agents[config.agent_type] = config
            self._load_agent_configs(config)
        logger.info(f"\nAgentRegistry 初始化完成，共加载 {len(self._agents)} 个智能体")

    def _load_agent_configs(self, config: AgentConfig) -> None:
        config_dir = _CONFIGS_DIR / config.config_dir
        if not config_dir.exists():
            logger.warning(f"\n智能体配置目录不存在: {config_dir}")
            return

        self._load_prompts(config.agent_type, config_dir)
        self._load_schema(config.agent_type, config_dir)
        if config.reports.enabled:
            self._load_reports(config.agent_type, config_dir)

    def _load_prompts(self, agent_type: str, config_dir: Path) -> None:
        prompts_path = config_dir / "prompts.yaml"
        if not prompts_path.exists():
            logger.warning(f"\n提示词配置文件不存在: {prompts_path}")
            self._prompts[agent_type] = {}
            return
        with open(prompts_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self._prompts[agent_type] = data or {}
        logger.info(f"\n已加载提示词: {agent_type} <- {prompts_path}")

    def _load_schema(self, agent_type: str, config_dir: Path) -> None:
        schema_path = config_dir / "schema_metadata.yaml"
        if not schema_path.exists():
            logger.warning(f"\nSchema元数据文件不存在: {schema_path}")
            return
        with open(schema_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        raw = SchemaRoot(**data)
        runtime = SchemaRuntime(raw=raw)
        self._schema_runtimes[agent_type] = runtime
        logger.info(f"\n已加载Schema: {agent_type} <- {schema_path} ({len(raw.tables)} 个表)")

    def _load_reports(self, agent_type: str, config_dir: Path) -> None:
        reports_path = config_dir / "ops_reports.yaml"
        if not reports_path.exists():
            logger.warning(f"\n报表配置文件不存在: {reports_path}")
            self._reports_configs[agent_type] = {}
            return
        with open(reports_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self._reports_configs[agent_type] = data or {}
        logger.info(f"\n已加载报表配置: {agent_type} <- {reports_path}")

    def get_agent_config(self, agent_type: str) -> AgentConfig:
        config = self._agents.get(agent_type)
        if config is None:
            raise ValueError(f"未找到智能体配置: {agent_type}")
        return config

    def get_system_prompt(self, agent_type: str) -> str:
        data = self._prompts.get(agent_type, {})
        prompt = data.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT.format(config_dir=agent_type)
        return f"{prompt}\n\n{_SQL_QUERY_RESULT_GUIDANCE}"

    def get_sql_system_prompt(self, agent_type: str) -> str:
        data = self._prompts.get(agent_type, {})
        return data.get("sql_system_prompt") or _DEFAULT_SQL_SYSTEM_PROMPT

    def get_sql_prompt_instructions(self, agent_type: str) -> str:
        data = self._prompts.get(agent_type, {})
        return data.get("sql_prompt_instructions") or ""

    def get_summary_prompt(self, agent_type: str) -> str:
        data = self._prompts.get(agent_type, {})
        prompt = data.get("summary_prompt") or _DEFAULT_SUMMARY_PROMPT
        return f"{prompt}\n\n{_SQL_QUERY_RESULT_GUIDANCE}"

    def get_schema_runtime(self, agent_type: str) -> SchemaRuntime:
        runtime = self._schema_runtimes.get(agent_type)
        if runtime is None:
            raise ValueError(f"未找到智能体Schema: {agent_type}")
        return runtime

    def get_database_url(self, agent_type: str) -> str | None:
        config = self.get_agent_config(agent_type)
        return config.database.build_url()

    def get_rag_config(self, agent_type: str) -> AgentRagConfig:
        config = self.get_agent_config(agent_type)
        return config.rag

    def get_llm_config(self, agent_type: str) -> AgentLlmConfig:
        config = self.get_agent_config(agent_type)
        return config.llm

    def get_reports_config(self, agent_type: str) -> dict:
        return self._reports_configs.get(agent_type, {})

    def get_enabled_agents(self) -> list[AgentConfig]:
        return list(self._agents.values())

    def get_default_agent_type(self) -> str:
        if self._agents:
            return next(iter(self._agents))
        raise ValueError("没有已启用的智能体")

    def has_agent(self, agent_type: str) -> bool:
        return agent_type in self._agents

    def reload(self) -> None:
        self._agents.clear()
        self._prompts.clear()
        self._schema_runtimes.clear()
        self._reports_configs.clear()
        reload_agents_yaml()
        self._load_all()
        logger.info("\nAgentRegistry 已重新加载")


def get_registry() -> AgentRegistry:
    return AgentRegistry()
