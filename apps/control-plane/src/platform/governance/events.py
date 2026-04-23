from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from uuid import UUID

from pydantic import BaseModel, Field


class GovernanceEventType(StrEnum):
    verdict_issued = "governance.verdict.issued"
    enforcement_executed = "governance.enforcement.executed"


class VerdictIssuedPayload(BaseModel):
    verdict_id: UUID
    judge_agent_fqn: str
    verdict_type: str
    policy_id: UUID | None = None
    fleet_id: UUID | None = None
    workspace_id: UUID | None = None
    source_event_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EnforcementExecutedPayload(BaseModel):
    action_id: UUID
    verdict_id: UUID
    enforcer_agent_fqn: str
    action_type: str
    target_agent_fqn: str | None = None
    workspace_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


GOVERNANCE_EVENT_SCHEMAS: dict[str, type[BaseModel]] = {
    GovernanceEventType.verdict_issued.value: VerdictIssuedPayload,
    GovernanceEventType.enforcement_executed.value: EnforcementExecutedPayload,
}


def register_governance_event_types() -> None:
    for event_type, schema in GOVERNANCE_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def _publish(
    producer: EventProducer | None,
    *,
    event_type: GovernanceEventType,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
) -> None:
    if producer is None:
        return
    payload_dict = payload.model_dump(mode="json")
    key = str(
        payload_dict.get("verdict_id")
        or payload_dict.get("action_id")
        or payload_dict.get("workspace_id")
        or correlation_ctx.correlation_id
    )
    await producer.publish(
        topic="governance.events",
        key=key,
        event_type=event_type.value,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source="platform.governance",
    )


async def publish_verdict_issued(
    producer: EventProducer | None,
    payload: VerdictIssuedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer,
        event_type=GovernanceEventType.verdict_issued,
        payload=payload,
        correlation_ctx=correlation_ctx,
    )


async def publish_enforcement_executed(
    producer: EventProducer | None,
    payload: EnforcementExecutedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer,
        event_type=GovernanceEventType.enforcement_executed,
        payload=payload,
        correlation_ctx=correlation_ctx,
    )
