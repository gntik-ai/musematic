from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from platform.localization.constants import KAFKA_TOPIC
from typing import Any, Final
from uuid import UUID

from pydantic import BaseModel


class LocalizationEventType(StrEnum):
    user_preferences_updated = "localization.user_preferences.updated"
    locale_file_published = "localization.locale_file.published"


class UserPreferencesUpdatedPayload(BaseModel):
    user_id: UUID
    changed_fields: dict[str, Any]
    updated_at: datetime


class LocaleFilePublishedPayload(BaseModel):
    locale_code: str
    version: int
    published_by: UUID | None
    vendor_source_ref: str | None
    namespace_count: int
    key_count: int
    published_at: datetime


LOCALIZATION_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    LocalizationEventType.user_preferences_updated.value: UserPreferencesUpdatedPayload,
    LocalizationEventType.locale_file_published.value: LocaleFilePublishedPayload,
}


def register_localization_event_types() -> None:
    for event_type, schema in LOCALIZATION_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_localization_event(
    producer: EventProducer | None,
    event_type: LocalizationEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
    *,
    source: str = "platform.localization",
) -> None:
    if producer is None:
        return
    event_name = event_type.value if isinstance(event_type, LocalizationEventType) else event_type
    payload_dict = payload.model_dump(mode="json")
    key = str(
        payload_dict.get("user_id")
        or payload_dict.get("locale_code")
        or correlation_ctx.correlation_id
    )
    await producer.publish(
        topic=KAFKA_TOPIC,
        key=key,
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source=source,
    )
