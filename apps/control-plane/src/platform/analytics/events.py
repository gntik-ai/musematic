from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class AnalyticsEventType(StrEnum):
    recommendation_generated = "analytics.recommendation.generated"
    forecast_updated = "analytics.forecast.updated"
    budget_threshold_crossed = "analytics.budget.threshold_crossed"


class RecommendationGeneratedPayload(BaseModel):
    workspace_id: UUID
    recommendation_count: int
    generated_at: datetime


class ForecastUpdatedPayload(BaseModel):
    workspace_id: UUID
    horizon_days: int
    trend_direction: str
    total_projected_expected: float
    generated_at: datetime


class BudgetThresholdCrossedPayload(BaseModel):
    workspace_id: UUID
    threshold_usd: float
    total_cost_usd: float
    period_start: datetime
    period_end: datetime
    execution_count: int


ANALYTICS_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    AnalyticsEventType.recommendation_generated.value: RecommendationGeneratedPayload,
    AnalyticsEventType.forecast_updated.value: ForecastUpdatedPayload,
    AnalyticsEventType.budget_threshold_crossed.value: BudgetThresholdCrossedPayload,
}


def register_analytics_event_types() -> None:
    for event_type, schema in ANALYTICS_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_analytics_event(
    producer: EventProducer | None,
    event_type: AnalyticsEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
    *,
    source: str = "platform.analytics",
) -> None:
    if producer is None:
        return
    event_name = event_type.value if isinstance(event_type, AnalyticsEventType) else event_type
    payload_dict = payload.model_dump(mode="json")
    subject_id = payload_dict.get("workspace_id") or str(correlation_ctx.correlation_id)
    await producer.publish(
        topic="analytics.events",
        key=str(subject_id),
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source=source,
    )


async def publish_recommendation_generated(
    producer: EventProducer | None,
    payload: RecommendationGeneratedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_analytics_event(
        producer,
        AnalyticsEventType.recommendation_generated,
        payload,
        correlation_ctx,
    )


async def publish_forecast_updated(
    producer: EventProducer | None,
    payload: ForecastUpdatedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_analytics_event(
        producer,
        AnalyticsEventType.forecast_updated,
        payload,
        correlation_ctx,
    )


async def publish_budget_threshold_crossed(
    producer: EventProducer | None,
    payload: BudgetThresholdCrossedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_analytics_event(
        producer,
        AnalyticsEventType.budget_threshold_crossed,
        payload,
        correlation_ctx,
    )
