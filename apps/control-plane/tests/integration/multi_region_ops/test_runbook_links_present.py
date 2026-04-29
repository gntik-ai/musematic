from __future__ import annotations

import pytest

from tests.integration.multi_region_ops.support import (
    REPO_ROOT,
    async_client,
    build_app,
    build_services,
    seeded_repository,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_runbook_links_present_in_upgrade_status_and_files_exist() -> None:
    app = build_app(build_services(seeded_repository()))

    async with await async_client(app) as client:
        response = await client.get("/api/v1/regions/upgrade-status")

    assert response.status_code == 200
    links = response.json()["documentation_links"]
    assert links == {
        "failover": "/docs/runbooks/failover.md",
        "zero_downtime_upgrade": "/docs/runbooks/zero-downtime-upgrade.md",
        "active_active_considerations": "/docs/runbooks/active-active-considerations.md",
    }
    for filename in (
        "failover.md",
        "zero-downtime-upgrade.md",
        "active-active-considerations.md",
    ):
        assert (REPO_ROOT / "deploy" / "runbooks" / filename).exists()
    assert "Rollback-fails-too" in (
        REPO_ROOT / "deploy" / "runbooks" / "zero-downtime-upgrade.md"
    ).read_text(encoding="utf-8")
