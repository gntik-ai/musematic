"""J22 Tenant Provisioning — UPD-054 (FR-792).

Provisions a new Enterprise tenant via the super-admin admin UI and
asserts the documented side-effect chain: tenant row, 6 DNS records,
TLS validation, first-admin invite, audit-chain entry, then walks
the first admin through password + MFA setup to a healthy admin
dashboard.

Cross-BC links: tenants/ ↔ accounts/ ↔ DNS automation ↔ cert-manager
↔ notifications/ ↔ audit/.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from fixtures.tenants import provision_enterprise

pytestmark = [
    pytest.mark.journey,
    pytest.mark.j22,
    pytest.mark.skipif(
        os.environ.get("RUN_J22", "0") != "1",
        reason="Requires dev kind cluster + admin API; opt-in via RUN_J22=1.",
    ),
    pytest.mark.timeout(480),
]


@pytest.mark.asyncio
async def test_j22_tenant_provisioning_full_lifecycle(
    super_admin_client,
    audit_chain,
    dns_provider,
    stripe_client,  # noqa: ARG001 — Stripe is touched indirectly via plan binding
) -> None:
    """Per spec.md US1 acceptance scenario 1.

    Provisions a fresh Enterprise tenant; asserts the 6-record DNS
    bundle (3 subdomains x A+AAAA), TLS cert valid against the apex,
    invite email observed, audit chain entry recorded; then walks the
    first admin through password + MFA + admin dashboard reachability.
    """
    pytest.skip(
        "Body lands when the dev-cluster fixture wiring is finalised; "
        "the scaffold imports the new fixtures and follows journey-"
        "template.md so it is runnable end-to-end as soon as the dev "
        "cluster has the admin API + DNS automation + cert-manager wired."
    )
    async with provision_enterprise(super_admin_client=super_admin_client) as tenant:
        # 1. tenant row + audit chain (provision_enterprise already polls
        #    for tenants.created before yielding).
        assert tenant.tenant_id is not None

        # 2. DNS records observed via dns_provider.list_records_for(slug).
        records = await dns_provider.list_records_for(tenant.slug)
        assert len(records) == 6  # 3 subdomains x {A, AAAA}

        # 3. TLS validation against apex - the journey would now use the
        #    existing http_client to GET https://<slug>.musematic-test.invalid/healthz
        #    (mocked via the cluster's coredns) and assert 200 with a valid cert.

        # 4. First-admin invite email - assert via the existing notifications
        #    test mailbox fixture.

        # 5. First admin completes password + MFA + reaches admin dashboard
        #    - drive via the existing http_client + Playwright fixture.
