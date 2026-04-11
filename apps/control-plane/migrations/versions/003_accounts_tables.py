"""Accounts bounded context schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "003_accounts_tables"
down_revision = "002_auth_tables"
branch_labels = None
depends_on = None


accounts_user_status = postgresql.ENUM(
    "pending_verification",
    "pending_approval",
    "active",
    "suspended",
    "blocked",
    "archived",
    name="accounts_user_status",
    create_type=False,
)
accounts_signup_source = postgresql.ENUM(
    "self_registration",
    "invitation",
    name="accounts_signup_source",
    create_type=False,
)
accounts_invitation_status = postgresql.ENUM(
    "pending",
    "consumed",
    "expired",
    "revoked",
    name="accounts_invitation_status",
    create_type=False,
)
accounts_approval_decision = postgresql.ENUM(
    "approved",
    "rejected",
    name="accounts_approval_decision",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    accounts_user_status.create(bind, checkfirst=True)
    accounts_signup_source.create(bind, checkfirst=True)
    accounts_invitation_status.create(bind, checkfirst=True)
    accounts_approval_decision.create(bind, checkfirst=True)

    op.create_table(
        "accounts_invitations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("inviter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invitee_email", sa.String(length=255), nullable=False),
        sa.Column("invitee_message", sa.Text(), nullable=True),
        sa.Column("roles_json", sa.Text(), nullable=False),
        sa.Column("workspace_ids_json", sa.Text(), nullable=True),
        sa.Column(
            "status",
            accounts_invitation_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("token_hash", name="uq_accounts_invitations_token_hash"),
    )
    op.create_index("ix_accounts_invitations_inviter_id", "accounts_invitations", ["inviter_id"], unique=False)
    op.create_index("ix_accounts_invitations_invitee_email", "accounts_invitations", ["invitee_email"], unique=False)

    op.create_table(
        "accounts_users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            accounts_user_status,
            nullable=False,
            server_default=sa.text("'pending_verification'"),
        ),
        sa.Column(
            "signup_source",
            accounts_signup_source,
            nullable=False,
            server_default=sa.text("'self_registration'"),
        ),
        sa.Column("invitation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("suspend_reason", sa.Text(), nullable=True),
        sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("block_reason", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["invitation_id"], ["accounts_invitations.id"], name="fk_accounts_users_invitation_id"),
        sa.UniqueConstraint("email", name="uq_accounts_users_email"),
    )
    op.create_index("ix_accounts_users_status", "accounts_users", ["status"], unique=False)
    op.create_index("ix_accounts_users_created_at", "accounts_users", ["created_at"], unique=False)

    op.create_table(
        "accounts_email_verifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["accounts_users.id"], name="fk_accounts_email_verifications_user_id"),
        sa.UniqueConstraint("token_hash", name="uq_accounts_email_verifications_token_hash"),
    )
    op.create_index("ix_accounts_email_verifications_user_id", "accounts_email_verifications", ["user_id"], unique=False)

    op.create_table(
        "accounts_approval_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision", accounts_approval_decision, nullable=True),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["accounts_users.id"], name="fk_accounts_approval_requests_user_id"),
        sa.UniqueConstraint("user_id", name="uq_accounts_approval_requests_user_id"),
    )
    op.create_index("ix_accounts_approval_requests_user_id", "accounts_approval_requests", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_accounts_approval_requests_user_id", table_name="accounts_approval_requests")
    op.drop_table("accounts_approval_requests")

    op.drop_index("ix_accounts_email_verifications_user_id", table_name="accounts_email_verifications")
    op.drop_table("accounts_email_verifications")

    op.drop_index("ix_accounts_users_created_at", table_name="accounts_users")
    op.drop_index("ix_accounts_users_status", table_name="accounts_users")
    op.drop_table("accounts_users")

    op.drop_index("ix_accounts_invitations_invitee_email", table_name="accounts_invitations")
    op.drop_index("ix_accounts_invitations_inviter_id", table_name="accounts_invitations")
    op.drop_table("accounts_invitations")

    bind = op.get_bind()
    accounts_approval_decision.drop(bind, checkfirst=True)
    accounts_invitation_status.drop(bind, checkfirst=True)
    accounts_signup_source.drop(bind, checkfirst=True)
    accounts_user_status.drop(bind, checkfirst=True)
