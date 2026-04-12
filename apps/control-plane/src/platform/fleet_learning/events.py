from __future__ import annotations

from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.fleets.events import (
    FleetAdaptationAppliedPayload,
    FleetEventType,
    FleetTransferStatusChangedPayload,
    publish_fleet_event,
)


async def publish_adaptation_applied(
    producer: EventProducer | None,
    payload: FleetAdaptationAppliedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_fleet_event(
        producer,
        FleetEventType.fleet_adaptation_applied,
        payload,
        correlation_ctx,
    )


async def publish_transfer_status_changed(
    producer: EventProducer | None,
    payload: FleetTransferStatusChangedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_fleet_event(
        producer,
        FleetEventType.fleet_transfer_status_changed,
        payload,
        correlation_ctx,
    )
