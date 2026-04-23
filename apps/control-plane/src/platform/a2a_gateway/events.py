from __future__ import annotations

from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class A2AEventType(StrEnum):
    task_submitted = "a2a.task.submitted"
    task_state_changed = "a2a.task.state_changed"
    task_completed = "a2a.task.completed"
    task_failed = "a2a.task.failed"
    task_cancelled = "a2a.task.cancelled"
    outbound_attempted = "a2a.outbound.attempted"
    outbound_denied = "a2a.outbound.denied"


class A2AEventPayload(BaseModel):
    task_id: str | None = None
    workspace_id: UUID | None = None
    principal_id: UUID | None = None
    agent_fqn: str
    state: str | None = None
    direction: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


def register_a2a_event_types() -> None:
    for event_type in A2AEventType:
        event_registry.register(event_type.value, A2AEventPayload)


class A2AEventPublisher:
    def __init__(self, producer: EventProducer | None) -> None:
        self.producer = producer

    async def publish(
        self,
        *,
        event_type: A2AEventType,
        key: str,
        payload: A2AEventPayload,
        correlation_ctx: CorrelationContext,
    ) -> None:
        if self.producer is None:
            return
        await self.producer.publish(
            topic="a2a.events",
            key=key,
            event_type=event_type.value,
            payload=payload.model_dump(mode="json"),
            correlation_ctx=correlation_ctx,
            source="platform.a2a_gateway",
        )
