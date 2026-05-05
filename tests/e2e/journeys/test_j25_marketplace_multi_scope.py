"""J25 Marketplace Multi-Scope — UPD-054 (FR-795).

Validates the full visibility matrix for workspace / tenant /
public_default_tenant scopes including the
``consume_public_marketplace`` Enterprise flag's effect.

Cross-BC links: marketplace/ ↔ tenants/ (RLS) ↔ accounts/ (per-tenant
users) ↔ governance/ (visibility policy).
"""
from __future__ import annotations

import os

import pytest

from fixtures.tenants import provision_enterprise

pytestmark = [
    pytest.mark.journey,
    pytest.mark.j25,
    pytest.mark.skipif(
        os.environ.get("RUN_J25", "0") != "1",
        reason="Requires dev kind cluster + marketplace seeded with default tenant.",
    ),
    pytest.mark.timeout(480),
]


@pytest.mark.asyncio
async def test_j25_full_scope_visibility_matrix(super_admin_client) -> None:
    """Full matrix per spec.md US4 acceptance scenario 1.

    - Default-tenant user publishes a public_default_tenant agent.
    - Super admin approves it.
    - Second default-tenant user discovers + runs.
    - Acme (consume_public_marketplace=true) sees + runs read-only.
    - Globex (without flag) does NOT see it.
    - Tenant-scope agent inside Acme is invisible from Globex.
    """
    pytest.skip("Scaffold — body lands during US4 implementation.")
    async with provision_enterprise(
        super_admin_client=super_admin_client,
        slug=None,  # auto-generated
        plan="enterprise",
    ) as acme:
        async with provision_enterprise(
            super_admin_client=super_admin_client,
            plan="enterprise",
        ) as globex:
            # 1. Toggle consume_public_marketplace=true on acme via
            #    PATCH /api/v1/admin/tenants/{acme.slug}/feature-flags
            # 2. Default-tenant user publishes agent with scope=public_default_tenant
            # 3. Super-admin POST /api/v1/admin/marketplace-review/{id}/approve
            # 4. Second default-tenant user runs the agent (success)
            # 5. Acme user lists marketplace; expects to see the public agent
            #    AND can run it; the agent shows as "read-only" (no fork rights).
            # 6. Globex user lists marketplace; expects EMPTY public list.
            # 7. Acme creator publishes a tenant-scope agent.
            # 8. Globex user lists Acme's namespace; expects 404 (no leak).
            del acme, globex
