from __future__ import annotations

import pytest

from tests.integration.multi_region_ops.support import (
    async_client,
    build_app,
    build_services,
    seeded_repository,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_upgrade_status_returns_concurrent_runtime_versions() -> None:
    app = build_app(
        build_services(seeded_repository()),
        runtime_manifest={
            "runtime_versions": [
                {
                    "runtime_id": "python-worker",
                    "version": "2026.04.1",
                    "status": "serving",
                    "coexistence_until": "2026-05-01T00:00:00Z",
                },
                {
                    "runtime_id": "python-worker-canary",
                    "version": "2026.04.2",
                    "status": "canary",
                    "coexistence_until": "2026-05-01T00:00:00Z",
                },
            ]
        },
    )

    async with await async_client(app) as client:
        response = await client.get("/api/v1/regions/upgrade-status")

    assert response.status_code == 200
    versions = response.json()["runtime_versions"]
    assert [item["runtime_id"] for item in versions] == [
        "python-worker",
        "python-worker-canary",
    ]
    assert {item["version"] for item in versions} == {"2026.04.1", "2026.04.2"}
