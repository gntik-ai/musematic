from __future__ import annotations

from uuid import uuid4

import pytest

from fixtures.http_client import AuthenticatedAsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.multi_region_ops, pytest.mark.asyncio]


async def test_failover_rehearsal_records_run_history(
    http_client: AuthenticatedAsyncClient,
) -> None:
    suffix = uuid4().hex[:8]
    plan = await http_client.json_request(
        "POST",
        "/api/v1/admin/regions/failover-plans",
        json={
            "name": f"primary-to-dr-{suffix}",
            "from_region": "eu-west",
            "to_region": "us-east",
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
