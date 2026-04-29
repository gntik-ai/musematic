from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel

ADMIN_EVENTS_TOPIC: Final[str] = "admin.events"


class AdminEventType(StrEnum):
    tenant_mode_changed = "admin.tenant_mode.changed"


class TenantModeChangedPayload(BaseModel):
    previous_mode: str
    new_mode: str
    actor_user_id: UUID
    changed_at: datetime


ADMIN_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    AdminEventType.tenant_mode_changed.value: TenantModeChangedPayload,
}


def register_admin_event_types() -> None:
    for event_type, schema in ADMIN_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_admin_event(
    producer: EventProducer | None,
    event_type: AdminEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
    *,
    source: str = "platform.admin",
) -> None:
    if producer is None:
        return
    event_name = event_type.value if isinstance(event_type, AdminEventType) else event_type
    payload_dict = payload.model_dump(mode="json")
    await producer.publish(
        topic=ADMIN_EVENTS_TOPIC,
        key=str(payload_dict.get("actor_user_id") or correlation_ctx.correlation_id),
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source=source,
    )
