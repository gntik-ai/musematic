from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from platform.incident_response.schemas import IncidentSeverity, IncidentSignal
from platform.incident_response.services.incident_service import IncidentService
from platform.incident_response.trigger_interface import IncidentTriggerInterface
from platform.multi_region_ops.constants import REPLICATION_COMPONENTS
from platform.multi_region_ops.events import (
    MultiRegionOpsEventType,
    RegionReplicationLagPayload,
    publish_multi_region_ops_event,
)
from platform.multi_region_ops.models import RegionConfig
from platform.multi_region_ops.repository import MultiRegionOpsRepository
from platform.multi_region_ops.services.probes.base import (
    ReplicationMeasurement,
    ReplicationProbeRegistry,
)
from uuid import uuid4

LOGGER = get_logger(__name__)


class ReplicationMonitor:
    def __init__(
        self,
        *,
        repository: MultiRegionOpsRepository,
        settings: PlatformSettings,
        probe_registry: ReplicationProbeRegistry,
        incident_trigger: IncidentTriggerInterface,
        producer: EventProducer | None = None,
        incident_service: IncidentService | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.probe_registry = probe_registry
        self.incident_trigger = incident_trigger
        self.producer = producer
        self.incident_service = incident_service

    async def probe_all(self) -> list[ReplicationMeasurement]:
        if not self.settings.feature_multi_region:
            return []
        regions = await self.repository.list_regions(enabled_only=True)
        primary = next((region for region in regions if region.region_role == "primary"), None)
        secondaries = [region for region in regions if region.region_role == "secondary"]
        if primary is None or not secondaries:
            return []
        measurements: list[ReplicationMeasurement] = []
        for target in secondaries:
            for component in REPLICATION_COMPONENTS:
                probe = self.probe_registry.get(component)
                if probe is None:
                    measurement = ReplicationMeasurement(
                        component=component,
                        lag_seconds=None,
                        health="unhealthy",
                        error_detail="replication probe not registered",
                    )
                else:
                    try:
                        measurement = await probe.measure(source=primary, target=target)
                    except Exception as exc:
                        LOGGER.warning(
                            "multi_region_replication_probe_failed",
                            extra={
                                "component": component,
                                "source_region": primary.region_code,
                                "target_region": target.region_code,
                            },
                            exc_info=True,
                        )
                        measurement = ReplicationMeasurement(
                            component=component,
                            lag_seconds=None,
                            health="unhealthy",
                            error_detail=str(exc),
                        )
                await self._record_measurement(primary, target, measurement)
                measurements.append(measurement)
        return measurements

    async def _record_measurement(
        self,
        source: RegionConfig,
        target: RegionConfig,
        measurement: ReplicationMeasurement,
    ) -> None:
        row = await self.repository.insert_replication_status(
            source_region=source.region_code,
            target_region=target.region_code,
            component=measurement.component,
            lag_seconds=measurement.lag_seconds,
            health=measurement.health,
            pause_reason=measurement.pause_reason,
            error_detail=measurement.error_detail,
            measured_at=measurement.measured_at,
        )
        threshold_seconds = target.rpo_target_minutes * 60
        correlation_ctx = CorrelationContext(correlation_id=uuid4())
        await publish_multi_region_ops_event(
            self.producer,
            MultiRegionOpsEventType.region_replication_lag,
            RegionReplicationLagPayload(
                region_id=target.id,
                component=measurement.component,
                source_region=source.region_code,
                target_region=target.region_code,
                lag_seconds=measurement.lag_seconds,
                threshold_seconds=threshold_seconds,
                health=measurement.health,
                correlation_context=correlation_ctx,
            ),
            correlation_ctx,
        )
        if measurement.health == "paused":
            return
        sustained_intervals = self.settings.multi_region_ops.rpo_alert_sustained_intervals
        if await self.repository.count_consecutive_over_threshold(
            source=source.region_code,
            target=target.region_code,
            component=measurement.component,
            threshold_seconds=threshold_seconds,
            n=sustained_intervals,
        ):
            await self.incident_trigger.fire(
                IncidentSignal(
                    condition_fingerprint=replication_fingerprint(
                        measurement.component,
                        source.region_code,
                        target.region_code,
                    ),
                    severity=IncidentSeverity.high,
                    alert_rule_class="replication_lag_breach",
                    title=(
                        f"{measurement.component} replication lag exceeds "
                        f"{target.rpo_target_minutes}min"
                    ),
                    description=(
                        f"{measurement.component} replication from {source.region_code} to "
                        f"{target.region_code} measured {measurement.lag_seconds}s against "
                        f"{threshold_seconds}s threshold at {row.measured_at.isoformat()}."
                    ),
                    runbook_scenario="region_failover",
                    correlation_context=correlation_ctx,
                )
            )
            return
        if self.incident_service is None:
            return
        if not await self.repository.count_consecutive_at_or_below_threshold(
            source=source.region_code,
            target=target.region_code,
            component=measurement.component,
            threshold_seconds=threshold_seconds,
            n=sustained_intervals,
        ):
            return
        existing = await self.incident_service.repository.find_open_incident_by_fingerprint(
            replication_fingerprint(measurement.component, source.region_code, target.region_code)
        )
        if existing is not None:
            await self.incident_service.resolve(
                existing.id, resolved_at=datetime.now(UTC), auto_resolved=True
            )


def replication_fingerprint(component: str, source_region: str, target_region: str) -> str:
    return hashlib.sha256(f"{component}:{source_region}:{target_region}".encode()).hexdigest()
