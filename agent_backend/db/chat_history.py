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
