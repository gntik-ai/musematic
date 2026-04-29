from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fixtures.http_client import AuthenticatedAsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.multi_region_ops, pytest.mark.asyncio]


async def test_maintenance_mode_blocks_writes_but_keeps_reads_available(
    http_client: AuthenticatedAsyncClient,
) -> None:
    starts_at = datetime.now(UTC) + timedelta(minutes=5)
    window = await http_client.json_request(
        "POST",
        "/api/v1/admin/maintenance/windows",
        json={
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(minutes=30)).isoformat(),
            "reason": "multi-region E2E drain check",
            "announcement_text": "Writes are paused for maintenance",
            "blocks_writes": True,
        },
        expected={201},
    )
    active = await http_client.json_request(
        "POST",
        f"/api/v1/admin/maintenance/windows/{window['id']}/enable",
        expected={200},
    )
    read_response = await http_client.get("/api/v1/maintenance/windows/active")
    write_response = await http_client.post(
        "/api/v1/admin/regions",
        json={"region_code": "blocked-write", "region_role": "secondary"},
    )

    assert active["status"] == "active"
    assert read_response.status_code == 200
    assert write_response.status_code in {503, 409, 422}

    disabled = await http_client.json_request(
        "POST",
        f"/api/v1/admin/maintenance/windows/{window['id']}/disable",
        json={"disable_kind": "manual"},
        expected={200},
    )
    assert disabled["status"] == "completed"
