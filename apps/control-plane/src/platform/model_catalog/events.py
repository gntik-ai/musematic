from __future__ import annotations

from datetime import datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class ModelCatalogUpdatedPayload(BaseModel):
    catalog_entry_id: UUID
    provider: str
    model_id: str
    status: str
    changed_by: UUID | None = None


class ModelCardPublishedPayload(BaseModel):
    catalog_entry_id: UUID
    card_id: UUID
    revision: int
    material: bool


class ModelFallbackTriggeredPayload(BaseModel):
    workspace_id: UUID
    primary_model_id: UUID
    fallback_model_id: UUID
    reason: str
    triggered_at: datetime


class ModelDeprecatedPayload(BaseModel):
    catalog_entry_id: UUID
    provider: str
    model_id: str
    approval_expires_at: datetime


MODEL_CATALOG_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    "model.catalog.updated": ModelCatalogUpdatedPayload,
    "model.card.published": ModelCardPublishedPayload,
    "model.fallback.triggered": ModelFallbackTriggeredPayload,
    "model.deprecated": ModelDeprecatedPayload,
}


def register_model_catalog_event_types() -> None:
    for event_type, schema in MODEL_CATALOG_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_model_catalog_event(
    event_type: str,
    payload: BaseModel,
    correlation_id: UUID,
    producer: EventProducer | None,
    *,
    workspace_id: UUID | None = None,
    source: str = "platform.model_catalog",
) -> None:
    if producer is None:
        return
    payload_data = payload.model_dump(mode="json")
    subject_id = (
        payload_data.get("catalog_entry_id")
        or payload_data.get("fallback_model_id")
        or correlation_id
    )
    await producer.publish(
        topic="model.catalog.events",
        key=str(subject_id),
        event_type=event_type,
        payload=payload_data,
        correlation_ctx=CorrelationContext(
            correlation_id=correlation_id,
            workspace_id=workspace_id,
        ),
        source=source,
    )


async def publish_model_catalog_updated(
    payload: ModelCatalogUpdatedPayload,
    correlation_id: UUID,
    producer: EventProducer | None,
    *,
    workspace_id: UUID | None = None,
) -> None:
    await publish_model_catalog_event(
        "model.catalog.updated",
        payload,
        correlation_id,
        producer,
        workspace_id=workspace_id,
    )


async def publish_model_card_published(
    payload: ModelCardPublishedPayload,
    correlation_id: UUID,
    producer: EventProducer | None,
    *,
    workspace_id: UUID | None = None,
) -> None:
    await publish_model_catalog_event(
        "model.card.published",
        payload,
        correlation_id,
        producer,
        workspace_id=workspace_id,
    )


async def publish_model_fallback_triggered(
    payload: ModelFallbackTriggeredPayload,
    correlation_id: UUID,
    producer: EventProducer | None,
    *,
    workspace_id: UUID | None = None,
) -> None:
    await publish_model_catalog_event(
        "model.fallback.triggered",
        payload,
        correlation_id,
        producer,
        workspace_id=workspace_id,
    )


async def publish_model_deprecated(
    payload: ModelDeprecatedPayload,
    correlation_id: UUID,
    producer: EventProducer | None,
    *,
    workspace_id: UUID | None = None,
) -> None:
    await publish_model_catalog_event(
        "model.deprecated",
        payload,
        correlation_id,
        producer,
        workspace_id=workspace_id,
    )
