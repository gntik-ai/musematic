from __future__ import annotations

from enum import StrEnum
from platform.agentops.models import GovernanceEvent
from platform.agentops.repository import AgentOpsRepository
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict


class AgentOpsEventType(StrEnum):
    health_warning = "agentops.health.warning"
    health_critical = "agentops.health.critical"
    regression_detected = "agentops.regression.detected"
    gate_checked = "agentops.gate.checked"
    canary_started = "agentops.canary.started"
    canary_promoted = "agentops.canary.promoted"
    canary_rolled_back = "agentops.canary.rolled_back"
    retirement_trigger = "agentops.retirement.trigger"
    retirement_initiated = "agentops.retirement.initiated"
    retirement_completed = "agentops.retirement.completed"
    recertification_triggered = "agentops.recertification.triggered"
    adaptation_proposed = "agentops.adaptation.proposed"
    adaptation_reviewed = "agentops.adaptation.reviewed"
    adaptation_completed = "agentops.adaptation.completed"


class AgentOpsLifecyclePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    agent_fqn: str
    workspace_id: UUID
    actor: str | None = None


AGENTOPS_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    event_type.value: AgentOpsLifecyclePayload for event_type in AgentOpsEventType
}


def register_agentops_event_types() -> None:
    for event_type, schema in AGENTOPS_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


class AgentOpsEventPublisher:
    def __init__(self, producer: EventProducer | None) -> None:
        self.producer = producer

    async def publish(
        self,
        event_type: str,
        agent_fqn: str,
        workspace_id: UUID,
        payload: dict[str, object],
        actor: UUID | str | None = None,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        if self.producer is None:
            return
        enriched_payload = {
            "agent_fqn": agent_fqn,
            "workspace_id": workspace_id,
            "actor": str(actor) if actor is not None else None,
            **payload,
        }
        await self.producer.publish(
            topic="agentops.events",
            key=agent_fqn,
            event_type=event_type,
            payload=enriched_payload,
            correlation_ctx=correlation_ctx
            or CorrelationContext(workspace_id=workspace_id, correlation_id=uuid4()),
            source="platform.agentops",
        )


class GovernanceEventPublisher:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        event_publisher: AgentOpsEventPublisher,
    ) -> None:
        self.repository = repository
        self.event_publisher = event_publisher

    async def record(
        self,
        event_type: str,
        agent_fqn: str,
        workspace_id: UUID,
        payload: dict[str, object],
        actor: UUID | str | None = None,
        revision_id: UUID | None = None,
        correlation_ctx: CorrelationContext | None = None,
    ) -> GovernanceEvent:
        event = await self.repository.insert_governance_event(
            GovernanceEvent(
                agent_fqn=agent_fqn,
                workspace_id=workspace_id,
                revision_id=revision_id,
                event_type=event_type,
                actor_id=_actor_uuid(actor),
                payload=payload,
            )
        )
        await self.event_publisher.publish(
            event_type,
            agent_fqn,
            workspace_id,
            payload,
            actor=actor,
            correlation_ctx=correlation_ctx,
        )
        return event


def _actor_uuid(value: UUID | str | None) -> UUID | None:
    if value in {None, ""}:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None
