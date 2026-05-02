"""UPD-049 — RLS cross-product visibility test.

Exercises the ``agents_visibility`` policy installed by migration 108
across the full default-tenant / Enterprise-with-flag / Enterprise-without-flag
× public-published / public-pending-review / private-tenant matrix.

Uses raw SQL via the regular session (NOT the platform-staff BYPASSRLS
session) to verify the database-layer policy is doing the work, not
application-layer filtering.

This test is skipped when no live PostgreSQL fixture is available — the
matrix only makes sense against a real database with the migration applied.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_TENANT_UUID = UUID("00000000-0000-0000-0000-000000000001")

pytestmark = pytest.mark.skipif(
    True,  # Default-skip; flip when the test infrastructure provides the live DB fixture.
    reason=(
        "RLS cross-product visibility requires a live PostgreSQL fixture "
        "with migration 108 applied; enable in the integration-test profile."
    ),
)


async def _set_request_guc(session: AsyncSession, *, tenant_id: UUID, kind: str, consume: bool) -> None:
    """Bind the three GUCs the agents_visibility policy reads."""
    await session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
    await session.execute(text(f"SET LOCAL app.tenant_kind = '{kind}'"))
    await session.execute(
        text(
            "SET LOCAL app.consume_public_marketplace = '"
            f"{'true' if consume else 'false'}'"
        )
    )


async def _count_agents(session: AsyncSession) -> int:
    row = await session.execute(text("SELECT COUNT(*) FROM registry_agent_profiles"))
    return int(row.scalar_one())


@pytest.mark.asyncio
async def test_default_tenant_user_sees_public_published(session: AsyncSession) -> None:
    await _set_request_guc(session, tenant_id=DEFAULT_TENANT_UUID, kind="default", consume=False)
    # Test data fixture must seed at least one public+published row in default tenant.
    assert await _count_agents(session) >= 1


@pytest.mark.asyncio
async def test_default_tenant_user_does_not_see_pending_review(session: AsyncSession) -> None:
    """Public-pending-review rows MUST NOT be visible cross-tenant under any circumstance."""
    # Seed: a row with public scope + pending_review in default tenant should be invisible
    # even to default-tenant users (unapproved drafts cannot leak — FR-021).
    pytest.fail(
        "Replace with a real assertion once the test fixture seeds a "
        "public+pending_review row and verifies it does not appear in counts."
    )


@pytest.mark.asyncio
async def test_enterprise_with_flag_sees_public(session: AsyncSession) -> None:
    acme_tenant_id = uuid4()
    await _set_request_guc(session, tenant_id=acme_tenant_id, kind="enterprise", consume=True)
    # Acme can see public-published rows (which live on the default tenant).
    assert await _count_agents(session) >= 1


@pytest.mark.asyncio
async def test_enterprise_with_flag_does_not_see_pending_review(session: AsyncSession) -> None:
    acme_tenant_id = uuid4()
    await _set_request_guc(session, tenant_id=acme_tenant_id, kind="enterprise", consume=True)
    pytest.fail(
        "Verify that public+pending_review rows are NOT visible to "
        "Enterprise-with-flag tenants (FR-021)."
    )


@pytest.mark.asyncio
async def test_enterprise_without_flag_does_not_see_public(session: AsyncSession) -> None:
    globex_tenant_id = uuid4()
    await _set_request_guc(session, tenant_id=globex_tenant_id, kind="enterprise", consume=False)
    # No public rows visible; only Globex's own private rows (none in this fixture state).
    assert await _count_agents(session) == 0


@pytest.mark.asyncio
async def test_enterprise_cannot_see_other_enterprise_private(session: AsyncSession) -> None:
    acme_tenant_id = uuid4()
    await _set_request_guc(session, tenant_id=acme_tenant_id, kind="enterprise", consume=True)
    # Acme cannot see Globex's private rows even with the consume flag set —
    # the flag is for public-default-tenant rows only.
    pytest.fail(
        "Seed a Globex-private row and verify it does not appear in Acme's count."
    )
