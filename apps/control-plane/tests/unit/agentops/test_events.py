from __future__ import annotations

from platform.agentops.events import (
    AgentOpsEventPublisher,
    AgentOpsEventType,
    GovernanceEventPublisher,
    register_agentops_event_types,
)
from platform.agentops.models import GovernanceEvent
from platform.common.events.envelope import CorrelationContext
from platform.common.events.registry import event_registry
from uuid import uuid4

import pytest


class _ProducerStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def publish(self, **kwargs) -> None:
        self.calls.append(kwargs)


class _RepositoryStub:
    def __init__(self) -> None:
        self.events: list[GovernanceEvent] = []

    async def insert_governance_event(self, event: GovernanceEvent) -> GovernanceEvent:
        self.events.append(event)
        return event


@pytest.mark.asyncio
async def test_agentops_event_publisher_is_noop_without_producer() -> None:
    publisher = AgentOpsEventPublisher(None)

    await publisher.publish(
        AgentOpsEventType.health_warning.value,
        "finance:agent",
        uuid4(),
        {"score": 42.0},
    )


@pytest.mark.asyncio
async def test_agentops_event_publisher_enriches_payload_and_uses_topic() -> None:
    producer = _ProducerStub()
    workspace_id = uuid4()
    actor_id = uuid4()
    correlation = CorrelationContext(workspace_id=workspace_id, correlation_id=uuid4())
    publisher = AgentOpsEventPublisher(producer)  # type: ignore[arg-type]

    await publisher.publish(
        AgentOpsEventType.gate_checked.value,
        "finance:agent",
        workspace_id,
        {"revision_id": str(uuid4())},
        actor=actor_id,
        correlation_ctx=correlation,
    )

    assert producer.calls[0]["topic"] == "agentops.events"
    assert producer.calls[0]["event_type"] == "agentops.gate.checked"
    assert producer.calls[0]["payload"]["actor"] == str(actor_id)


@pytest.mark.asyncio
async def test_governance_event_publisher_records_and_emits_event() -> None:
    producer = _ProducerStub()
    repository = _RepositoryStub()
    workspace_id = uuid4()
    revision_id = uuid4()
    actor_id = uuid4()
    publisher = GovernanceEventPublisher(
        repository=repository,  # type: ignore[arg-type]
        event_publisher=AgentOpsEventPublisher(producer),  # type: ignore[arg-type]
    )

    event = await publisher.record(
        AgentOpsEventType.adaptation_completed.value,
        "finance:agent",
        workspace_id,
        payload={"passed": True},
        actor=actor_id,
        revision_id=revision_id,
    )

    assert repository.events[0] is event
    assert event.actor_id == actor_id
    assert producer.calls[0]["payload"]["passed"] is True


def test_register_agentops_event_types_registers_all_schemas() -> None:
    register_agentops_event_types()

    for event_type in AgentOpsEventType:
        assert event_registry.is_registered(event_type.value) is True
