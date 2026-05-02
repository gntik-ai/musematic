"""User onboarding states and default-workspace idempotency.

Revision ID: 106_user_onboarding_states
Revises: 105_execution_paused_quota
Create Date: 2026-05-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "106_user_onboarding_states"
down_revision: str | None = "105_execution_paused_quota"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PG_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.drop_constraint("uq_accounts_users_email", "accounts_users", type_="unique")
    op.create_unique_constraint(
        "uq_accounts_users_tenant_email",
        "accounts_users",
        ["tenant_id", "email"],
    )
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.create_unique_constraint("uq_users_tenant_email", "users", ["tenant_id", "email"])
    op.drop_constraint("uq_user_credentials_email", "user_credentials", type_="unique")
    op.create_unique_constraint(
        "uq_user_credentials_tenant_email",
        "user_credentials",
        ["tenant_id", "email"],
    )
    op.create_table(
        "user_onboarding_states",
        sa.Column(
            "id",
            PG_UUID,
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", PG_UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", PG_UUID, sa.ForeignKey("accounts_users.id"), nullable=False),
        sa.Column(
            "step_workspace_named",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "step_invitations_sent_or_skipped",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "step_first_agent_created_or_skipped",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "step_tour_started_or_skipped",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "last_step_attempted",
            sa.String(length=32),
            nullable=False,
            server_default="workspace_named",
        ),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "last_step_attempted IN "
            "('workspace_named','invitations','first_agent','tour','done')",
            name="ck_user_onboarding_states_last_step",
        ),
        sa.UniqueConstraint("user_id", name="user_onboarding_states_user_unique"),
    )
    op.create_index(
        "user_onboarding_states_tenant_idx",
        "user_onboarding_states",
        ["tenant_id"],
    )
    op.create_index(
        "workspaces_user_default_unique",
        "workspaces_workspaces",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )
    _enable_rls("user_onboarding_states")


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "user_onboarding_states"')
    op.execute('ALTER TABLE "user_onboarding_states" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "user_onboarding_states" DISABLE ROW LEVEL SECURITY')
    op.drop_index("workspaces_user_default_unique", table_name="workspaces_workspaces")
    op.drop_index("user_onboarding_states_tenant_idx", table_name="user_onboarding_states")
    op.drop_table("user_onboarding_states")
    op.drop_constraint(
        "uq_user_credentials_tenant_email",
        "user_credentials",
        type_="unique",
    )
    op.create_unique_constraint("uq_user_credentials_email", "user_credentials", ["email"])
    op.drop_constraint("uq_users_tenant_email", "users", type_="unique")
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.drop_constraint(
        "uq_accounts_users_tenant_email",
        "accounts_users",
        type_="unique",
    )
    op.create_unique_constraint("uq_accounts_users_email", "accounts_users", ["email"])


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
