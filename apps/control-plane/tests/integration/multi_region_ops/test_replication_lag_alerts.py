from __future__ import annotations

from datetime import timedelta
from platform.multi_region_ops.services.probes.base import ReplicationMeasurement
from platform.multi_region_ops.services.replication_monitor import replication_fingerprint

import pytest

from tests.integration.multi_region_ops.support import (
    RecordingIncidentService,
    build_monitor,
    now,
    seeded_repository,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_replication_lag_breach_fires_once_then_resolves() -> None:
    repository = seeded_repository()
    source, target = await repository.list_regions(enabled_only=True)
    monitor, trigger = build_monitor(repository)
    measured_at = now()

    await monitor._record_measurement(
        source,
        target,
        ReplicationMeasurement(
            component="postgres",
            lag_seconds=20,
            health="healthy",
            measured_at=measured_at,
        ),
    )
    assert trigger.signals == []

    for offset in range(1, 4):
        await monitor._record_measurement(
            source,
            target,
            ReplicationMeasurement(
                component="postgres",
                lag_seconds=120,
                health="degraded",
                measured_at=measured_at + timedelta(seconds=offset),
            ),
        )

    assert len(trigger.signals) == 1
    signal = trigger.signals[0]
    assert signal.condition_fingerprint == replication_fingerprint(
        "postgres", "eu-west", "us-east"
    )
    assert signal.severity.value == "high"
    assert "postgres replication lag" in signal.title

    incident_service = RecordingIncidentService()
    resolving, _ = build_monitor(repository, incident_service=incident_service)
    for offset in range(4, 7):
        await resolving._record_measurement(
            source,
            target,
            ReplicationMeasurement(
                component="postgres",
                lag_seconds=0,
                health="healthy",
                measured_at=measured_at + timedelta(seconds=offset),
            ),
        )

    assert incident_service.resolved == [incident_service.incident_id]
