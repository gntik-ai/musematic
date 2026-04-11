from __future__ import annotations

from collections.abc import AsyncIterator
from platform.common.config import DatabaseSettings, PlatformSettings
from platform.common.config import settings as default_settings

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_database_engine(
    dsn: str,
    pool_size: int,
    max_overflow: int,
    *,
    echo: bool = False,
) -> AsyncEngine:
    return create_async_engine(
        dsn,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        echo=echo,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


engine: AsyncEngine
AsyncSessionLocal: async_sessionmaker[AsyncSession]


def configure_database(settings: PlatformSettings | DatabaseSettings) -> None:
    global engine, AsyncSessionLocal

    db_settings = settings if isinstance(settings, DatabaseSettings) else settings.db
    engine = create_database_engine(
        db_settings.dsn,
        db_settings.pool_size,
        db_settings.max_overflow,
    )
    AsyncSessionLocal = create_session_factory(engine)


async def database_health_check() -> bool:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True


async def get_async_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


configure_database(default_settings)
