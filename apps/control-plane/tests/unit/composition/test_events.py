from __future__ import annotations

from platform.common.events.envelope import CorrelationContext
from platform.common.events.registry import event_registry
from platform.composition.events import (
    CompositionEventPublisher,
    CompositionEventType,
    register_composition_event_types,
)
from uuid import uuid4

import pytest


class FakeProducer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def publish(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def test_register_composition_event_types() -> None:
    register_composition_event_types()

    assert event_registry.is_registered(CompositionEventType.blueprint_generated.value)
    assert event_registry.is_registered(CompositionEventType.generation_failed.value)


@pytest.mark.asyncio
async def test_publisher_noops_without_producer_and_publishes_with_producer() -> None:
    request_id = uuid4()
    workspace_id = uuid4()
    await CompositionEventPublisher(None).publish(
        CompositionEventType.blueprint_generated.value,
        request_id,
        workspace_id,
        {"request_type": "agent"},
    )
    producer = FakeProducer()
    ctx = CorrelationContext(workspace_id=workspace_id, correlation_id=uuid4())

    await CompositionEventPublisher(producer).publish(
        CompositionEventType.blueprint_generated.value,
        request_id,
        workspace_id,
        {"request_type": "agent"},
        actor_id=uuid4(),
        correlation_ctx=ctx,
    )

    assert producer.calls[0]["topic"] == "composition.events"
    assert producer.calls[0]["key"] == str(request_id)
    assert producer.calls[0]["correlation_ctx"] is ctx
