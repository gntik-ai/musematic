from __future__ import annotations

from platform.multi_region_ops.exceptions import MaintenanceDisableFailedError

import pytest

from tests.integration.multi_region_ops.support import (
    FakeRedis,
    build_services,
    make_window,
    seeded_repository,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_disable_failure_keeps_window_active_and_fires_incident() -> None:
    repository = seeded_repository()
    active = make_window(status="active")
    repository.windows[active.id] = active
    services = build_services(repository, redis=FakeRedis(fail_delete=True))

    with pytest.raises(MaintenanceDisableFailedError):
        await services["maintenance"].disable(active.id)

    assert active.status == "active"
    assert active.disable_failure_reason == "redis unavailable"
    assert services["incident_trigger"].signals[-1].alert_rule_class == "maintenance_disable_failed"
