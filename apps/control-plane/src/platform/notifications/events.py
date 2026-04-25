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
    channel_config_changed = "notifications.channel.config.changed"
    webhook_registered = "notifications.webhook.registered"
    webhook_deactivated = "notifications.webhook.deactivated"
    webhook_secret_rotated = "notifications.webhook.rotated"
    delivery_attempted = "notifications.delivery.attempted"
    delivery_dead_lettered = "notifications.delivery.dead_lettered"
    dlq_depth_threshold_reached = "notifications.dlq.depth.threshold_reached"


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


class ChannelConfigChangedPayload(BaseModel):
    channel_config_id: UUID
    user_id: UUID
    channel_type: str
    action: str
    actor_id: UUID
    occurred_at: datetime


class WebhookRegisteredPayload(BaseModel):
    webhook_id: UUID
    workspace_id: UUID
    event_types: list[str]
    actor_id: UUID
    occurred_at: datetime


class WebhookDeactivatedPayload(BaseModel):
    webhook_id: UUID
    workspace_id: UUID
    actor_id: UUID
    occurred_at: datetime


class WebhookSecretRotatedPayload(BaseModel):
    webhook_id: UUID
    workspace_id: UUID
    actor_id: UUID
    occurred_at: datetime


class DeliveryAttemptedPayload(BaseModel):
    delivery_id: UUID | None = None
    alert_id: UUID | None = None
    webhook_id: UUID | None = None
    channel_type: str
    outcome: str
    attempts: int = 1
    workspace_id: UUID | None = None
    error_detail: str | None = None
    occurred_at: datetime


class DeliveryDeadLetteredPayload(BaseModel):
    delivery_id: UUID
    webhook_id: UUID
    workspace_id: UUID
    failure_reason: str
    attempts: int
    occurred_at: datetime


class DlqDepthThresholdReachedPayload(BaseModel):
    workspace_id: UUID
    depth: int
    threshold: int
    occurred_at: datetime


NOTIFICATIONS_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    NotificationsEventType.alert_created.value: AlertCreatedPayload,
    NotificationsEventType.alert_read.value: AlertReadPayload,
    NotificationsEventType.channel_config_changed.value: ChannelConfigChangedPayload,
    NotificationsEventType.webhook_registered.value: WebhookRegisteredPayload,
    NotificationsEventType.webhook_deactivated.value: WebhookDeactivatedPayload,
    NotificationsEventType.webhook_secret_rotated.value: WebhookSecretRotatedPayload,
    NotificationsEventType.delivery_attempted.value: DeliveryAttemptedPayload,
    NotificationsEventType.delivery_dead_lettered.value: DeliveryDeadLetteredPayload,
    NotificationsEventType.dlq_depth_threshold_reached.value: DlqDepthThresholdReachedPayload,
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
    topic: str = "notifications.alerts",
) -> None:
    if producer is None:
        return
    await producer.publish(
        topic=topic,
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


async def publish_channel_config_changed(
    producer: EventProducer | None,
    payload: ChannelConfigChangedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        event_type=NotificationsEventType.channel_config_changed,
        key=str(payload.user_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
        topic="monitor.alerts",
    )


async def publish_webhook_registered(
    producer: EventProducer | None,
    payload: WebhookRegisteredPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        event_type=NotificationsEventType.webhook_registered,
        key=str(payload.workspace_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
        topic="monitor.alerts",
    )


async def publish_webhook_deactivated(
    producer: EventProducer | None,
    payload: WebhookDeactivatedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        event_type=NotificationsEventType.webhook_deactivated,
        key=str(payload.workspace_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
        topic="monitor.alerts",
    )


async def publish_webhook_secret_rotated(
    producer: EventProducer | None,
    payload: WebhookSecretRotatedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        event_type=NotificationsEventType.webhook_secret_rotated,
        key=str(payload.workspace_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
        topic="monitor.alerts",
    )


async def publish_delivery_attempted(
    producer: EventProducer | None,
    payload: DeliveryAttemptedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    key = str(payload.workspace_id or payload.webhook_id or payload.alert_id)
    await _publish(
        producer=producer,
        event_type=NotificationsEventType.delivery_attempted,
        key=key,
        payload=payload,
        correlation_ctx=correlation_ctx,
        topic="monitor.alerts",
    )


async def publish_delivery_dead_lettered(
    producer: EventProducer | None,
    payload: DeliveryDeadLetteredPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        event_type=NotificationsEventType.delivery_dead_lettered,
        key=str(payload.workspace_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
        topic="monitor.alerts",
    )


async def publish_dlq_depth_threshold_reached(
    producer: EventProducer | None,
    payload: DlqDepthThresholdReachedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        event_type=NotificationsEventType.dlq_depth_threshold_reached,
        key=str(payload.workspace_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
        topic="monitor.alerts",
    )
