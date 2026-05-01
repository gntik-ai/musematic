from __future__ import annotations

from collections.abc import AsyncIterator
from platform.common.config import DatabaseSettings, PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.tenant_context import current_tenant
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import event, text
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


regular_engine: AsyncEngine
platform_staff_engine: AsyncEngine
RegularAsyncSessionLocal: async_sessionmaker[AsyncSession]
PlatformStaffAsyncSessionLocal: async_sessionmaker[AsyncSession]
engine: AsyncEngine
AsyncSessionLocal: async_sessionmaker[AsyncSession]


def configure_database(settings: PlatformSettings | DatabaseSettings) -> None:
    global AsyncSessionLocal
    global PlatformStaffAsyncSessionLocal
    global RegularAsyncSessionLocal
    global engine
    global platform_staff_engine
    global regular_engine

    db_settings = settings if isinstance(settings, DatabaseSettings) else settings.db
    regular_engine = create_database_engine(
        db_settings.dsn,
        db_settings.pool_size,
        db_settings.max_overflow,
    )
    platform_staff_dsn = getattr(db_settings, "platform_staff_dsn", "") or _platform_staff_dsn(
        db_settings.dsn
    )
    platform_staff_engine = create_database_engine(
        platform_staff_dsn,
        db_settings.pool_size,
        db_settings.max_overflow,
    )
    _install_tenant_binding_listener(regular_engine)
    RegularAsyncSessionLocal = create_session_factory(regular_engine)
    PlatformStaffAsyncSessionLocal = create_session_factory(platform_staff_engine)
    engine = regular_engine
    AsyncSessionLocal = RegularAsyncSessionLocal


async def database_health_check() -> bool:
    async with regular_engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True


async def get_session() -> AsyncIterator[AsyncSession]:
    async with RegularAsyncSessionLocal() as session:
        yield session


async def get_platform_staff_session() -> AsyncIterator[AsyncSession]:
    async with PlatformStaffAsyncSessionLocal() as session:
        yield session


async def get_async_session() -> AsyncIterator[AsyncSession]:
    async with RegularAsyncSessionLocal() as session:
        yield session


def _platform_staff_dsn(dsn: str) -> str:
    split = urlsplit(dsn)
    if not split.username:
        return dsn
    password = f":{split.password}" if split.password else ""
    host = split.hostname or ""
    port = f":{split.port}" if split.port else ""
    netloc = f"musematic_platform_staff{password}@{host}{port}"
    return urlunsplit((split.scheme, netloc, split.path, split.query, split.fragment))


def _install_tenant_binding_listener(target_engine: AsyncEngine) -> None:
    event.listen(
        target_engine.sync_engine,
        "before_cursor_execute",
        _bind_tenant_id,
    )


def _bind_tenant_id(
    conn: Any,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
) -> None:
    del conn, statement, parameters, context, executemany
    tenant = current_tenant.get(None)
    if tenant is None:
        return
    cursor.execute(f"SET LOCAL app.tenant_id = '{tenant.id}'")


configure_database(default_settings)
