"""UPD-049 migration smoke test — verifies migration 108 declares all the
columns, indexes, CHECK constraints, and the RLS policy replacement that
the data model contract requires.

Pattern matches the existing migration smoke tests (e.g.
``test_107_tenant_first_admin_invitations.py``): static source-text
assertions over the migration file. The full cross-tenant visibility
matrix lives in
``apps/control-plane/tests/integration/marketplace/test_rls_public_visibility.py``.
"""

from __future__ import annotations

from pathlib import Path

MIGRATION_PATH = Path("migrations/versions/108_marketplace_scope_and_review.py")


def _source() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_108_migration_adds_six_marketplace_columns() -> None:
    source = _source()
    for column in (
        "marketplace_scope",
        "review_status",
        "reviewed_at",
        "reviewed_by_user_id",
        "review_notes",
        "forked_from_agent_id",
    ):
        assert column in source, f"migration 108 missing column {column!r}"


def test_108_migration_declares_check_constraints() -> None:
    source = _source()
    assert "registry_agent_profiles_marketplace_scope_check" in source
    assert "registry_agent_profiles_review_status_check" in source
    assert "registry_agent_profiles_public_only_default_tenant" in source
    # The three-layer Enterprise refusal CHECK references the well-known
    # default-tenant UUID literally — no runtime SELECT.
    assert "00000000-0000-0000-0000-000000000001" in source


def test_108_migration_declares_partial_indexes() -> None:
    source = _source()
    assert "registry_agent_profiles_review_status_idx" in source
    assert "registry_agent_profiles_scope_status_idx" in source
    # Both indexes are partial.
    assert "review_status = 'pending_review'" in source
    assert (
        "marketplace_scope = 'public_default_tenant' "
        "AND review_status = 'published'"
    ) in source


def test_108_migration_replaces_tenant_isolation_policy() -> None:
    source = _source()
    assert "DROP POLICY IF EXISTS tenant_isolation" in source
    assert "CREATE POLICY agents_visibility" in source
    # All three branches of the visibility expression must be present.
    assert "current_setting('app.tenant_id', true)::uuid" in source
    assert "current_setting('app.tenant_kind', true) = 'default'" in source
    assert "current_setting('app.consume_public_marketplace', true) = 'true'" in source
    # FORCE ROW LEVEL SECURITY is asserted to remain explicitly set.
    assert "FORCE ROW LEVEL SECURITY" in source


def test_108_migration_chains_to_107() -> None:
    source = _source()
    assert 'down_revision: str | None = "107_tenant_first_admin_invites"' in source
    assert 'revision: str = "108_marketplace_scope_review"' in source
