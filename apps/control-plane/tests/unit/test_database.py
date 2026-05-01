from __future__ import annotations

import pytest

from platform.common import database
from platform.common import dependencies
from platform.common.config import PlatformSettings


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []

    async def execute(self, statement) -> None:
        self.executed.append(str(statement))


class FakeConnectionContext:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeEngine:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    def connect(self) -> FakeConnectionContext:
        return FakeConnectionContext(self.connection)


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()


def test_configure_database_replaces_module_state(monkeypatch) -> None:
    fake_engine = object()
    fake_factory = object()
    monkeypatch.setattr(database, "create_database_engine", lambda *args, **kwargs: fake_engine)
    monkeypatch.setattr(database, "create_session_factory", lambda engine, **kwargs: fake_factory)

    database.configure_database(PlatformSettings(POSTGRES_DSN="postgresql+asyncpg://configured/test"))

    assert database.engine is fake_engine
    assert database.AsyncSessionLocal is fake_factory


@pytest.mark.asyncio
async def test_database_health_check_uses_engine(monkeypatch) -> None:
    fake_engine = FakeEngine()
    monkeypatch.setattr(database, "engine", fake_engine)

    assert await database.database_health_check() is True
    assert fake_engine.connection.executed


@pytest.mark.asyncio
async def test_get_db_commits_and_closes_on_success(monkeypatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)

    generator = dependencies.get_db()
    yielded = await anext(generator)
    assert yielded is session

    with pytest.raises(StopAsyncIteration):
        await generator.asend(None)

    assert session.committed is True
    assert session.closed is True
    assert session.rolled_back is False


@pytest.mark.asyncio
async def test_get_db_rolls_back_on_exception(monkeypatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)

    generator = dependencies.get_db()
    await anext(generator)

    with pytest.raises(RuntimeError):
        await generator.athrow(RuntimeError("boom"))

    assert session.rolled_back is True
    assert session.closed is True


@pytest.mark.asyncio
async def test_get_async_session_yields_context_managed_session(monkeypatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)

    generator = database.get_async_session()
    yielded = await anext(generator)

    assert yielded is session
    with pytest.raises(StopAsyncIteration):
        await generator.asend(None)
    assert session.closed is True


@pytest.mark.asyncio
async def test_regular_and_platform_session_helpers_use_expected_factories(monkeypatch) -> None:
    regular = FakeSession()
    platform = FakeSession()
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: regular)
    monkeypatch.setattr(database, "PlatformStaffAsyncSessionLocal", lambda: platform)

    regular_generator = database.get_session()
    assert await anext(regular_generator) is regular
    with pytest.raises(StopAsyncIteration):
        await regular_generator.asend(None)

    platform_generator = database.get_platform_staff_session()
    assert await anext(platform_generator) is platform
    with pytest.raises(StopAsyncIteration):
        await platform_generator.asend(None)

    assert regular.closed is True
    assert platform.closed is True
