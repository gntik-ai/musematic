from __future__ import annotations

from datetime import timedelta
from platform.multi_region_ops.schemas import ReplicationComponent, ReplicationHealth
from platform.multi_region_ops.services.probes.base import ReplicationMeasurement

import pytest

from tests.integration.multi_region_ops.support import build_monitor, now, seeded_repository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_paused_replication_is_visible_and_does_not_fire_incident() -> None:
    repository = seeded_repository()
    source, target = await repository.list_regions(enabled_only=True)
    monitor, trigger = build_monitor(repository)

    await monitor._record_measurement(
        source,
        target,
        ReplicationMeasurement(
            component=ReplicationComponent.postgres,
            lag_seconds=None,
            health=ReplicationHealth.paused,
            pause_reason="planned maintenance",
            measured_at=now(),
        ),
    )

    row = repository.replication_rows[-1]
    assert row.health == "paused"
    assert row.pause_reason == "planned maintenance"
    assert trigger.signals == []


async def test_unintended_outage_fires_after_sustained_unhealthy_lag() -> None:
    repository = seeded_repository()
    source, target = await repository.list_regions(enabled_only=True)
    monitor, trigger = build_monitor(repository)
    measured_at = now()

    for offset in range(3):
        await monitor._record_measurement(
            source,
            target,
            ReplicationMeasurement(
                component="postgres",
                lag_seconds=180,
                health="unhealthy",
                error_detail="secondary disconnected",
                measured_at=measured_at + timedelta(seconds=offset),
            ),
        )

    assert len(trigger.signals) == 1
    assert trigger.signals[0].alert_rule_class == "replication_lag_breach"
