from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from platform.incident_response.constants import (
    INCIDENT_RESOLVED_EVENT,
    INCIDENT_TRIGGERED_EVENT,
    KAFKA_TOPIC,
)
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class IncidentResponseEventType(StrEnum):
    incident_triggered = INCIDENT_TRIGGERED_EVENT
    incident_resolved = INCIDENT_RESOLVED_EVENT


class IncidentTriggeredPayload(BaseModel):
    incident_id: UUID
    condition_fingerprint: str
    severity: str
    alert_rule_class: str
    related_execution_ids: list[UUID]
    runbook_scenario: str | None
    triggered_at: datetime
    correlation_context: CorrelationContext


class IncidentResolvedPayload(BaseModel):
    incident_id: UUID
    condition_fingerprint: str
    severity: str
    status: str
    resolved_at: datetime
    correlation_context: CorrelationContext


INCIDENT_RESPONSE_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    IncidentResponseEventType.incident_triggered.value: IncidentTriggeredPayload,
    IncidentResponseEventType.incident_resolved.value: IncidentResolvedPayload,
}


def register_incident_response_event_types() -> None:
    for event_type, schema in INCIDENT_RESPONSE_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_incident_response_event(
    producer: EventProducer | None,
    event_type: IncidentResponseEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
    *,
    source: str = "platform.incident_response",
) -> None:
    if producer is None:
        return
    event_name = (
        event_type.value if isinstance(event_type, IncidentResponseEventType) else event_type
    )
    payload_dict = payload.model_dump(mode="json")
    subject_id = payload_dict.get("incident_id") or str(correlation_ctx.correlation_id)
    await producer.publish(
        topic=KAFKA_TOPIC,
        key=str(subject_id),
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source=source,
    )


async def publish_incident_triggered(
    producer: EventProducer | None,
    payload: IncidentTriggeredPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_incident_response_event(
        producer,
        IncidentResponseEventType.incident_triggered,
        payload,
        correlation_ctx,
    )


async def publish_incident_resolved(
    producer: EventProducer | None,
    payload: IncidentResolvedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_incident_response_event(
        producer,
        IncidentResponseEventType.incident_resolved,
        payload,
        correlation_ctx,
    )
