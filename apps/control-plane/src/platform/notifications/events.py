from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class NotificationsEventType(StrEnum):
    alert_created = "notifications.alert_created"
    alert_read = "notifications.alert_read"


class AlertCreatedPayload(BaseModel):
    id: UUID
    user_id: UUID
    alert_type: str
    title: str
    body: str | None
    urgency: str
    read: bool
    interaction_id: UUID | None
    source_reference: dict[str, object] | None
    created_at: datetime
    updated_at: datetime


class AlertReadPayload(BaseModel):
    alert_id: UUID
    user_id: UUID
    unread_count: int


NOTIFICATIONS_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    NotificationsEventType.alert_created.value: AlertCreatedPayload,
    NotificationsEventType.alert_read.value: AlertReadPayload,
}


def register_notifications_event_types() -> None:
    for event_type, schema in NOTIFICATIONS_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def _publish(
    *,
    producer: EventProducer | None,
    event_type: NotificationsEventType,
    key: str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
) -> None:
    if producer is None:
        return
    await producer.publish(
        topic="notifications.alerts",
        key=key,
        event_type=event_type.value,
        payload=payload.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.notifications",
    )


async def publish_alert_created(
    producer: EventProducer | None,
    payload: AlertCreatedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        event_type=NotificationsEventType.alert_created,
        key=str(payload.user_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_alert_read(
    producer: EventProducer | None,
    payload: AlertReadPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        event_type=NotificationsEventType.alert_read,
        key=str(payload.user_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )
