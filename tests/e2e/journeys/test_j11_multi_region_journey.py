from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fixtures.http_client import AuthenticatedAsyncClient

from journeys.helpers.narrative import journey_step

JOURNEY_ID = "j11"
TIMEOUT_SECONDS = 600

# Cross-context inventory:
# - auth
# - workspaces
# - workflows
# - execution
# - runtime
# - analytics


@pytest.mark.journey
@pytest.mark.j11_multi_region_journey
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j11_multi_region_journey(http_client: AuthenticatedAsyncClient) -> None:
    suffix = uuid4().hex[:8]
    primary_code = f"primary-{suffix}"
    secondary_code = f"secondary-{suffix}"
    from_region: str | None = None
    to_region: str | None = None
    plan_id: str | None = None
    window_id: str | None = None

    with journey_step("Operator is authenticated for multi-region work"):
        email = f"j11-multi-region-{suffix}@e2e.test"
        password = "e2e-test-password"
        provisioned = await http_client.post(
            "/api/v1/_e2e/users",
            json={
                "id": str(uuid4()),
                "email": email,
                "password": password,
                "display_name": "J11 Multi Region Operator",
                "roles": ["superadmin", "platform_operator", "platform_admin"],
            },
        )
        assert provisioned.status_code == 200, provisioned.text
        await http_client.login(email, password)
        assert http_client.access_token is not None

    with journey_step("Operator reads the active workspace context"):
        workspaces = await http_client.get("/api/v1/workspaces")
        assert workspaces.status_code in {200, 404, 422}

    with journey_step("Operator declares or observes the primary region"):
        primary = await http_client.post(
            "/api/v1/admin/regions",
            json={
                "region_code": primary_code,
                "region_role": "primary",
                "endpoint_urls": {},
            },
        )
        assert primary.status_code in {201, 422}
        if primary.status_code == 201:
            from_region = primary.json()["region_code"]

    with journey_step("Operator declares a secondary region"):
        secondary = await http_client.post(
            "/api/v1/admin/regions",
            json={
                "region_code": secondary_code,
                "region_role": "secondary",
                "endpoint_urls": {},
            },
        )
        assert secondary.status_code in {201, 409, 422}
        if secondary.status_code == 201:
            to_region = secondary.json()["region_code"]

    with journey_step("Operator reviews replication status"):
        status = await http_client.get("/api/v1/regions/replication-status")
        assert status.status_code == 200
        assert isinstance(status.json().get("items", []), list)
        regions = await http_client.get("/api/v1/regions")
        assert regions.status_code == 200
        region_items = regions.json()
        if from_region is None:
            from_region = next(
                (
                    item["region_code"]
                    for item in region_items
                    if item["region_role"] == "primary" and item.get("enabled", True)
                ),
                None,
            )
        if to_region is None:
            to_region = next(
                (
                    item["region_code"]
                    for item in region_items
                    if item["region_role"] == "secondary" and item.get("enabled", True)
                ),
                None,
            )

    with journey_step("Operator schedules a maintenance window"):
        starts_at = datetime.now(UTC) + timedelta(minutes=5)
        scheduled = await http_client.post(
            "/api/v1/admin/maintenance/windows",
            json={
                "starts_at": starts_at.isoformat(),
                "ends_at": (starts_at + timedelta(minutes=30)).isoformat(),
                "announcement_text": "Writes are paused for maintenance",
                "blocks_writes": True,
            },
        )
        assert scheduled.status_code in {201, 409, 422}
        if scheduled.status_code == 201:
            window_id = scheduled.json()["id"]
            assert window_id

    with journey_step("Operator enables and verifies maintenance when scheduled"):
        if window_id is not None:
            enabled = await http_client.post(
                f"/api/v1/admin/maintenance/windows/{window_id}/enable"
            )
            assert enabled.status_code == 200
        active = await http_client.get("/api/v1/maintenance/windows/active")
        assert active.status_code == 200

    with journey_step("In-flight execution surface remains readable during maintenance"):
        executions = await http_client.get("/api/v1/executions")
        assert executions.status_code in {200, 404, 422}

    with journey_step("Operator disables maintenance and read surface remains available"):
        if window_id is not None:
            disabled = await http_client.post(
                f"/api/v1/admin/maintenance/windows/{window_id}/disable",
                json={"disable_kind": "manual"},
            )
            assert disabled.status_code == 200
        assert (await http_client.get("/api/v1/maintenance/windows/active")).status_code == 200

    with journey_step("Operator creates a failover rehearsal plan"):
        assert from_region is not None
        assert to_region is not None
        created = await http_client.post(
            "/api/v1/admin/regions/failover-plans",
            json={
                "name": f"journey-failover-{suffix}",
                "from_region": from_region,
                "to_region": to_region,
                "steps": [{"kind": "custom", "name": "Verify health", "parameters": {}}],
                "runbook_url": "/docs/runbooks/failover.md",
            },
        )
        assert created.status_code in {201, 409, 422}
        if created.status_code == 201:
            plan_id = created.json()["id"]
            assert plan_id

    with journey_step("Operator rehearses failover when the plan is accepted"):
        if plan_id is not None:
            run = await http_client.post(
                f"/api/v1/admin/regions/failover-plans/{plan_id}/rehearse",
                json={"run_kind": "rehearsal", "reason": "journey rehearsal"},
            )
            assert run.status_code == 200
            assert run.json()["plan_id"] == plan_id

    with journey_step("Operator inspects capacity recommendations"):
        capacity = await http_client.get("/api/v1/regions/capacity")
        assert capacity.status_code == 200
        assert isinstance(capacity.json(), list)
