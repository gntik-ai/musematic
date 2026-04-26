from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from platform.multi_region_ops.constants import (
    KAFKA_TOPIC,
    MAINTENANCE_MODE_DISABLED_EVENT,
    MAINTENANCE_MODE_ENABLED_EVENT,
    REGION_FAILOVER_COMPLETED_EVENT,
    REGION_FAILOVER_INITIATED_EVENT,
    REGION_REPLICATION_LAG_EVENT,
)
from typing import Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel


class MultiRegionOpsEventType(StrEnum):
    region_replication_lag = REGION_REPLICATION_LAG_EVENT
    region_failover_initiated = REGION_FAILOVER_INITIATED_EVENT
    region_failover_completed = REGION_FAILOVER_COMPLETED_EVENT
    maintenance_mode_enabled = MAINTENANCE_MODE_ENABLED_EVENT
    maintenance_mode_disabled = MAINTENANCE_MODE_DISABLED_EVENT


class RegionReplicationLagPayload(BaseModel):
    region_id: UUID | None = None
    component: str
    source_region: str
    target_region: str
    lag_seconds: int | None
    threshold_seconds: int
    health: str
    correlation_context: CorrelationContext


class RegionFailoverInitiatedPayload(BaseModel):
    plan_id: UUID
    run_id: UUID
    from_region: str
    to_region: str
    run_kind: str
    initiated_by: UUID | None


class RegionFailoverCompletedPayload(BaseModel):
    plan_id: UUID
    run_id: UUID
    outcome: str
    duration_ms: int
    step_outcomes_summary: dict[str, Any]


class MaintenanceModeEnabledPayload(BaseModel):
    window_id: UUID
    starts_at: datetime
    ends_at: datetime
    reason: str | None
    announcement_text: str | None


class MaintenanceModeDisabledPayload(BaseModel):
    window_id: UUID
    disabled_at: datetime
    disable_kind: Literal["scheduled", "manual", "failed"]


MULTI_REGION_OPS_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    MultiRegionOpsEventType.region_replication_lag.value: RegionReplicationLagPayload,
    MultiRegionOpsEventType.region_failover_initiated.value: RegionFailoverInitiatedPayload,
    MultiRegionOpsEventType.region_failover_completed.value: RegionFailoverCompletedPayload,
    MultiRegionOpsEventType.maintenance_mode_enabled.value: MaintenanceModeEnabledPayload,
    MultiRegionOpsEventType.maintenance_mode_disabled.value: MaintenanceModeDisabledPayload,
}


def register_multi_region_ops_event_types() -> None:
    for event_type, schema in MULTI_REGION_OPS_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_multi_region_ops_event(
    producer: EventProducer | None,
    event_type: MultiRegionOpsEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
    *,
    source: str = "platform.multi_region_ops",
) -> None:
    if producer is None:
        return
    event_name = event_type.value if isinstance(event_type, MultiRegionOpsEventType) else event_type
    payload_dict = payload.model_dump(mode="json")
    subject_id = (
        payload_dict.get("region_id")
        or payload_dict.get("plan_id")
        or payload_dict.get("window_id")
        or correlation_ctx.correlation_id
    )
    await producer.publish(
        topic=KAFKA_TOPIC,
        key=str(subject_id),
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source=source,
    )
