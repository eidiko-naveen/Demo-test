"""
Async engine + session factory, plus one-time DB bootstrap:
enabling the pgvector extension and creating tables if they don't exist.
"""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings
from src.db.models import Base

logger = structlog.get_logger()

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,   # detects dropped connections before using them
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def init_db() -> None:
    """
    Run once at startup: enable pgvector extension, create tables if missing.
    Idempotent — safe to call every time the app boots (local dev, restarts,
    and the K8s startup probe later all rely on this being safe to re-run).
    """
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("db_initialized")


async def close_db() -> None:
    """Called on SIGTERM shutdown (see main.py lifespan) — satisfies graceful shutdown (C22)."""
    await engine.dispose()
    logger.info("db_connections_closed")


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Use as `async with get_db_session() as db:` inside memory strategies / routes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise