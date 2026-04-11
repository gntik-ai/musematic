from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from platform.memory.models import MemoryScope
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class MemoryEventType(StrEnum):
    memory_written = "memory.written"
    conflict_detected = "memory.conflict.detected"
    pattern_promoted = "memory.pattern.promoted"
    consolidation_completed = "memory.consolidation.completed"


class MemoryWrittenPayload(BaseModel):
    memory_entry_id: UUID
    workspace_id: UUID
    agent_fqn: str
    scope: MemoryScope
    namespace: str
    contradiction_detected: bool
    conflict_id: UUID | None = None


class ConflictDetectedPayload(BaseModel):
    conflict_id: UUID
    workspace_id: UUID
    memory_entry_id_a: UUID
    memory_entry_id_b: UUID
    similarity_score: float


class PatternPromotedPayload(BaseModel):
    pattern_asset_id: UUID
    workspace_id: UUID
    trajectory_record_id: UUID | None = None
    memory_entry_id: UUID
    approved_by: str


class ConsolidationCompletedPayload(BaseModel):
    workspace_id: UUID
    entries_consolidated: int
    entries_promoted: int
    duration_seconds: float
    run_at: datetime


MEMORY_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    MemoryEventType.memory_written.value: MemoryWrittenPayload,
    MemoryEventType.conflict_detected.value: ConflictDetectedPayload,
    MemoryEventType.pattern_promoted.value: PatternPromotedPayload,
    MemoryEventType.consolidation_completed.value: ConsolidationCompletedPayload,
}


def register_memory_event_types() -> None:
    for event_type, schema in MEMORY_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_memory_event(
    producer: EventProducer | None,
    event_type: MemoryEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
) -> None:
    if producer is None:
        return
    event_name = event_type.value if isinstance(event_type, MemoryEventType) else event_type
    payload_dict = payload.model_dump(mode="json")
    key = (
        payload_dict.get("memory_entry_id")
        or payload_dict.get("conflict_id")
        or payload_dict.get("pattern_asset_id")
        or payload_dict.get("workspace_id")
        or str(correlation_ctx.correlation_id)
    )
    await producer.publish(
        topic="memory.events",
        key=str(key),
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source="platform.memory",
    )


async def publish_memory_written(
    producer: EventProducer | None,
    payload: MemoryWrittenPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_memory_event(
        producer,
        MemoryEventType.memory_written,
        payload,
        correlation_ctx,
    )


async def publish_conflict_detected(
    producer: EventProducer | None,
    payload: ConflictDetectedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_memory_event(
        producer,
        MemoryEventType.conflict_detected,
        payload,
        correlation_ctx,
    )


async def publish_pattern_promoted(
    producer: EventProducer | None,
    payload: PatternPromotedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_memory_event(
        producer,
        MemoryEventType.pattern_promoted,
        payload,
        correlation_ctx,
    )


async def publish_consolidation_completed(
    producer: EventProducer | None,
    payload: ConsolidationCompletedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_memory_event(
        producer,
        MemoryEventType.consolidation_completed,
        payload,
        correlation_ctx,
    )
