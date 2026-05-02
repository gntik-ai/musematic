"""Tenant first-admin setup invitations.

Revision ID: 107_tenant_first_admin_invitations
Revises: 106_user_onboarding_states
Create Date: 2026-05-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "107_tenant_first_admin_invitations"
down_revision: str | None = "106_user_onboarding_states"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PG_UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "tenant_first_admin_invitations",
        sa.Column(
            "id",
            PG_UUID,
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", PG_UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("target_email", sa.String(length=320), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prior_token_invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "setup_step_state",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("mfa_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_by_super_admin_id",
            PG_UUID,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("consumed_by_user_id", PG_UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint(
            "token_hash",
            name="tenant_first_admin_invitations_token_unique",
        ),
    )
    op.create_index(
        "tenant_first_admin_invitations_tenant_active_idx",
        "tenant_first_admin_invitations",
        ["tenant_id", "expires_at"],
        postgresql_where=sa.text(
            "consumed_at IS NULL AND prior_token_invalidated_at IS NULL"
        ),
    )
    op.create_index(
        "tenant_first_admin_invitations_target_email_idx",
        "tenant_first_admin_invitations",
        ["target_email", "expires_at"],
    )
    _enable_rls("tenant_first_admin_invitations")


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "tenant_first_admin_invitations"')
    op.execute('ALTER TABLE "tenant_first_admin_invitations" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "tenant_first_admin_invitations" DISABLE ROW LEVEL SECURITY')
    op.drop_index(
        "tenant_first_admin_invitations_target_email_idx",
        table_name="tenant_first_admin_invitations",
    )
    op.drop_index(
        "tenant_first_admin_invitations_tenant_active_idx",
        table_name="tenant_first_admin_invitations",
    )
    op.drop_table("tenant_first_admin_invitations")


def _enable_rls(table_name: str) -> None:
    quoted = '"' + table_name.replace('"', '""') + '"'
    op.execute(f"ALTER TABLE {quoted} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {quoted} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {quoted}
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )
