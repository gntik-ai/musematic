from __future__ import annotations

from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class TestingEventType(StrEnum):
    suite_generated = "evaluation.suite.generated"
    drift_detected = "evaluation.drift.detected"


class SuiteGeneratedPayload(BaseModel):
    suite_id: UUID
    workspace_id: UUID
    agent_fqn: str
    suite_type: str
    case_count: int


class TestingDriftDetectedPayload(BaseModel):
    alert_id: UUID
    workspace_id: UUID
    agent_fqn: str
    eval_set_id: UUID
    metric_name: str
    stddevs_from_baseline: float


TESTING_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    TestingEventType.suite_generated.value: SuiteGeneratedPayload,
    TestingEventType.drift_detected.value: TestingDriftDetectedPayload,
}


def register_testing_event_types() -> None:
    for event_type, schema in TESTING_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_testing_event(
    producer: EventProducer | None,
    event_type: TestingEventType,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
) -> None:
    if producer is None:
        return
    key = str(
        getattr(payload, "suite_id", None)
        or getattr(payload, "alert_id", None)
        or correlation_ctx.correlation_id
    )
    await producer.publish(
        topic="evaluation.events",
        key=key,
        event_type=event_type.value,
        payload=payload.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.testing",
    )
