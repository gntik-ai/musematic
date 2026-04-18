from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID, uuid4

from pydantic import BaseModel


class MarketplaceEventType(StrEnum):
    rating_created = "marketplace.rating.created"
    rating_updated = "marketplace.rating.updated"
    trending_updated = "marketplace.trending.updated"


class RatingEventPayload(BaseModel):
    agent_id: UUID
    user_id: UUID
    score: int
    workspace_id: UUID | None = None
    occurred_at: datetime


class TrendingUpdatedPayload(BaseModel):
    snapshot_date: date
    top_agent_fqns: list[str]
    occurred_at: datetime


MARKETPLACE_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    MarketplaceEventType.rating_created.value: RatingEventPayload,
    MarketplaceEventType.rating_updated.value: RatingEventPayload,
    MarketplaceEventType.trending_updated.value: TrendingUpdatedPayload,
}


def register_marketplace_event_types() -> None:
    for event_type, schema in MARKETPLACE_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def emit_rating_created(
    producer: EventProducer | None,
    *,
    agent_id: UUID,
    user_id: UUID,
    score: int,
    workspace_id: UUID | None = None,
    correlation_ctx: CorrelationContext | None = None,
) -> None:
    await _publish(
        producer,
        MarketplaceEventType.rating_created,
        RatingEventPayload(
            agent_id=agent_id,
            user_id=user_id,
            score=score,
            workspace_id=workspace_id,
            occurred_at=datetime.now(UTC),
        ),
        correlation_ctx=correlation_ctx,
        key=str(agent_id),
    )


async def emit_rating_updated(
    producer: EventProducer | None,
    *,
    agent_id: UUID,
    user_id: UUID,
    score: int,
    workspace_id: UUID | None = None,
    correlation_ctx: CorrelationContext | None = None,
) -> None:
    await _publish(
        producer,
        MarketplaceEventType.rating_updated,
        RatingEventPayload(
            agent_id=agent_id,
            user_id=user_id,
            score=score,
            workspace_id=workspace_id,
            occurred_at=datetime.now(UTC),
        ),
        correlation_ctx=correlation_ctx,
        key=str(agent_id),
    )


async def emit_trending_updated(
    producer: EventProducer | None,
    *,
    snapshot_date: date,
    top_agent_fqns: list[str],
    correlation_ctx: CorrelationContext | None = None,
) -> None:
    await _publish(
        producer,
        MarketplaceEventType.trending_updated,
        TrendingUpdatedPayload(
            snapshot_date=snapshot_date,
            top_agent_fqns=top_agent_fqns,
            occurred_at=datetime.now(UTC),
        ),
        correlation_ctx=correlation_ctx,
        key=top_agent_fqns[0] if top_agent_fqns else str(snapshot_date),
    )


async def _publish(
    producer: EventProducer | None,
    event_type: MarketplaceEventType,
    payload: BaseModel,
    *,
    correlation_ctx: CorrelationContext | None,
    key: str,
) -> None:
    if producer is None:
        return
    await producer.publish(
        topic="marketplace.events",
        key=key,
        event_type=event_type.value,
        payload=payload.model_dump(mode="json"),
        correlation_ctx=correlation_ctx or CorrelationContext(correlation_id=uuid4()),
        source="platform.marketplace",
    )
