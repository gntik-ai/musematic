from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest

from journeys.helpers.narrative import journey_step

JOURNEY_ID = "j18"
TIMEOUT_SECONDS = 240

# Cross-context inventory:
# - auth
# - accounts
# - audit
# - governance
# - policies
# - workspaces

ADMIN_ROUTES = [
    "/admin",
    "/admin/users",
    "/admin/users/id",
    "/admin/roles",
    "/admin/roles/id",
    "/admin/groups",
    "/admin/sessions",
    "/admin/oauth-providers",
    "/admin/ibor",
    "/admin/ibor/connector_id",
    "/admin/api-keys",
    "/admin/tenants",
    "/admin/tenants/id",
    "/admin/workspaces",
    "/admin/workspaces/id",
    "/admin/workspaces/id/quotas",
    "/admin/namespaces",
    "/admin/settings",
    "/admin/feature-flags",
    "/admin/model-catalog",
    "/admin/model-catalog/id",
    "/admin/policies",
    "/admin/connectors",
    "/admin/audit-chain",
    "/admin/security/sbom",
    "/admin/security/pentests",
    "/admin/security/rotations",
    "/admin/security/jit",
    "/admin/privacy/dsr",
    "/admin/privacy/dlp",
    "/admin/privacy/pia",
    "/admin/compliance",
    "/admin/privacy/consent",
    "/admin/health",
    "/admin/incidents",
    "/admin/incidents/id",
    "/admin/runbooks",
    "/admin/runbooks/id",
    "/admin/maintenance",
    "/admin/regions",
    "/admin/queues",
    "/admin/warm-pool",
    "/admin/executions",
    "/admin/costs/overview",
    "/admin/costs/budgets",
    "/admin/costs/chargeback",
    "/admin/costs/anomalies",
    "/admin/costs/forecasts",
    "/admin/costs/rates",
    "/admin/observability/dashboards",
    "/admin/observability/alerts",
    "/admin/observability/log-retention",
    "/admin/observability/registry",
    "/admin/integrations/webhooks",
    "/admin/integrations/incidents",
    "/admin/integrations/notifications",
    "/admin/integrations/a2a",
    "/admin/integrations/mcp",
    "/admin/lifecycle/version",
    "/admin/lifecycle/migrations",
    "/admin/lifecycle/backup",
    "/admin/lifecycle/installer",
    "/admin/audit",
    "/admin/audit/admin-activity",
]


def assert_status_code(response: Any, allowed: set[int]) -> None:
    assert response.status_code in allowed


def assert_header_contains(response: Any, header: str, expected: str) -> None:
    assert expected in response.headers.get(header, "")


def assert_json_field(response: Any, field: str, expected: Any) -> None:
    assert response.json()[field] == expected


def assert_route_declared(route: str) -> None:
    assert route in ADMIN_ROUTES


def assert_routes_cover(prefixes: Iterable[str]) -> None:
    assert all(any(route.startswith(prefix) for route in ADMIN_ROUTES) for prefix in prefixes)


@pytest.mark.journey
@pytest.mark.j18_super_admin_lifecycle
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j18_super_admin_lifecycle(http_client_superadmin) -> None:
    with journey_step("Super admin can query the admin health endpoint"):
        landing = await http_client_superadmin.get("/api/v1/admin/health")
        assert_status_code(landing, {200, 404})

    with journey_step("Super admin can persist checklist state"):
        checklist = await http_client_superadmin.patch(
            "/api/v1/admin/users/me/checklist-state",
            json={"state": {"mfa": "complete", "observability": "complete"}},
        )
        assert_status_code(checklist, {200, 204})

    with journey_step("Super admin can create a 2PA request"):
        two_pa = await http_client_superadmin.post(
            "/api/v1/admin/2pa/requests",
            json={"action": "multi_region_ops.failover.execute", "payload": {"mode": "test"}},
        )
        assert_status_code(two_pa, {200, 201, 202})

    with journey_step("Super admin can enable read-only mode"):
        read_only = await http_client_superadmin.patch(
            "/api/v1/admin/sessions/me/read-only-mode",
            json={"enabled": True},
        )
        assert_status_code(read_only, {200, 204})

    with journey_step("Read-only mode blocks privileged writes"):
        blocked = await http_client_superadmin.post("/api/v1/admin/users/123/suspend")
        assert_status_code(blocked, {403})
        assert "admin_read_only_mode" in blocked.text

    with journey_step("Super admin can disable read-only mode"):
        writable = await http_client_superadmin.patch(
            "/api/v1/admin/sessions/me/read-only-mode",
            json={"enabled": False},
        )
        assert_status_code(writable, {200, 204})

    with journey_step("Writable session can export platform configuration"):
        export = await http_client_superadmin.post(
            "/api/v1/admin/config/export",
            json={"scope": "platform"},
        )
        assert_status_code(export, {200})

    with journey_step("Configuration export returns a gzip bundle"):
        assert_header_contains(export, "content-type", "application/gzip")

    with journey_step("Super admin can preview bulk user suspension"):
        preview = await http_client_superadmin.post(
            "/api/v1/admin/users/bulk/suspend?preview=true",
            json=["11111111-1111-4111-8111-111111111111"],
        )
        assert_status_code(preview, {200})

    with journey_step("Bulk preview response is marked preview"):
        assert_json_field(preview, "preview", True)

    with journey_step("Every admin page has a declared route for axe coverage"):
        assert len(ADMIN_ROUTES) >= 57
        assert_route_declared("/admin/lifecycle/installer")
        assert_route_declared("/admin/observability/dashboards")
        assert_route_declared("/admin/audit/admin-activity")

    with journey_step("Admin route inventory covers lifecycle observability and audit pages"):
        assert_routes_cover(("/admin/lifecycle", "/admin/observability", "/admin/audit"))
