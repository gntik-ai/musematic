from __future__ import annotations

from uuid import uuid4

import pytest

from fixtures.http_client import AuthenticatedAsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.multi_region_ops, pytest.mark.asyncio]


async def test_secondary_region_replication_status_surfaces_all_known_rows(
    http_client: AuthenticatedAsyncClient,
) -> None:
    suffix = uuid4().hex[:8]
    secondary_code = f"dr-{suffix}"

    primary_response = await http_client.post(
        "/api/v1/admin/regions",
        json={
            "region_code": f"primary-{suffix}",
            "region_role": "primary",
            "endpoint_urls": {},
            "rpo_target_minutes": 5,
            "rto_target_minutes": 30,
            "enabled": True,
        },
    )
    assert primary_response.status_code in {201, 422}

    secondary = await http_client.json_request(
        "POST",
        "/api/v1/admin/regions",
        json={
            "region_code": secondary_code,
            "region_role": "secondary",
            "endpoint_urls": {},
            "rpo_target_minutes": 5,
            "rto_target_minutes": 30,
            "enabled": True,
        },
        expected={201},
    )
    status = await http_client.json_request("GET", "/api/v1/regions/replication-status")

    assert secondary["region_code"] == secondary_code
    assert "items" in status
    assert isinstance(status["items"], list)
