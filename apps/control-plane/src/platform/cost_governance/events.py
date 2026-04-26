from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from platform.cost_governance.constants import KAFKA_TOPIC
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class CostGovernanceEventType(StrEnum):
    execution_attributed = "cost.execution.attributed"
    budget_threshold_reached = "cost.budget.threshold.reached"
    budget_exceeded = "cost.budget.exceeded"
    anomaly_detected = "cost.anomaly.detected"
    forecast_updated = "cost.forecast.updated"


class CostExecutionAttributedPayload(BaseModel):
    attribution_id: UUID
    execution_id: UUID
    workspace_id: UUID
    agent_id: UUID | None = None
    user_id: UUID | None = None
    total_cost_cents: Decimal
    currency: str
    attributed_at: datetime


class CostBudgetThresholdReachedPayload(BaseModel):
    budget_id: UUID
    workspace_id: UUID
    threshold_percentage: int
    period_start: datetime
    period_end: datetime
    spend_cents: Decimal
    budget_cents: int


class CostBudgetExceededPayload(BaseModel):
    budget_id: UUID
    workspace_id: UUID
    period_start: datetime
    period_end: datetime
    spend_cents: Decimal
    budget_cents: int
    override_endpoint: str


class CostAnomalyDetectedPayload(BaseModel):
    anomaly_id: UUID
    workspace_id: UUID
    anomaly_type: str
    severity: str
    baseline_cents: Decimal
    observed_cents: Decimal
    detected_at: datetime


class CostForecastUpdatedPayload(BaseModel):
    forecast_id: UUID
    workspace_id: UUID
    period_start: datetime
    period_end: datetime
    forecast_cents: Decimal | None
    computed_at: datetime


COST_GOVERNANCE_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    CostGovernanceEventType.execution_attributed.value: CostExecutionAttributedPayload,
    CostGovernanceEventType.budget_threshold_reached.value: CostBudgetThresholdReachedPayload,
    CostGovernanceEventType.budget_exceeded.value: CostBudgetExceededPayload,
    CostGovernanceEventType.anomaly_detected.value: CostAnomalyDetectedPayload,
    CostGovernanceEventType.forecast_updated.value: CostForecastUpdatedPayload,
}


def register_cost_governance_event_types() -> None:
    for event_type, schema in COST_GOVERNANCE_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_cost_governance_event(
    producer: EventProducer | None,
    event_type: CostGovernanceEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
    *,
    source: str = "platform.cost_governance",
) -> None:
    if producer is None:
        return
    event_name = event_type.value if isinstance(event_type, CostGovernanceEventType) else event_type
    payload_dict = payload.model_dump(mode="json")
    key = str(payload_dict.get("workspace_id") or correlation_ctx.correlation_id)
    await producer.publish(
        topic=KAFKA_TOPIC,
        key=key,
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source=source,
    )

