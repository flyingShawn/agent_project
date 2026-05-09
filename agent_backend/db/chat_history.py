"""
PostgreSQL 异步数据库引擎与会话管理模块

文件功能：
    初始化 PostgreSQL 异步数据库引擎，提供 ORM 基类、数据库初始化函数
    和 FastAPI 依赖注入用的异步会话生成器。

在系统架构中的定位：
    位于数据访问层的基础设施层，是所有数据库操作的底层支撑。
    - 对上：被 db/models.py（Base 基类）、api/v1/（get_session 依赖）等模块依赖
    - 对下：封装 asyncpg 异步驱动和 SQLAlchemy AsyncEngine

主要使用场景：
    - 应用启动时调用 init_db() 创建表
    - API 路由通过 Depends(get_session) 获取异步会话

核心组件：
    - engine: SQLAlchemy AsyncEngine 实例（postgresql+asyncpg 驱动）
    - async_session: async_sessionmaker 工厂，用于创建 AsyncSession
    - Base: DeclarativeBase 基类，所有 ORM 模型的父类
    - init_db(): 异步初始化函数，创建表
    - get_session(): FastAPI 依赖注入用的异步会话生成器

专有技术说明：
    - asyncpg: PostgreSQL 高性能异步驱动
    - pool_size/max_overflow: 连接池配置，控制并发连接数
    - expire_on_commit=False: 提交后不刷新对象属性，避免懒加载异常

关联文件：
    - agent_backend/db/models.py: ORM 模型定义（继承 Base）
    - agent_backend/main.py: 应用启动时调用 init_db()
    - agent_backend/api/v1/: 通过 get_session 获取会话
"""
import logging

from agent_backend.core.config import load_env_file, get_settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

load_env_file()
_settings = get_settings()
CHAT_DB_URL = _settings.build_chat_db_url()

engine = create_async_engine(
    CHAT_DB_URL,
    echo=False,
    pool_size=_settings.misc.chat_db_pool_size,
    max_overflow=_settings.misc.chat_db_max_overflow,
    pool_pre_ping=True,
    pool_recycle=_settings.misc.chat_db_pool_recycle_seconds,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"\n[DB] PostgreSQL 数据库初始化完成: {CHAT_DB_URL.split('@')[-1] if '@' in CHAT_DB_URL else CHAT_DB_URL}")


async def close_db():
    await engine.dispose()
    logger.info("\n[DB] PostgreSQL 连接池已关闭")


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
