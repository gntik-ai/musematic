from __future__ import annotations

from platform.a2a_gateway.events import (
    A2AEventPayload,
    A2AEventPublisher,
    A2AEventType,
    register_a2a_event_types,
)
from platform.common.events.envelope import CorrelationContext
from platform.common.events.registry import event_registry
from uuid import uuid4

import pytest


class ProducerStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def publish(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_register_a2a_event_types_and_publish() -> None:
    register_a2a_event_types()
    for event_type in A2AEventType:
        assert event_registry.is_registered(event_type.value)

    producer = ProducerStub()
    publisher = A2AEventPublisher(producer)
    correlation = CorrelationContext(workspace_id=uuid4(), correlation_id=uuid4())
    payload = A2AEventPayload(agent_fqn="finance:verifier", state="submitted")

    await publisher.publish(
        event_type=A2AEventType.task_submitted,
        key="task-1",
        payload=payload,
        correlation_ctx=correlation,
    )

    assert producer.calls == [
        {
            "topic": "a2a.events",
            "key": "task-1",
            "event_type": "a2a.task.submitted",
            "payload": payload.model_dump(mode="json"),
            "correlation_ctx": correlation,
            "source": "platform.a2a_gateway",
        }
    ]


@pytest.mark.asyncio
async def test_publish_is_noop_without_producer() -> None:
    publisher = A2AEventPublisher(None)
    await publisher.publish(
        event_type=A2AEventType.task_failed,
        key="task-2",
        payload=A2AEventPayload(agent_fqn="finance:verifier"),
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
    )
