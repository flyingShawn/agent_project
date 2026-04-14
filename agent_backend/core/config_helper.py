"""
环境变量配置助手模块

文件功能：
    提供环境变量加载和数据库/LLM等核心配置的统一访问接口。
    封装dotenv加载逻辑，确保环境变量在首次访问前初始化。

在系统架构中的定位：
    位于核心基础层，是整个后端配置的入口点。
    所有需要读取环境变量的模块（LLM客户端、SQL执行器、RAG引擎等）均依赖此模块。

主要使用场景：
    - LLM客户端初始化时调用load_env_file()确保环境变量已加载
    - SQL执行器通过get_database_url()获取数据库连接地址
    - SQL工具通过get_max_rows()获取查询行数限制

核心函数：
    - load_env_file: 加载项目根目录.env文件，幂等设计（多次调用仅加载一次）
    - get_database_url: 构建数据库连接URL，支持MySQL和PostgreSQL
    - get_max_rows: 获取SQL查询最大行数限制

专有技术说明：
    - 使用全局标志_env_loaded实现幂等加载，避免重复解析.env文件
    - get_database_url优先使用DATABASE_URL完整连接串，其次从DB_HOST等组件变量拼接
    - 支持MySQL(pymysql驱动)和PostgreSQL(psycopg2驱动)两种数据库类型

关联文件：
    - agent_backend/agent/llm.py: 调用load_env_file()加载LLM配置
    - agent_backend/sql_agent/executor.py: 调用get_database_url()和get_max_rows()
    - agent_backend/agent/tools/sql_tool.py: 调用get_database_url()和get_max_rows()
    - agent_backend/api/v1/sql_agent.py: 调用get_max_rows()
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

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
        - mysql: 拼接为 mysql+pymysql://user:pass@host:port/db?charset=utf8mb4
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
