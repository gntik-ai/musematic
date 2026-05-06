"""J36 Default Tenant Constraint — UPD-054 (FR-806).

Every forbidden operation against the canonical default tenant must
fail at the API and at the migration layer. The default tenant
remains in healthy `Active` state after the test.

Cross-BC links: tenants/ (constraint) ↔ admin/ (API guards) ↔
migrations (constraint enforcement).
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.journey,
    pytest.mark.j36,
    pytest.mark.skipif(
        os.environ.get("RUN_J36", "0") != "1",
        reason="Requires dev kind cluster + admin API + DB access.",
    ),
    pytest.mark.timeout(480),
]


@pytest.mark.asyncio
async def test_j36_default_tenant_delete_via_api_returns_403(super_admin_client) -> None:
    """DELETE /api/v1/admin/tenants/default returns 403 with
    `default_tenant_immutable`.
    """
    pytest.skip("Scaffold — body lands during US1 implementation.")


@pytest.mark.asyncio
async def test_j36_default_tenant_suspend_blocked(super_admin_client) -> None:
    """POST .../tenants/default/suspend returns 403."""
    pytest.skip("Scaffold — body lands during US1 implementation.")


@pytest.mark.asyncio
async def test_j36_default_tenant_rename_blocked(super_admin_client) -> None:
    """PATCH .../tenants/default {slug: new-name} returns 403."""
    pytest.skip("Scaffold — body lands during US1 implementation.")


@pytest.mark.asyncio
async def test_j36_migration_dropping_constraint_aborts(super_admin_client) -> None:
    """A migration that would drop the existence constraint fails at the
    constraint check; default tenant remains Active.
    """
    pytest.skip("Scaffold — body lands during US1 implementation.")
