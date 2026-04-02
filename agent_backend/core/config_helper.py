"""
配置助手模块

文件目的：
    - 从.env文件加载配置
    - 自动生成DATABASE_URL
    - 提供配置验证

使用方法：
    from agent_backend.core.config_helper import get_database_url
    
    db_url = get_database_url()
"""
from __future__ import annotations

import os
import urllib.parse
from pathlib import Path


def load_env_file(env_file: Path | None = None) -> None:
    """
    加载.env文件到环境变量
    
    参数：
        env_file: .env文件路径，默认为项目根目录下的.env
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
    获取数据库连接URL
    
    优先级：
        1. 环境变量中的 DATABASE_URL
        2. 从分离的配置项自动生成（DB_HOST, DB_PORT, DB_USER等）
    
    返回：
        数据库连接URL，如果未配置则返回None
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
    获取Ollama配置
    
    返回：
        包含base_url, chat_model, vision_model的字典
    """
    load_env_file()
    
    return {
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "chat_model": os.getenv("CHAT_MODEL", "qwen2.5:7b"),
        "vision_model": os.getenv("VISION_MODEL", "qwen2.5-vl:7b"),
    }


def print_config_status():
    """打印配置状态"""
    load_env_file()
    
    print("\n" + "="*60)
    print("  配置状态检查")
    print("="*60)
    
    print("\n【大模型配置】")
    ollama_config = get_ollama_config()
    print(f"  Ollama地址: {ollama_config['base_url']}")
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
    rag_docs_dir = os.getenv("RAG_DOCS_DIR", "./data/docs")
    qdrant_url = os.getenv("RAG_QDRANT_URL", "http://localhost:6333")
    print(f"  文档目录: {rag_docs_dir}")
    print(f"  Qdrant地址: {qdrant_url}")
    
    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    print_config_status()


# 模块导入时自动加载.env文件
load_env_file()
