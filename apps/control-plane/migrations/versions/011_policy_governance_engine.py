"""Policy and governance engine schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "011_policy_governance_engine"
down_revision = "010_connectors"
branch_labels = None
depends_on = None


policy_scope_type = postgresql.ENUM(
    "global",
    "deployment",
    "workspace",
    "agent",
    "execution",
    name="policy_scope_type",
    create_type=False,
)
policy_status = postgresql.ENUM(
    "active",
    "archived",
    name="policy_status",
    create_type=False,
)
policy_attachment_target_type = postgresql.ENUM(
    "global",
    "deployment",
    "workspace",
    "agent_revision",
    "fleet",
    "execution",
    name="policy_attachment_target_type",
    create_type=False,
)
policy_enforcement_component = postgresql.ENUM(
    "tool_gateway",
    "memory_write_gate",
    "sanitizer",
    "visibility_filter",
    name="policy_enforcement_component",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    policy_scope_type.create(bind, checkfirst=True)
    policy_status.create(bind, checkfirst=True)
    policy_attachment_target_type.create(bind, checkfirst=True)
    policy_enforcement_component.create(bind, checkfirst=True)

    op.create_table(
        "policy_policies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope_type", policy_scope_type, nullable=False),
        sa.Column(
            "status",
            policy_status,
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
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
    )
    op.create_index("ix_policy_policies_name", "policy_policies", ["name"], unique=False)
    op.create_index(
        "ix_policy_policies_scope_type",
        "policy_policies",
        ["scope_type"],
        unique=False,
    )
    op.create_index("ix_policy_policies_status", "policy_policies", ["status"], unique=False)
    op.create_index(
        "ix_policy_policies_workspace_id",
        "policy_policies",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "policy_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "rules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["policy_policies.id"],
            name="fk_policy_versions_policy_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_policy_versions_policy_id",
        "policy_versions",
        ["policy_id"],
        unique=False,
    )
    op.create_index(
        "uq_policy_versions_policy_version",
        "policy_versions",
        ["policy_id", "version_number"],
        unique=True,
    )

    op.create_foreign_key(
        "fk_policy_policies_current_version_id",
        "policy_policies",
        "policy_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "policy_attachments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", policy_attachment_target_type, nullable=False),
        sa.Column("target_id", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["policy_policies.id"],
            name="fk_policy_attachments_policy_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["policy_version_id"],
            ["policy_versions.id"],
            name="fk_policy_attachments_policy_version_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_policy_attachments_policy_id",
        "policy_attachments",
        ["policy_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_attachments_target_type",
        "policy_attachments",
        ["target_type"],
        unique=False,
    )
    op.create_index(
        "ix_policy_attachments_is_active",
        "policy_attachments",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        "ix_policy_attachments_target_lookup",
        "policy_attachments",
        ["target_type", "target_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "policy_blocked_action_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("enforcement_component", policy_enforcement_component, nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=512), nullable=False),
        sa.Column("block_reason", sa.String(length=255), nullable=False),
        sa.Column(
            "policy_rule_ref",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
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
    )
    op.create_index(
        "ix_policy_blocked_action_records_agent_id",
        "policy_blocked_action_records",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_blocked_action_records_component",
        "policy_blocked_action_records",
        ["enforcement_component"],
        unique=False,
    )
    op.create_index(
        "ix_policy_blocked_action_records_execution_id",
        "policy_blocked_action_records",
        ["execution_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_blocked_action_records_workspace_id",
        "policy_blocked_action_records",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "policy_bundle_cache",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "bundle_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "source_version_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
    )
    op.create_index(
        "ix_policy_bundle_cache_fingerprint",
        "policy_bundle_cache",
        ["fingerprint"],
        unique=True,
    )
    op.create_index(
        "ix_policy_bundle_cache_expires_at",
        "policy_bundle_cache",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_policy_bundle_cache_expires_at", table_name="policy_bundle_cache")
    op.drop_index("ix_policy_bundle_cache_fingerprint", table_name="policy_bundle_cache")
    op.drop_table("policy_bundle_cache")

    op.drop_index(
        "ix_policy_blocked_action_records_workspace_id",
        table_name="policy_blocked_action_records",
    )
    op.drop_index(
        "ix_policy_blocked_action_records_execution_id",
        table_name="policy_blocked_action_records",
    )
    op.drop_index(
        "ix_policy_blocked_action_records_component",
        table_name="policy_blocked_action_records",
    )
    op.drop_index(
        "ix_policy_blocked_action_records_agent_id",
        table_name="policy_blocked_action_records",
    )
    op.drop_table("policy_blocked_action_records")

    op.drop_index("ix_policy_attachments_target_lookup", table_name="policy_attachments")
    op.drop_index("ix_policy_attachments_is_active", table_name="policy_attachments")
    op.drop_index("ix_policy_attachments_target_type", table_name="policy_attachments")
    op.drop_index("ix_policy_attachments_policy_id", table_name="policy_attachments")
    op.drop_table("policy_attachments")

    op.drop_constraint(
        "fk_policy_policies_current_version_id",
        "policy_policies",
        type_="foreignkey",
    )
    op.drop_index("uq_policy_versions_policy_version", table_name="policy_versions")
    op.drop_index("ix_policy_versions_policy_id", table_name="policy_versions")
    op.drop_table("policy_versions")

    op.drop_index("ix_policy_policies_workspace_id", table_name="policy_policies")
    op.drop_index("ix_policy_policies_status", table_name="policy_policies")
    op.drop_index("ix_policy_policies_scope_type", table_name="policy_policies")
    op.drop_index("ix_policy_policies_name", table_name="policy_policies")
    op.drop_table("policy_policies")

    bind = op.get_bind()
    policy_enforcement_component.drop(bind, checkfirst=True)
    policy_attachment_target_type.drop(bind, checkfirst=True)
    policy_status.drop(bind, checkfirst=True)
    policy_scope_type.drop(bind, checkfirst=True)
