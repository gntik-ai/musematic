from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class ConnectorsEventType(StrEnum):
    ingress_received = "connector.ingress.received"
    delivery_requested = "connector.delivery.requested"
    delivery_succeeded = "connector.delivery.succeeded"
    delivery_failed = "connector.delivery.failed"
    dead_lettered = "connector.delivery.dead_lettered"


class ConnectorIngressPayload(BaseModel):
    connector_instance_id: UUID
    workspace_id: UUID
    connector_type_slug: str
    route_id: UUID | None
    target_agent_fqn: str | None
    target_workflow_id: UUID | None
    sender_identity: str
    channel: str
    content_text: str | None
    content_structured: dict[str, object] | None
    timestamp: datetime
    message_id: str | None
    original_payload: dict[str, object]


class ConnectorDeliveryRequestPayload(BaseModel):
    delivery_id: UUID
    connector_instance_id: UUID
    workspace_id: UUID


class ConnectorDeliverySucceededPayload(BaseModel):
    delivery_id: UUID
    connector_instance_id: UUID
    workspace_id: UUID
    delivered_at: datetime


class ConnectorDeliveryFailedPayload(BaseModel):
    delivery_id: UUID
    connector_instance_id: UUID
    workspace_id: UUID
    attempt_count: int
    retry_at: datetime | None
    error: str


class ConnectorDeadLetteredPayload(BaseModel):
    delivery_id: UUID
    dead_letter_entry_id: UUID
    connector_instance_id: UUID
    workspace_id: UUID
    attempt_count: int
    error: str


CONNECTOR_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    ConnectorsEventType.ingress_received.value: ConnectorIngressPayload,
    ConnectorsEventType.delivery_requested.value: ConnectorDeliveryRequestPayload,
    ConnectorsEventType.delivery_succeeded.value: ConnectorDeliverySucceededPayload,
    ConnectorsEventType.delivery_failed.value: ConnectorDeliveryFailedPayload,
    ConnectorsEventType.dead_lettered.value: ConnectorDeadLetteredPayload,
}


def register_connectors_event_types() -> None:
    for event_type, schema in CONNECTOR_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def _publish(
    *,
    producer: EventProducer | None,
    topic: str,
    event_type: ConnectorsEventType | str,
    key: str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
) -> None:
    if producer is None:
        return
    event_name = event_type.value if isinstance(event_type, ConnectorsEventType) else event_type
    await producer.publish(
        topic=topic,
        key=key,
        event_type=event_name,
        payload=payload.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.connectors",
    )


async def publish_connector_ingress(
    producer: EventProducer | None,
    payload: ConnectorIngressPayload,
    correlation_ctx: CorrelationContext,
    *,
    topic: str = "connector.ingress",
) -> None:
    await _publish(
        producer=producer,
        topic=topic,
        event_type=ConnectorsEventType.ingress_received,
        key=str(payload.connector_instance_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_delivery_requested(
    producer: EventProducer | None,
    payload: ConnectorDeliveryRequestPayload,
    correlation_ctx: CorrelationContext,
    *,
    topic: str = "connector.delivery",
) -> None:
    await _publish(
        producer=producer,
        topic=topic,
        event_type=ConnectorsEventType.delivery_requested,
        key=str(payload.delivery_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_delivery_succeeded(
    producer: EventProducer | None,
    payload: ConnectorDeliverySucceededPayload,
    correlation_ctx: CorrelationContext,
    *,
    topic: str = "connector.delivery",
) -> None:
    await _publish(
        producer=producer,
        topic=topic,
        event_type=ConnectorsEventType.delivery_succeeded,
        key=str(payload.delivery_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_delivery_failed(
    producer: EventProducer | None,
    payload: ConnectorDeliveryFailedPayload,
    correlation_ctx: CorrelationContext,
    *,
    topic: str = "connector.delivery",
) -> None:
    await _publish(
        producer=producer,
        topic=topic,
        event_type=ConnectorsEventType.delivery_failed,
        key=str(payload.delivery_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_dead_lettered(
    producer: EventProducer | None,
    payload: ConnectorDeadLetteredPayload,
    correlation_ctx: CorrelationContext,
    *,
    topic: str = "connector.delivery",
) -> None:
    await _publish(
        producer=producer,
        topic=topic,
        event_type=ConnectorsEventType.dead_lettered,
        key=str(payload.delivery_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )
