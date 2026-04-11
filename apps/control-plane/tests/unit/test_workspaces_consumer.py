from __future__ import annotations

from platform.accounts.events import AccountsEventType
from platform.accounts.models import SignupSource
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.workspaces.consumer import WorkspacesConsumer
from uuid import uuid4

import pytest

from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


class ConsumerServiceStub:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.calls: list[tuple[str, object, object]] = []
        self.should_fail = should_fail

    async def create_default_workspace(self, user_id, display_name, *, correlation_ctx=None):
        if self.should_fail:
            raise RuntimeError("boom")
        self.calls.append((str(user_id), display_name, correlation_ctx))
        return {"ok": True}


class SessionStub:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class SessionFactoryStub:
    def __init__(self, session: SessionStub) -> None:
        self.session = session

    def __call__(self) -> SessionStub:
        return self.session


class ManagerStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def subscribe(self, topic: str, group_id: str, handler) -> None:
        self.calls.append((topic, group_id, handler))


@pytest.mark.asyncio
async def test_workspaces_consumer_registers_subscription(monkeypatch) -> None:
    settings = __import__(
        "platform.common.config", fromlist=["PlatformSettings"]
    ).PlatformSettings()
    consumer = WorkspacesConsumer(
        settings=settings,
        redis_client=FakeAsyncRedisClient(),
        producer=RecordingProducer(),
    )
    manager = ManagerStub()
    consumer.register(manager)
    assert manager.calls[0][0] == "accounts.events"
    assert manager.calls[0][1].endswith(".workspaces")


@pytest.mark.asyncio
async def test_workspaces_consumer_handles_activation_event(monkeypatch) -> None:
    settings = __import__(
        "platform.common.config", fromlist=["PlatformSettings"]
    ).PlatformSettings()
    session = SessionStub()
    service = ConsumerServiceStub()
    monkeypatch.setattr(
        "platform.workspaces.consumer.database.AsyncSessionLocal",
        SessionFactoryStub(session),
    )
    monkeypatch.setattr(
        "platform.workspaces.consumer.build_workspaces_service",
        lambda **kwargs: service,
    )
    consumer = WorkspacesConsumer(
        settings=settings,
        redis_client=FakeAsyncRedisClient(),
        producer=RecordingProducer(),
    )
    envelope = EventEnvelope(
        event_type=AccountsEventType.user_activated.value,
        source="platform.accounts",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={
            "user_id": str(uuid4()),
            "email": "user@example.com",
            "display_name": "New User",
            "signup_source": SignupSource.self_registration.value,
        },
    )

    await consumer.handle_event(envelope)

    assert service.calls[0][1] == "New User"
    assert session.committed is True


@pytest.mark.asyncio
async def test_workspaces_consumer_ignores_unrelated_events() -> None:
    settings = __import__(
        "platform.common.config", fromlist=["PlatformSettings"]
    ).PlatformSettings()
    session = SessionStub()
    service = ConsumerServiceStub()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "platform.workspaces.consumer.database.AsyncSessionLocal",
        SessionFactoryStub(session),
    )
    monkeypatch.setattr(
        "platform.workspaces.consumer.build_workspaces_service",
        lambda **kwargs: service,
    )
    consumer = WorkspacesConsumer(
        settings=settings,
        redis_client=FakeAsyncRedisClient(),
        producer=RecordingProducer(),
    )
    envelope = EventEnvelope(
        event_type="accounts.user.deleted",
        source="platform.accounts",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={},
    )

    try:
        await consumer.handle_event(envelope)
    finally:
        monkeypatch.undo()

    assert service.calls == []
    assert session.committed is False
    assert session.rolled_back is False


@pytest.mark.asyncio
async def test_workspaces_consumer_rolls_back_on_workspace_provision_error(monkeypatch) -> None:
    settings = __import__(
        "platform.common.config", fromlist=["PlatformSettings"]
    ).PlatformSettings()
    session = SessionStub()
    service = ConsumerServiceStub(should_fail=True)
    logger_calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        "platform.workspaces.consumer.database.AsyncSessionLocal",
        SessionFactoryStub(session),
    )
    monkeypatch.setattr(
        "platform.workspaces.consumer.build_workspaces_service",
        lambda **kwargs: service,
    )
    monkeypatch.setattr(
        "platform.workspaces.consumer.LOGGER.exception",
        lambda message, *, extra: logger_calls.append((message, extra)),
    )
    consumer = WorkspacesConsumer(
        settings=settings,
        redis_client=FakeAsyncRedisClient(),
        producer=RecordingProducer(),
    )
    user_id = uuid4()
    envelope = EventEnvelope(
        event_type=AccountsEventType.user_activated.value,
        source="platform.accounts",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={
            "user_id": str(user_id),
            "email": "user@example.com",
            "display_name": "New User",
            "signup_source": SignupSource.self_registration.value,
        },
    )

    await consumer.handle_event(envelope)

    assert session.committed is False
    assert session.rolled_back is True
    assert logger_calls == [
        (
            "Failed to provision default workspace for activated user",
            {"user_id": str(user_id)},
        )
    ]
