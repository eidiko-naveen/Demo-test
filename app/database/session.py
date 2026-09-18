from collections.abc import AsyncIterator
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import get_settings
from app.database.base import Base
import app.database.models.entities  # noqa: F401

logger = logging.getLogger("enterprise_rag")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None
_sqlite_fallback_active: bool = False
_sqlite_initialized: bool = False


async def _init_sqlite_engine() -> AsyncEngine:
    global _sqlite_fallback_active, _sqlite_initialized
    data_dir = Path(".data")
    data_dir.mkdir(parents=True, exist_ok=True)
    sqlite_url = "sqlite+aiosqlite:///.data/enterprise_rag.db"
    sqlite_engine = create_async_engine(sqlite_url, echo=False)
    if not _sqlite_initialized:
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _sqlite_initialized = True
    _sqlite_fallback_active = True
    return sqlite_engine


async def _ensure_engine_and_factory() -> async_sessionmaker:
    global _engine, _session_factory, _sqlite_fallback_active
    if _session_factory is not None:
        return _session_factory

    settings = get_settings()
    if settings.database_url and not _sqlite_fallback_active:
        try:
            connect_args = {"timeout": 2.0} if "postgresql" in settings.database_url else {}
            test_engine = create_async_engine(
                settings.database_url,
                pool_pre_ping=True,
                connect_args=connect_args,
            )
            async with test_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            _engine = test_engine
            _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
            logger.info("Connected to primary database at %s", settings.database_url)
        except Exception as exc:
            logger.warning(
                "Primary database at %s unreachable (%s); using SQLite fallback at .data/enterprise_rag.db",
                settings.database_url,
                exc,
            )
            _engine = await _init_sqlite_engine()
            _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    else:
        _engine = await _init_sqlite_engine()
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    return _session_factory


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        if settings.database_url and not _sqlite_fallback_active:
            connect_args = {"timeout": 2.0} if "postgresql" in settings.database_url else {}
            _engine = create_async_engine(
                settings.database_url,
                pool_pre_ping=True,
                connect_args=connect_args,
            )
        else:
            _engine = create_async_engine("sqlite+aiosqlite:///.data/enterprise_rag.db")
    return _engine


def get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a transaction-scoped async session for API dependencies."""
    factory = await _ensure_engine_and_factory()
    async with factory() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None

