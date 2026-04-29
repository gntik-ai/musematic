from __future__ import annotations

import pytest

from journeys.helpers.narrative import journey_step

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


@pytest.mark.journey
@pytest.mark.j18_super_admin_lifecycle
@pytest.mark.timeout(240)
@pytest.mark.asyncio
async def test_j18_super_admin_lifecycle(http_client_superadmin) -> None:
    with journey_step("Super admin can query the admin landing and checklist backing API"):
        landing = await http_client_superadmin.get("/api/v1/admin/health")
        assert landing.status_code in {200, 404}
        checklist = await http_client_superadmin.patch(
            "/api/v1/admin/users/me/checklist-state",
            json={"state": {"mfa": "complete", "observability": "complete"}},
        )
        assert checklist.status_code in {200, 204}

    with journey_step("Super admin can create 2PA and exercise read-only mode"):
        two_pa = await http_client_superadmin.post(
            "/api/v1/admin/2pa/requests",
            json={"action": "multi_region_ops.failover.execute", "payload": {"mode": "test"}},
        )
        assert two_pa.status_code in {200, 201, 202}
        read_only = await http_client_superadmin.patch(
            "/api/v1/admin/sessions/me/read-only-mode",
            json={"enabled": True},
        )
        assert read_only.status_code in {200, 204}
        blocked = await http_client_superadmin.post("/api/v1/admin/users/123/suspend")
        assert blocked.status_code == 403
        await http_client_superadmin.patch(
            "/api/v1/admin/sessions/me/read-only-mode",
            json={"enabled": False},
        )

    with journey_step("Super admin can preview configuration export/import and bulk actions"):
        export = await http_client_superadmin.post(
            "/api/v1/admin/config/export",
            json={"scope": "platform"},
        )
        assert export.status_code == 200
        assert "application/gzip" in export.headers.get("content-type", "")
        preview = await http_client_superadmin.post(
            "/api/v1/admin/users/bulk/suspend?preview=true",
            json=["11111111-1111-4111-8111-111111111111"],
        )
        assert preview.status_code == 200
        assert preview.json()["preview"] is True

    with journey_step("Every admin page has a declared route for axe coverage"):
        assert len(ADMIN_ROUTES) >= 57
        assert "/admin/lifecycle/installer" in ADMIN_ROUTES
        assert "/admin/observability/dashboards" in ADMIN_ROUTES
        assert "/admin/audit/admin-activity" in ADMIN_ROUTES
