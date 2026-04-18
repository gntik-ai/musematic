from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.notifications.consumers.attention_consumer import AttentionConsumer
from platform.notifications.consumers.state_change_consumer import StateChangeConsumer
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class SessionStub:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class ManagerStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def subscribe(self, topic: str, group: str, handler) -> None:
        self.calls.append((topic, group, handler))


class ServiceStub:
    def __init__(self) -> None:
        self.attention_payloads: list[object] = []
        self.state_payloads: list[tuple[object, UUID]] = []

    async def process_attention_request(self, payload) -> None:
        self.attention_payloads.append(payload)

    async def process_state_change(self, payload, workspace_id: UUID) -> None:
        self.state_payloads.append((payload, workspace_id))


class RedisStub:
    async def check_rate_limit(self, resource: str, key: str, limit: int, window_ms: int):
        return SimpleNamespace(allowed=True)


@pytest.mark.asyncio
async def test_attention_consumer_registers_and_processes_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SessionStub()
    service = ServiceStub()

    @asynccontextmanager
    async def _session_scope():
        yield session

    monkeypatch.setattr(
        "platform.notifications.consumers.attention_consumer.database.AsyncSessionLocal",
        lambda: _session_scope(),
    )
    monkeypatch.setattr(
        "platform.notifications.consumers.attention_consumer.build_notifications_service",
        lambda **kwargs: service,
    )

    consumer = AttentionConsumer(
        settings=SimpleNamespace(KAFKA_CONSUMER_GROUP_ID="platform"),
        redis_client=RedisStub(),  # type: ignore[arg-type]
        producer=None,
    )
    manager = ManagerStub()
    consumer.register(manager)

    envelope = EventEnvelope(
        event_type="attention.requested",
        source="pytest",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={
            "request_id": str(uuid4()),
            "workspace_id": str(uuid4()),
            "source_agent_fqn": "ops:reviewer",
            "target_identity": "user@example.com",
            "urgency": "high",
            "related_interaction_id": None,
            "related_goal_id": None,
            "context_summary": "Need review",
        },
    )

    await consumer.handle_event(envelope)

    assert manager.calls[0][0] == "interaction.attention"
    assert manager.calls[0][1] == "platform.notifications-attention"
    assert len(service.attention_payloads) == 1
    assert service.attention_payloads[0].target_identity == "user@example.com"
    assert session.committed is True
    assert session.rolled_back is False


@pytest.mark.asyncio
async def test_state_change_consumer_skips_invalid_states_and_processes_valid_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SessionStub()
    service = ServiceStub()

    @asynccontextmanager
    async def _session_scope():
        yield session

    monkeypatch.setattr(
        "platform.notifications.consumers.state_change_consumer.database.AsyncSessionLocal",
        lambda: _session_scope(),
    )
    monkeypatch.setattr(
        "platform.notifications.consumers.state_change_consumer.build_notifications_service",
        lambda **kwargs: service,
    )
    monkeypatch.setattr(
        "platform.notifications.consumers.state_change_consumer.build_workspaces_service",
        lambda **kwargs: SimpleNamespace(list_member_ids=lambda workspace_id: []),
    )

    consumer = StateChangeConsumer(
        settings=SimpleNamespace(KAFKA_CONSUMER_GROUP_ID="platform"),
        redis_client=RedisStub(),  # type: ignore[arg-type]
        producer=None,
    )

    ignored = EventEnvelope(
        event_type="interaction.state_changed",
        source="pytest",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={
            "interaction_id": str(uuid4()),
            "workspace_id": str(uuid4()),
            "from_state": "unknown",
            "to_state": "failed",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    await consumer.handle_event(ignored)
    assert service.state_payloads == []

    valid_workspace_id = uuid4()
    processed = EventEnvelope(
        event_type="interaction.state_changed",
        source="pytest",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={
            "interaction_id": str(uuid4()),
            "workspace_id": str(valid_workspace_id),
            "from_state": "running",
            "to_state": "failed",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    await consumer.handle_event(processed)

    assert len(service.state_payloads) == 1
    assert service.state_payloads[0][1] == valid_workspace_id
    assert session.committed is True



@pytest.mark.asyncio
async def test_attention_consumer_ignores_other_events_and_rolls_back_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = SessionStub()

    class FailingService(ServiceStub):
        async def process_attention_request(self, payload) -> None:
            del payload
            raise RuntimeError("boom")

    service = FailingService()

    @asynccontextmanager
    async def _session_scope():
        yield session

    monkeypatch.setattr(
        "platform.notifications.consumers.attention_consumer.database.AsyncSessionLocal",
        lambda: _session_scope(),
    )
    monkeypatch.setattr(
        "platform.notifications.consumers.attention_consumer.build_notifications_service",
        lambda **kwargs: service,
    )

    consumer = AttentionConsumer(
        settings=SimpleNamespace(KAFKA_CONSUMER_GROUP_ID="platform"),
        redis_client=RedisStub(),  # type: ignore[arg-type]
        producer=None,
    )
    ignored = EventEnvelope(
        event_type="interaction.state_changed",
        source="pytest",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={},
    )
    await consumer.handle_event(ignored)
    assert service.attention_payloads == []

    failing = EventEnvelope(
        event_type="attention.requested",
        source="pytest",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={
            "request_id": str(uuid4()),
            "workspace_id": str(uuid4()),
            "source_agent_fqn": "ops:reviewer",
            "target_identity": "user@example.com",
            "urgency": "high",
            "related_interaction_id": None,
            "related_goal_id": None,
            "context_summary": None,
        },
    )
    with caplog.at_level("ERROR"):
        await consumer.handle_event(failing)

    assert session.committed is False
    assert session.rolled_back is True
    assert "Failed to process interaction attention event" in caplog.text


@pytest.mark.asyncio
async def test_state_change_consumer_registers_ignores_other_events_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = SessionStub()

    class FailingService(ServiceStub):
        async def process_state_change(self, payload, workspace_id: UUID) -> None:
            del payload, workspace_id
            raise RuntimeError("boom")

    service = FailingService()

    @asynccontextmanager
    async def _session_scope():
        yield session

    monkeypatch.setattr(
        "platform.notifications.consumers.state_change_consumer.database.AsyncSessionLocal",
        lambda: _session_scope(),
    )
    monkeypatch.setattr(
        "platform.notifications.consumers.state_change_consumer.build_notifications_service",
        lambda **kwargs: service,
    )
    monkeypatch.setattr(
        "platform.notifications.consumers.state_change_consumer.build_workspaces_service",
        lambda **kwargs: SimpleNamespace(list_member_ids=lambda workspace_id: []),
    )

    consumer = StateChangeConsumer(
        settings=SimpleNamespace(KAFKA_CONSUMER_GROUP_ID="platform"),
        redis_client=RedisStub(),  # type: ignore[arg-type]
        producer=None,
    )
    manager = ManagerStub()
    consumer.register(manager)
    assert manager.calls[0][0] == "interaction.events"
    assert manager.calls[0][1] == "platform.notifications-state-change"

    ignored = EventEnvelope(
        event_type="attention.requested",
        source="pytest",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={},
    )
    await consumer.handle_event(ignored)
    assert service.state_payloads == []

    failing = EventEnvelope(
        event_type="interaction.state_changed",
        source="pytest",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={
            "interaction_id": str(uuid4()),
            "workspace_id": str(uuid4()),
            "from_state": "running",
            "to_state": "failed",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    with caplog.at_level("ERROR"):
        await consumer.handle_event(failing)

    assert session.committed is False
    assert session.rolled_back is True
    assert "Failed to process interaction.state_changed event" in caplog.text
