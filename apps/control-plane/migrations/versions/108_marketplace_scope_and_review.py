"""Marketplace scope dimension + public-review lifecycle on agents.

Adds the marketplace scope, review-status lifecycle, and fork-provenance
columns to ``registry_agent_profiles`` per UPD-049:

* ``marketplace_scope`` (workspace | tenant | public_default_tenant)
* ``review_status`` (draft | pending_review | approved | rejected
  | published | deprecated)
* ``reviewed_at`` / ``reviewed_by_user_id`` / ``review_notes``
* ``forked_from_agent_id`` (self-FK marking a fork's provenance source)

Also installs:

1. A partial index ``registry_agent_profiles_review_status_idx`` covering
   ``review_status = 'pending_review'`` to keep the platform-staff review
   queue cheap.
2. A partial index ``registry_agent_profiles_scope_status_idx`` covering
   ``marketplace_scope = 'public_default_tenant' AND
   review_status = 'published'`` to keep cross-tenant marketplace listing
   reads cheap.
3. A CHECK constraint
   ``registry_agent_profiles_public_only_default_tenant`` that refuses
   any row with ``marketplace_scope = 'public_default_tenant'`` whose
   ``tenant_id`` is not the well-known default-tenant UUID. This is the
   database-layer leg of the three-layer Enterprise public-publish
   refusal (FR-010 / FR-011 / FR-012).
4. The ``agents_visibility`` RLS policy that REPLACES the original
   ``tenant_isolation`` policy. The new policy keeps tenant isolation as
   the default branch and adds two narrow exceptions to permit
   ``public_default_tenant + published`` rows to be visible cross-tenant
   when the consumer is the default tenant OR when the consumer's
   tenant has flipped the ``consume_public_marketplace`` feature flag.

Revision ID: 108_marketplace_scope_review
Revises: 107_tenant_first_admin_invites
Create Date: 2026-05-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "108_marketplace_scope_review"
down_revision: str | None = "107_tenant_first_admin_invites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PG_UUID = postgresql.UUID(as_uuid=True)

DEFAULT_TENANT_UUID = "00000000-0000-0000-0000-000000000001"
"""Well-known default-tenant identifier seeded by UPD-046 migration 096.
Reproduced here so the CHECK constraint expression is self-contained and
does not depend on a runtime SELECT against ``tenants``."""


def upgrade() -> None:
    # --- 1. Column additions -------------------------------------------------
    op.add_column(
        "registry_agent_profiles",
        sa.Column(
            "marketplace_scope",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'workspace'"),
        ),
    )
    op.create_check_constraint(
        "registry_agent_profiles_marketplace_scope_check",
        "registry_agent_profiles",
        "marketplace_scope IN ('workspace', 'tenant', 'public_default_tenant')",
    )

    op.add_column(
        "registry_agent_profiles",
        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
    )
    op.create_check_constraint(
        "registry_agent_profiles_review_status_check",
        "registry_agent_profiles",
        (
            "review_status IN ("
            "'draft', 'pending_review', 'approved', 'rejected', "
            "'published', 'deprecated'"
            ")"
        ),
    )

    op.add_column(
        "registry_agent_profiles",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "registry_agent_profiles",
        sa.Column(
            "reviewed_by_user_id",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "registry_agent_profiles",
        sa.Column("review_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "registry_agent_profiles",
        sa.Column(
            "forked_from_agent_id",
            PG_UUID,
            sa.ForeignKey("registry_agent_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # --- 2. Partial indexes --------------------------------------------------
    op.create_index(
        "registry_agent_profiles_review_status_idx",
        "registry_agent_profiles",
        ["review_status"],
        postgresql_where=sa.text("review_status = 'pending_review'"),
    )
    op.create_index(
        "registry_agent_profiles_scope_status_idx",
        "registry_agent_profiles",
        ["marketplace_scope", "review_status"],
        postgresql_where=sa.text(
            "marketplace_scope = 'public_default_tenant' "
            "AND review_status = 'published'"
        ),
    )

    # --- 3. Three-layer Enterprise refusal (DB layer) -------------------------
    # FR-012: rows with marketplace_scope='public_default_tenant' may exist
    # ONLY when the owning tenant is the default tenant. Combined with the
    # application service guard and the UI scope-picker disable state, this
    # gives defense-in-depth refusal of public publishing from Enterprise
    # tenants.
    op.create_check_constraint(
        "registry_agent_profiles_public_only_default_tenant",
        "registry_agent_profiles",
        (
            "marketplace_scope <> 'public_default_tenant' "
            f"OR tenant_id = '{DEFAULT_TENANT_UUID}'::uuid"
        ),
    )

    # --- 4. RLS policy replacement -------------------------------------------
    # Drop the original tenant_isolation policy created by UPD-046
    # migration 100 and replace with agents_visibility. The new policy
    # keeps strict tenant isolation as the default branch and adds two
    # exceptions for cross-tenant visibility of public-published agents:
    #
    #   (a) when the consumer is the default tenant, public-published
    #       rows are visible (the SaaS public hub is owned by the default
    #       tenant, so default-tenant users see their own rows by the
    #       first branch and the public ones by this branch — these
    #       overlap, which is fine);
    #   (b) when the consumer is an Enterprise tenant whose
    #       consume_public_marketplace feature flag is set, public-
    #       published rows are visible read-only.
    #
    # Both exceptions require review_status = 'published', so unapproved
    # submissions never leak.
    op.execute(
        'DROP POLICY IF EXISTS tenant_isolation ON "registry_agent_profiles"'
    )
    op.execute(
        """
        CREATE POLICY agents_visibility ON "registry_agent_profiles"
        USING (
            tenant_id = current_setting('app.tenant_id', true)::uuid
            OR (
                marketplace_scope = 'public_default_tenant'
                AND review_status = 'published'
                AND current_setting('app.tenant_kind', true) = 'default'
            )
            OR (
                marketplace_scope = 'public_default_tenant'
                AND review_status = 'published'
                AND current_setting('app.consume_public_marketplace', true) = 'true'
            )
        )
        """
    )
    # FORCE ROW LEVEL SECURITY was already enabled by migration 100; the
    # ALTER TABLE statement here is idempotent and explicit.
    op.execute(
        'ALTER TABLE "registry_agent_profiles" FORCE ROW LEVEL SECURITY'
    )


def downgrade() -> None:
    # Restore the original tenant_isolation policy on the agents table.
    op.execute(
        'DROP POLICY IF EXISTS agents_visibility ON "registry_agent_profiles"'
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation ON "registry_agent_profiles"
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )

    op.drop_constraint(
        "registry_agent_profiles_public_only_default_tenant",
        "registry_agent_profiles",
        type_="check",
    )
    op.drop_index(
        "registry_agent_profiles_scope_status_idx",
        table_name="registry_agent_profiles",
    )
    op.drop_index(
        "registry_agent_profiles_review_status_idx",
        table_name="registry_agent_profiles",
    )

    op.drop_column("registry_agent_profiles", "forked_from_agent_id")
    op.drop_column("registry_agent_profiles", "review_notes")
    op.drop_column("registry_agent_profiles", "reviewed_by_user_id")
    op.drop_column("registry_agent_profiles", "reviewed_at")

    op.drop_constraint(
        "registry_agent_profiles_review_status_check",
        "registry_agent_profiles",
        type_="check",
    )
    op.drop_column("registry_agent_profiles", "review_status")

    op.drop_constraint(
        "registry_agent_profiles_marketplace_scope_check",
        "registry_agent_profiles",
        type_="check",
    )
    op.drop_column("registry_agent_profiles", "marketplace_scope")
