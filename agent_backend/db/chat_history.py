"""
SQLite 异步数据库引擎与会话管理模块

文件功能：
    初始化 SQLite 异步数据库引擎，提供 ORM 基类、数据库初始化函数
    和 FastAPI 依赖注入用的异步会话生成器。启用 WAL 模式提升并发性能。

在系统架构中的定位：
    位于数据访问层的基础设施层，是所有数据库操作的底层支撑。
    - 对上：被 db/models.py（Base 基类）、api/v1/（get_session 依赖）、
      scheduler/manager.py（async_session 直接使用）等模块依赖
    - 对下：封装 aiosqlite 异步驱动和 SQLAlchemy AsyncEngine

主要使用场景：
    - 应用启动时调用 init_db() 创建表和启用 WAL 模式
    - API 路由通过 Depends(get_session) 获取异步会话
    - SchedulerManager 通过 async_session() 直接创建会话

核心组件：
    - engine: SQLAlchemy AsyncEngine 实例（sqlite+aiosqlite 驱动）
    - async_session: async_sessionmaker 工厂，用于创建 AsyncSession
    - Base: DeclarativeBase 基类，所有 ORM 模型的父类
    - init_db(): 异步初始化函数，创建表并启用 WAL 模式
    - get_session(): FastAPI 依赖注入用的异步会话生成器

专有技术说明：
    - WAL 模式：启用 Write-Ahead Logging，允许读写并发，避免读阻塞
    - check_same_thread=False：SQLite 多线程访问配置
    - expire_on_commit=False：提交后不刷新对象属性，避免懒加载异常

关联文件：
    - agent_backend/db/models.py: ORM 模型定义（继承 Base）
    - agent_backend/main.py: 应用启动时调用 init_db()
    - agent_backend/api/v1/: 通过 get_session 获取会话
    - agent_backend/scheduler/manager.py: 通过 async_session 操作任务表
"""
import os
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

logger = logging.getLogger(__name__)

SQLITE_DB_PATH = os.environ.get("CHAT_DB_PATH", "data/chat_history.db")

db_path = Path(SQLITE_DB_PATH).resolve()
db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    f"sqlite+aiosqlite:///{db_path.as_posix()}",
    echo=False,
    connect_args={"check_same_thread": False},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"\n[DB] SQLite 数据库初始化完成（WAL模式已启用）: {db_path}")


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
