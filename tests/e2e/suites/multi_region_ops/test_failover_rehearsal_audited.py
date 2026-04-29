from __future__ import annotations

from uuid import uuid4

import pytest

from fixtures.http_client import AuthenticatedAsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.multi_region_ops, pytest.mark.asyncio]


async def test_failover_rehearsal_records_run_history(
    http_client_superadmin: AuthenticatedAsyncClient,
) -> None:
    http_client = http_client_superadmin
    suffix = uuid4().hex[:8]
    from_region, to_region = await _region_pair(http_client, suffix)
    plan = await http_client.json_request(
        "POST",
        "/api/v1/admin/regions/failover-plans",
        json={
            "name": f"primary-to-dr-{suffix}",
            "from_region": from_region,
            "to_region": to_region,
            "steps": [{"kind": "custom", "name": "Operator verification", "parameters": {}}],
            "runbook_url": "/docs/runbooks/failover.md",
        },
        expected={201},
    )
    run = await http_client.json_request(
        "POST",
        f"/api/v1/admin/regions/failover-plans/{plan['id']}/rehearse",
        json={"run_kind": "rehearsal", "reason": "quarterly E2E rehearsal"},
        expected={200},
    )
    history = await http_client.json_request(
        "GET",
        f"/api/v1/regions/failover-plans/{plan['id']}/runs",
        expected={200},
    )

    assert run["plan_id"] == plan["id"]
    assert run["run_kind"] == "rehearsal"
    assert any(item["id"] == run["id"] for item in history)


async def _region_pair(
    http_client: AuthenticatedAsyncClient,
    suffix: str,
) -> tuple[str, str]:
    regions = await http_client.json_request("GET", "/api/v1/regions", expected={200})
    primary = next(
        (
            item["region_code"]
            for item in regions
            if item["region_role"] == "primary" and item["enabled"]
        ),
        None,
    )
    if primary is None:
        primary = f"primary-{suffix}"
        response = await http_client.post(
            "/api/v1/admin/regions",
            json={
                "region_code": primary,
                "region_role": "primary",
                "endpoint_urls": {},
                "rpo_target_minutes": 5,
                "rto_target_minutes": 30,
                "enabled": True,
            },
        )
        assert response.status_code == 201, response.text

    secondary = f"dr-{suffix}"
    response = await http_client.post(
        "/api/v1/admin/regions",
        json={
            "region_code": secondary,
            "region_role": "secondary",
            "endpoint_urls": {},
            "rpo_target_minutes": 5,
            "rto_target_minutes": 30,
            "enabled": True,
        },
    )
    assert response.status_code == 201, response.text
    return primary, secondary
