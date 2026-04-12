from __future__ import annotations

from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class FleetEventType(StrEnum):
    fleet_created = "fleet.created"
    fleet_archived = "fleet.archived"
    fleet_status_changed = "fleet.status.changed"
    fleet_member_added = "fleet.member.added"
    fleet_member_removed = "fleet.member.removed"
    fleet_topology_changed = "fleet.topology.changed"
    fleet_orchestration_rules_updated = "fleet.orchestration_rules.updated"
    fleet_governance_chain_updated = "fleet.governance_chain.updated"
    fleet_adaptation_applied = "fleet.adaptation.applied"
    fleet_transfer_status_changed = "fleet.transfer.status_changed"
    fleet_health_updated = "fleet.health.updated"


class FleetCreatedPayload(BaseModel):
    fleet_id: UUID
    workspace_id: UUID
    name: str
    topology_type: str


class FleetArchivedPayload(BaseModel):
    fleet_id: UUID
    workspace_id: UUID


class FleetStatusChangedPayload(BaseModel):
    fleet_id: UUID
    workspace_id: UUID
    status: str
    previous_status: str | None
    reason: str | None = None


class FleetMemberPayload(BaseModel):
    fleet_id: UUID
    workspace_id: UUID
    agent_fqn: str
    role: str | None = None


class FleetTopologyChangedPayload(BaseModel):
    fleet_id: UUID
    workspace_id: UUID
    version: int
    topology_type: str


class FleetRulesUpdatedPayload(BaseModel):
    fleet_id: UUID
    workspace_id: UUID
    version: int


class FleetGovernanceChainUpdatedPayload(BaseModel):
    fleet_id: UUID
    workspace_id: UUID
    version: int
    is_default: bool


class FleetAdaptationAppliedPayload(BaseModel):
    fleet_id: UUID
    workspace_id: UUID
    rule_id: UUID
    before_version: int
    after_version: int


class FleetTransferStatusChangedPayload(BaseModel):
    transfer_id: UUID
    workspace_id: UUID
    source_fleet_id: UUID
    target_fleet_id: UUID
    status: str


class FleetHealthUpdatedPayload(BaseModel):
    fleet_id: UUID
    workspace_id: UUID
    health_pct: float
    quorum_met: bool
    status: str
    available_count: int
    total_count: int
    member_statuses: list[dict[str, object]]


FLEET_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    FleetEventType.fleet_created.value: FleetCreatedPayload,
    FleetEventType.fleet_archived.value: FleetArchivedPayload,
    FleetEventType.fleet_status_changed.value: FleetStatusChangedPayload,
    FleetEventType.fleet_member_added.value: FleetMemberPayload,
    FleetEventType.fleet_member_removed.value: FleetMemberPayload,
    FleetEventType.fleet_topology_changed.value: FleetTopologyChangedPayload,
    FleetEventType.fleet_orchestration_rules_updated.value: FleetRulesUpdatedPayload,
    FleetEventType.fleet_governance_chain_updated.value: FleetGovernanceChainUpdatedPayload,
    FleetEventType.fleet_adaptation_applied.value: FleetAdaptationAppliedPayload,
    FleetEventType.fleet_transfer_status_changed.value: FleetTransferStatusChangedPayload,
    FleetEventType.fleet_health_updated.value: FleetHealthUpdatedPayload,
}


def register_fleet_event_types() -> None:
    for event_type, schema in FLEET_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def _publish(
    *,
    producer: EventProducer | None,
    topic: str,
    key: str,
    event_type: FleetEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
) -> None:
    if producer is None:
        return
    event_name = event_type.value if isinstance(event_type, FleetEventType) else event_type
    await producer.publish(
        topic=topic,
        key=key,
        event_type=event_name,
        payload=payload.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.fleets",
    )


async def publish_fleet_event(
    producer: EventProducer | None,
    event_type: FleetEventType,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
) -> None:
    topic = "fleet.health" if event_type is FleetEventType.fleet_health_updated else "fleet.events"
    key = str(getattr(payload, "fleet_id", getattr(payload, "transfer_id", "")))
    await _publish(
        producer=producer,
        topic=topic,
        key=key,
        event_type=event_type,
        payload=payload,
        correlation_ctx=correlation_ctx,
    )
