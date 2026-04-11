from __future__ import annotations

from datetime import UTC, datetime
from platform.analytics.events import (
    ANALYTICS_EVENT_SCHEMAS,
    AnalyticsEventType,
    BudgetThresholdCrossedPayload,
    ForecastUpdatedPayload,
    RecommendationGeneratedPayload,
    publish_analytics_event,
    publish_budget_threshold_crossed,
    publish_forecast_updated,
    publish_recommendation_generated,
    register_analytics_event_types,
)
from platform.common.events.envelope import CorrelationContext
from platform.common.events.registry import event_registry
from uuid import uuid4

from tests.auth_support import RecordingProducer


async def test_publish_helpers_emit_analytics_events() -> None:
    register_analytics_event_types()
    producer = RecordingProducer()
    workspace_id = uuid4()
    correlation = CorrelationContext(correlation_id=uuid4(), workspace_id=workspace_id)
    now = datetime.now(UTC)

    await publish_recommendation_generated(
        producer,
        RecommendationGeneratedPayload(
            workspace_id=workspace_id,
            recommendation_count=3,
            generated_at=now,
        ),
        correlation,
    )
    await publish_forecast_updated(
        producer,
        ForecastUpdatedPayload(
            workspace_id=workspace_id,
            horizon_days=30,
            trend_direction="increasing",
            total_projected_expected=42.5,
            generated_at=now,
        ),
        correlation,
    )
    await publish_budget_threshold_crossed(
        producer,
        BudgetThresholdCrossedPayload(
            workspace_id=workspace_id,
            threshold_usd=25.0,
            total_cost_usd=28.0,
            period_start=now,
            period_end=now,
            execution_count=9,
        ),
        correlation,
    )

    assert {event["event_type"] for event in producer.events} == {
        item.value for item in AnalyticsEventType
    }
    assert {event["topic"] for event in producer.events} == {"analytics.events"}
    for event_type in ANALYTICS_EVENT_SCHEMAS:
        assert event_registry.is_registered(event_type) is True


async def test_publish_analytics_event_is_noop_without_producer() -> None:
    await publish_analytics_event(
        None,
        AnalyticsEventType.recommendation_generated,
        RecommendationGeneratedPayload(
            workspace_id=uuid4(),
            recommendation_count=1,
            generated_at=datetime.now(UTC),
        ),
        CorrelationContext(correlation_id=uuid4()),
    )
