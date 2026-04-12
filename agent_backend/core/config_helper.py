"""
配置助手模块

文件功能：
    从 .env 文件加载环境变量，并为数据库连接、Ollama 大模型、SQL 查询限制等
    提供统一的配置获取接口。支持 MySQL 和 PostgreSQL 两种数据库的 URL 自动拼装。

核心作用与设计目的：
    - 将分散的环境变量归一化为可直接使用的配置值
    - 支持 DATABASE_URL 直接配置和 DB_HOST/DB_PORT/DB_USER 等分离配置两种方式
    - 数据库密码自动 URL 编码，避免特殊字符导致连接失败
    - 模块导入时自动加载 .env 文件，确保后续调用无需手动初始化

主要使用场景：
    - SQL Agent 获取数据库连接 URL 和最大查询行数
    - LLM 客户端获取 Ollama 服务地址和模型名称
    - 运维脚本通过 print_config_status() 快速检查配置完整性

包含的主要函数：
    - load_env_file(): 加载 .env 文件到环境变量（不覆盖已存在的变量）
    - get_database_url(): 获取数据库连接 URL，支持 MySQL/PostgreSQL 自动拼装
    - get_ollama_config(): 获取 Ollama 大模型配置（base_url, chat_model, vision_model）
    - get_max_rows(): 获取 SQL 查询默认最大行数限制
    - print_config_status(): 打印当前所有配置状态（用于运维诊断）

相关联的调用文件：
    - agent_backend/sql_agent/executor.py: 调用 get_database_url() 和 get_max_rows()
    - agent_backend/sql_agent/service.py: 间接通过 executor 使用数据库配置
    - agent_backend/llm/clients.py: 使用 OLLAMA_BASE_URL/CHAT_MODEL/VISION_MODEL 环境变量
    - agent_backend/chat/handlers.py: 调用 get_database_url() 检查数据库可用性
"""
from __future__ import annotations

import os
import urllib.parse
from pathlib import Path


def load_env_file(env_file: Path | None = None) -> None:
    """
    加载 .env 文件到环境变量。

    行为：
        - 逐行解析 .env 文件，跳过空行和 # 开头的注释行
        - 仅在环境变量尚未设置时才写入（不覆盖已有值）
        - 文件不存在时静默返回，不抛异常

    参数：
        env_file: .env 文件路径，默认为项目根目录（agent_backend 的上级目录）下的 .env
    """
    if env_file is None:
        env_file = Path(__file__).parent.parent.parent / ".env"
    
    if not env_file.exists():
        return
    
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if key not in os.environ:
                    os.environ[key] = value


def get_database_url() -> str | None:
    """
    获取数据库连接 URL。

    优先级：
        1. 环境变量 DATABASE_URL（直接使用，不做任何处理）
        2. 从分离配置项自动拼装（DB_TYPE, DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME）

    拼装规则：
        - MySQL: mysql+pymysql://{user}:{encoded_password}@{host}:{port}/{db}?charset=utf8mb4
        - PostgreSQL: postgresql://{user}:{encoded_password}@{host}:{port}/{db}
        - 密码中的特殊字符会自动进行 URL 编码

    返回：
        str | None: 数据库连接 URL；若必需配置缺失（DB_HOST/DB_NAME/DB_USER）则返回 None。

    安全注意事项：
        - 密码通过 urllib.parse.quote 编码，防止特殊字符破坏 URL 格式
        - 返回的 URL 包含明文密码，不应记录到日志中
    """
    load_env_file()
    
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return database_url
    
    db_type = os.getenv("DB_TYPE", "mysql").lower()
    db_host = os.getenv("DB_HOST", "").strip()
    db_port = os.getenv("DB_PORT", "").strip()
    db_name = os.getenv("DB_NAME", "").strip()
    db_user = os.getenv("DB_USER", "").strip()
    db_password = os.getenv("DB_PASSWORD", "").strip()
    
    if not all([db_host, db_name, db_user]):
        return None
    
    encoded_password = urllib.parse.quote(db_password, safe='')
    
    if db_type == "mysql":
        port = db_port or "3306"
        return f"mysql+pymysql://{db_user}:{encoded_password}@{db_host}:{port}/{db_name}?charset=utf8mb4"
    elif db_type == "postgresql":
        port = db_port or "5432"
        return f"postgresql://{db_user}:{encoded_password}@{db_host}:{port}/{db_name}"
    else:
        return None


def get_ollama_config() -> dict:
    """
    获取大模型服务配置。

    返回：
        dict: 包含以下键的配置字典：
            - base_url (str): LLM 服务地址，默认 http://localhost:11434/v1
            - api_key (str): LLM API Key，默认为空（本地模式不需要）
            - chat_model (str): 文本对话模型名称，默认 qwen2.5:7b
            - vision_model (str): 视觉模型名称，默认 qwen2.5-vl:7b
    """
    load_env_file()
    
    return {
        "base_url": os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        "api_key": os.getenv("LLM_API_KEY", ""),
        "chat_model": os.getenv("CHAT_MODEL", "qwen2.5:7b"),
        "vision_model": os.getenv("VISION_MODEL", "qwen2.5-vl:7b"),
    }


def get_max_rows() -> int:
    """
    获取 SQL 查询默认最大行数限制。

    返回：
        int: 最大行数，取自环境变量 SQL_MAX_ROWS，默认 500。
             若环境变量值无法转为整数则回退为默认值。
    """
    load_env_file()
    try:
        return int(os.getenv("SQL_MAX_ROWS", "500"))
    except (ValueError, TypeError):
        return 500


def print_config_status():
    """
    打印当前所有配置状态到标准输出。

    输出内容：
        - 大模型配置：Ollama 地址、对话模型、视觉模型
        - 数据库配置：类型、主机、端口、数据库名、用户名、配置状态
        - RAG 配置：文档目录、Qdrant 地址、SQL 样本目录和集合

    使用场景：
        - 运维诊断：快速确认服务启动时各项配置是否正确
        - 可通过 python -m agent_backend.core.config_helper 直接运行
    """
    load_env_file()
    
    print("\n" + "="*60)
    print("  配置状态检查")
    print("="*60)
    
    print("\n【大模型配置】")
    ollama_config = get_ollama_config()
    print(f"  LLM地址: {ollama_config['base_url']}")
    print(f"  API Key: {'已配置' if ollama_config['api_key'] else '未配置(本地模式)'}")
    print(f"  对话模型: {ollama_config['chat_model']}")
    print(f"  视觉模型: {ollama_config['vision_model']}")
    
    print("\n【数据库配置】")
    db_url = get_database_url()
    if db_url:
        db_type = os.getenv("DB_TYPE", "mysql")
        db_host = os.getenv("DB_HOST", "未配置")
        db_port = os.getenv("DB_PORT", "默认")
        db_name = os.getenv("DB_NAME", "未配置")
        db_user = os.getenv("DB_USER", "未配置")
        
        print(f"  数据库类型: {db_type}")
        print(f"  主机地址: {db_host}")
        print(f"  端口: {db_port}")
        print(f"  数据库名: {db_name}")
        print(f"  用户名: {db_user}")
        print(f"  ✅ 数据库已配置")
    else:
        print("  ❌ 数据库未配置")
        print("  请在.env文件中配置数据库连接信息")
    
    print("\n【RAG配置】")
    rag_docs_dir = os.getenv("RAG_DOCS_DIR", "./data/desk-agent/docs")
    qdrant_url = os.getenv("RAG_QDRANT_URL", "http://localhost:6333")
    print(f"  文档目录: {rag_docs_dir}")
    print(f"  Qdrant地址: {qdrant_url}")

    sql_dir = os.getenv("RAG_SQL_DIR", "./data/desk-agent/sql")
    sql_collection = os.getenv("RAG_SQL_QDRANT_COLLECTION", "desk_agent_sql")
    print(f"  SQL样本目录: {sql_dir}")
    print(f"  SQL样本集合: {sql_collection}")
    
    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    print_config_status()


# 模块导入时自动加载.env文件
load_env_file()
