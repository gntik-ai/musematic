"""Add workspace owner workbench settings.

Revision ID: 071_workspace_owner_workbench
Revises: 070_user_self_service_extensions
Create Date: 2026-04-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "071_workspace_owner_workbench"
down_revision: str | None = "070_user_self_service_extensions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _jsonb_settings_column(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


def upgrade() -> None:
    op.add_column("workspaces_settings", _jsonb_settings_column("quota_config"))
    op.add_column("workspaces_settings", _jsonb_settings_column("dlp_rules"))
    op.add_column("workspaces_settings", _jsonb_settings_column("residency_config"))

    action_type = postgresql.ENUM(
        "workspace_transfer_ownership",
        name="two_person_approval_action_type",
        create_type=False,
    )
    challenge_status = postgresql.ENUM(
        "pending",
        "approved",
        "consumed",
        "expired",
        name="two_person_approval_challenge_status",
        create_type=False,
    )
    bind = op.get_bind()
    action_type.create(bind, checkfirst=True)
    challenge_status.create(bind, checkfirst=True)

    op.create_table(
        "two_person_approval_challenges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("action_type", action_type, nullable=False),
        sa.Column(
            "action_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("initiator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("co_signer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            challenge_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["initiator_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["co_signer_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_two_person_approval_challenges_pending_expiry",
        "two_person_approval_challenges",
        ["expires_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_two_person_approval_challenges_initiator",
        "two_person_approval_challenges",
        ["initiator_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_two_person_approval_challenges_initiator",
        table_name="two_person_approval_challenges",
    )
    op.drop_index(
        "ix_two_person_approval_challenges_pending_expiry",
        table_name="two_person_approval_challenges",
    )
    op.drop_table("two_person_approval_challenges")

    bind = op.get_bind()
    postgresql.ENUM(
        "pending",
        "approved",
        "consumed",
        "expired",
        name="two_person_approval_challenge_status",
    ).drop(bind, checkfirst=True)
    postgresql.ENUM(
        "workspace_transfer_ownership",
        name="two_person_approval_action_type",
    ).drop(bind, checkfirst=True)

    op.drop_column("workspaces_settings", "residency_config")
    op.drop_column("workspaces_settings", "dlp_rules")
    op.drop_column("workspaces_settings", "quota_config")
