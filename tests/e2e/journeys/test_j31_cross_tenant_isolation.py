"""J31 Cross-Tenant Isolation — UPD-054 (FR-801).

Negative tests across every tenant-scoped resource (workspaces,
agents, executions, audit, costs, secrets); positive test under
privileged platform-staff role. Asserts 404 (not 403) on every
cross-tenant attempt to prevent existence leakage.

Cross-BC links: tenants/ (RLS) ↔ workspaces/ ↔ marketplace/ ↔
governance/ ↔ accounts/ ↔ analytics/.
"""
from __future__ import annotations

import os

import pytest

from fixtures.tenants import provision_enterprise

pytestmark = [
    pytest.mark.journey,
    pytest.mark.j31,
    pytest.mark.skipif(
        os.environ.get("RUN_J31", "0") != "1",
        reason="Requires dev kind cluster + RLS + accounts + marketplace.",
    ),
    pytest.mark.timeout(480),
]


_RESOURCE_PATHS = [
    "/api/v1/workspaces",
    "/api/v1/agents",
    "/api/v1/executions",
    "/api/v1/audit/entries",
    "/api/v1/cost/summary",
    "/api/v1/secrets",
]


@pytest.mark.asyncio
async def test_j31_cross_tenant_negative_returns_404_not_403(super_admin_client) -> None:
    """User in tenant A cannot read tenant B's resources; every cross-tenant
    attempt returns 404 (NOT 403) to avoid existence-leakage.
    """
    pytest.skip("Scaffold — body lands during US1 implementation.")
    async with provision_enterprise(super_admin_client=super_admin_client) as tenant_a:
        async with provision_enterprise(super_admin_client=super_admin_client) as tenant_b:
            # 1. Synthetic user in tenant_a; sign in.
            # 2. For each path in _RESOURCE_PATHS:
            #    - GET against tenant_b's namespace via crafted Host header
            #    - assert response.status_code == 404
            #    - assert no row data in body
            del tenant_a, tenant_b


@pytest.mark.asyncio
async def test_j31_platform_staff_can_see_both_tenants(super_admin_client) -> None:
    """Privileged platform-staff role CAN see both tenants' data — verifies
    RLS isn't accidentally blocking legitimate cross-tenant access.
    """
    pytest.skip("Scaffold — body lands during US1 implementation.")
