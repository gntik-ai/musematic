from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class ContextEngineeringEventType(StrEnum):
    assembly_completed = "context_engineering.assembly.completed"
    budget_exceeded_minimum = "context_engineering.budget.exceeded_minimum"
    drift_detected = "context_engineering.drift.detected"


class AssemblyCompletedPayload(BaseModel):
    assembly_id: UUID
    workspace_id: UUID
    execution_id: UUID
    step_id: UUID
    agent_fqn: str
    quality_score: float
    token_count: int
    ab_test_id: UUID | None = None
    ab_test_group: str | None = None
    flags: list[str]
    created_at: datetime


class BudgetExceededMinimumPayload(BaseModel):
    workspace_id: UUID
    execution_id: UUID
    step_id: UUID
    agent_fqn: str
    max_tokens: int
    minimum_tokens: int


class DriftDetectedPayload(BaseModel):
    alert_id: UUID
    workspace_id: UUID
    agent_fqn: str
    historical_mean: float
    historical_stddev: float
    recent_mean: float
    degradation_delta: float


CONTEXT_ENGINEERING_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    ContextEngineeringEventType.assembly_completed.value: AssemblyCompletedPayload,
    ContextEngineeringEventType.budget_exceeded_minimum.value: BudgetExceededMinimumPayload,
    ContextEngineeringEventType.drift_detected.value: DriftDetectedPayload,
}


def register_context_engineering_event_types() -> None:
    for event_type, schema in CONTEXT_ENGINEERING_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_context_engineering_event(
    producer: EventProducer | None,
    event_type: ContextEngineeringEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
) -> None:
    if producer is None:
        return
    event_name = (
        event_type.value if isinstance(event_type, ContextEngineeringEventType) else event_type
    )
    payload_dict = payload.model_dump(mode="json")
    event_key = (
        payload_dict.get("assembly_id")
        or payload_dict.get("alert_id")
        or payload_dict.get("workspace_id")
        or str(correlation_ctx.correlation_id)
    )
    await producer.publish(
        topic="context_engineering.events",
        key=str(event_key),
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source="platform.context_engineering",
    )


async def publish_assembly_completed(
    producer: EventProducer | None,
    payload: AssemblyCompletedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_context_engineering_event(
        producer,
        ContextEngineeringEventType.assembly_completed,
        payload,
        correlation_ctx,
    )


async def publish_budget_exceeded_minimum(
    producer: EventProducer | None,
    payload: BudgetExceededMinimumPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_context_engineering_event(
        producer,
        ContextEngineeringEventType.budget_exceeded_minimum,
        payload,
        correlation_ctx,
    )


async def publish_drift_detected(
    producer: EventProducer | None,
    payload: DriftDetectedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_context_engineering_event(
        producer,
        ContextEngineeringEventType.drift_detected,
        payload,
        correlation_ctx,
    )
