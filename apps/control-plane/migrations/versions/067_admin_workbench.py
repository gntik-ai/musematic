"""Administrator workbench and super-admin bootstrap.

Revision ID: 067_admin_workbench
Revises: 066_localization
Create Date: 2026-04-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "067_admin_workbench"
down_revision: str | None = "066_localization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk(name: str = "id") -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _ts(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=None if nullable else sa.text("now()"),
    )


def upgrade() -> None:
    op.create_table(
        "two_person_auth_requests",
        _uuid_pk("request_id"),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("initiator_id", postgresql.UUID(as_uuid=True), nullable=False),
        _ts("created_at"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["initiator_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rejected_by_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_two_person_auth_requests_unconsumed_request",
        "two_person_auth_requests",
        ["request_id"],
        unique=True,
        postgresql_where=sa.text("consumed IS FALSE"),
    )
    op.create_index(
        "ix_two_person_auth_requests_pending",
        "two_person_auth_requests",
        ["expires_at"],
        postgresql_where=sa.text(
            "approved_at IS NULL AND rejected_at IS NULL AND consumed IS FALSE"
        ),
    )

    op.create_table(
        "impersonation_sessions",
        _uuid_pk("session_id"),
        sa.Column("impersonating_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effective_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        _ts("started_at"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["impersonating_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["effective_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_impersonation_sessions_active_admin",
        "impersonation_sessions",
        ["impersonating_user_id", "expires_at"],
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_index(
        "ix_impersonation_sessions_effective_user",
        "impersonation_sessions",
        ["effective_user_id", "started_at"],
    )

    op.add_column("users", sa.Column("username", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("mfa_pending", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column(
            "mfa_required_before_login",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "force_password_change",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "first_install_checklist_state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_index(
        "uq_users_username_active",
        "users",
        ["username"],
        unique=True,
        postgresql_where=sa.text("username IS NOT NULL AND deleted_at IS NULL"),
    )

    op.add_column(
        "sessions",
        sa.Column(
            "admin_read_only_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.add_column(
        "audit_chain_entries",
        sa.Column("event_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "audit_chain_entries",
        sa.Column("actor_role", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "audit_chain_entries",
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="info"),
    )
    op.add_column(
        "audit_chain_entries",
        sa.Column("canonical_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "audit_chain_entries",
        sa.Column("impersonation_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_audit_chain_entries_impersonation_user_id_users",
        "audit_chain_entries",
        "users",
        ["impersonation_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        CREATE INDEX audit_chain_entries_actor_role_created_at_idx
        ON audit_chain_entries (actor_role, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_audit_chain_entries_event_type_created_at
        ON audit_chain_entries (event_type, created_at DESC)
        """
    )

    op.create_table(
        "platform_settings",
        _uuid_pk(),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("scope", sa.String(length=32), nullable=False, server_default="global"),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "scope IN ('global','tenant','workspace','user')",
            name="ck_platform_settings_scope",
        ),
    )
    op.create_index(
        "uq_platform_settings_global_key",
        "platform_settings",
        ["key", "scope"],
        unique=True,
        postgresql_where=sa.text("scope_id IS NULL"),
    )
    op.create_index(
        "uq_platform_settings_scoped_key",
        "platform_settings",
        ["key", "scope", "scope_id"],
        unique=True,
        postgresql_where=sa.text("scope_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_platform_settings_scoped_key", table_name="platform_settings")
    op.drop_index("uq_platform_settings_global_key", table_name="platform_settings")
    op.drop_table("platform_settings")

    op.drop_index("ix_audit_chain_entries_event_type_created_at", table_name="audit_chain_entries")
    op.drop_index("audit_chain_entries_actor_role_created_at_idx", table_name="audit_chain_entries")
    op.drop_constraint(
        "fk_audit_chain_entries_impersonation_user_id_users",
        "audit_chain_entries",
        type_="foreignkey",
    )
    op.drop_column("audit_chain_entries", "impersonation_user_id")
    op.drop_column("audit_chain_entries", "canonical_payload")
    op.drop_column("audit_chain_entries", "severity")
    op.drop_column("audit_chain_entries", "actor_role")
    op.drop_column("audit_chain_entries", "event_type")

    op.drop_column("sessions", "admin_read_only_mode")

    op.drop_index("uq_users_username_active", table_name="users")
    op.drop_column("users", "first_install_checklist_state")
    op.drop_column("users", "force_password_change")
    op.drop_column("users", "mfa_required_before_login")
    op.drop_column("users", "mfa_pending")
    op.drop_column("users", "username")

    op.drop_index("ix_impersonation_sessions_effective_user", table_name="impersonation_sessions")
    op.drop_index("ix_impersonation_sessions_active_admin", table_name="impersonation_sessions")
    op.drop_table("impersonation_sessions")

    op.drop_index(
        "ix_two_person_auth_requests_pending",
        table_name="two_person_auth_requests",
    )
    op.drop_index(
        "uq_two_person_auth_requests_unconsumed_request",
        table_name="two_person_auth_requests",
    )
    op.drop_table("two_person_auth_requests")
