from __future__ import annotations

from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Any, Final
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict


class CompositionEventType(StrEnum):
    """Kafka event types emitted by the composition context."""

    blueprint_generated = "composition.blueprint.generated"
    blueprint_validated = "composition.blueprint.validated"
    blueprint_overridden = "composition.blueprint.overridden"
    blueprint_finalized = "composition.blueprint.finalized"
    generation_failed = "composition.generation.failed"


class CompositionLifecyclePayload(BaseModel):
    """Common payload schema for composition lifecycle events."""

    model_config = ConfigDict(extra="allow")

    composition_request_id: UUID
    workspace_id: UUID
    request_type: str | None = None
    actor_id: UUID | None = None


COMPOSITION_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    event_type.value: CompositionLifecyclePayload for event_type in CompositionEventType
}


AUDIT_TO_EVENT: Final[dict[str, str]] = {
    "blueprint_generated": CompositionEventType.blueprint_generated.value,
    "blueprint_validated": CompositionEventType.blueprint_validated.value,
    "blueprint_overridden": CompositionEventType.blueprint_overridden.value,
    "blueprint_finalized": CompositionEventType.blueprint_finalized.value,
    "generation_failed": CompositionEventType.generation_failed.value,
}


def register_composition_event_types() -> None:
    """Register composition event schemas with the platform event registry."""
    for event_type, schema in COMPOSITION_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


class CompositionEventPublisher:
    """Publish composition lifecycle events to Kafka."""

    def __init__(self, producer: EventProducer | None) -> None:
        self.producer = producer

    async def publish(
        self,
        event_type: str,
        request_id: UUID,
        workspace_id: UUID,
        payload: dict[str, Any],
        actor_id: UUID | None = None,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        """Publish a composition event if a producer is configured."""
        if self.producer is None:
            return
        enriched = {
            "composition_request_id": request_id,
            "workspace_id": workspace_id,
            "actor_id": actor_id,
            **payload,
        }
        await self.producer.publish(
            topic="composition.events",
            key=str(request_id),
            event_type=event_type,
            payload=enriched,
            correlation_ctx=correlation_ctx
            or CorrelationContext(workspace_id=workspace_id, correlation_id=uuid4()),
            source="platform.composition",
        )
