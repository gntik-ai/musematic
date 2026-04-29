from __future__ import annotations

from datetime import timedelta
from platform.multi_region_ops.schemas import MaintenanceWindowCreateRequest

import pytest

from tests.integration.multi_region_ops.support import build_services, now, seeded_repository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_maintenance_window_lifecycle_updates_banner_and_disabled_event() -> None:
    services = build_services(seeded_repository())
    starts = now() + timedelta(minutes=30)
    window = await services["maintenance"].schedule(
        MaintenanceWindowCreateRequest(
            starts_at=starts,
            ends_at=starts + timedelta(minutes=60),
            reason="database failover rehearsal",
            announcement_text="Writes are paused for maintenance",
        )
    )
    active = await services["maintenance"].enable(window.id)
    banner = services["maintenance"].status_banner(active)
    completed = await services["maintenance"].disable(active.id, disable_kind="manual")

    assert banner is not None
    assert "Writes are paused" in banner["message"]
    assert completed.status == "completed"
    active_after_disable = await services["maintenance"].get_active_window()
    assert services["maintenance"].status_banner(active_after_disable) is None
    assert [event["event_type"] for event in services["producer"].events] == [
        "maintenance.mode.enabled",
        "maintenance.mode.disabled",
    ]
    assert services["producer"].events[-1]["payload"]["disable_kind"] == "manual"
