"""J24 Enterprise Tenant Provisioning Variants — UPD-054 (FR-794).

Super-admin-driven Enterprise tenant creation with branding upload,
SSO config, and per-tenant feature-flag editing.

Cross-BC links: tenants/ ↔ admin/ ↔ accounts/ (SSO) ↔ governance/
(feature flags).
"""
from __future__ import annotations

import os

import pytest

from fixtures.tenants import provision_enterprise

pytestmark = [
    pytest.mark.journey,
    pytest.mark.j24,
    pytest.mark.skipif(
        os.environ.get("RUN_J24", "0") != "1",
        reason="Requires dev kind cluster + admin API + branding storage.",
    ),
    pytest.mark.timeout(480),
]


@pytest.mark.asyncio
async def test_j24_enterprise_full_admin_provisioning(super_admin_client) -> None:
    """Super admin creates Enterprise tenant; uploads branding logo;
    configures SSO; toggles per-tenant feature flag — all surfaces
    visible to the tenant admin afterward.
    """
    pytest.skip("Scaffold — body lands during US1 implementation.")
    async with provision_enterprise(
        super_admin_client=super_admin_client,
        plan="enterprise",
    ) as tenant:
        # 1. POST branding logo to /api/v1/admin/tenants/{slug}/branding
        # 2. POST SSO config (OIDC issuer + client id) to /api/v1/admin/tenants/{slug}/sso
        # 3. PATCH per-tenant feature flag /api/v1/admin/tenants/{slug}/feature-flags
        #    enabling consume_public_marketplace; assert response 200.
        # 4. Tenant admin signs in; assert branding header renders, SSO option
        #    appears on login page, feature-flag-gated UI is visible.
        del tenant
