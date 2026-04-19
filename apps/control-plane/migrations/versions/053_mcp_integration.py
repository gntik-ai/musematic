"""Create MCP integration tables and registry references."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "053_mcp_integration"
down_revision = "052_a2a_gateway"
branch_labels = None
depends_on = None

mcp_server_status = postgresql.ENUM(
    "active",
    "suspended",
    "deregistered",
    name="mcp_server_status",
    create_type=False,
)
mcp_invocation_direction = postgresql.ENUM(
    "inbound",
    "outbound",
    name="mcp_invocation_direction",
    create_type=False,
)
mcp_invocation_outcome = postgresql.ENUM(
    "allowed",
    "denied",
    "error_transient",
    "error_permanent",
    name="mcp_invocation_outcome",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    mcp_server_status.create(bind, checkfirst=True)
    mcp_invocation_direction.create(bind, checkfirst=True)
    mcp_invocation_outcome.create(bind, checkfirst=True)

    op.create_table(
        "mcp_server_registrations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("endpoint_url", sa.String(length=2048), nullable=False),
        sa.Column("auth_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", mcp_server_status, nullable=False, server_default=sa.text("'active'")),
        sa.Column("catalog_ttl_seconds", sa.Integer(), nullable=False, server_default=sa.text("3600")),
        sa.Column("last_catalog_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("catalog_version_snapshot", sa.String(length=128), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces_workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "workspace_id",
            "endpoint_url",
            name="uq_mcp_server_registrations_workspace_url",
        ),
    )
    op.create_index("ix_mcp_server_registrations_workspace", "mcp_server_registrations", ["workspace_id"], unique=False)
    op.create_index("ix_mcp_server_registrations_status", "mcp_server_registrations", ["status"], unique=False)

    op.create_table(
        "mcp_exposed_tools",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tool_fqn", sa.String(length=512), nullable=False),
        sa.Column("mcp_tool_name", sa.String(length=128), nullable=False),
        sa.Column("mcp_description", sa.Text(), nullable=False),
        sa.Column("mcp_input_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_exposed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces_workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "tool_fqn", name="uq_mcp_exposed_tools_workspace_tool"),
    )
    op.create_index("ix_mcp_exposed_tools_exposed", "mcp_exposed_tools", ["is_exposed"], unique=False)

    op.create_table(
        "mcp_catalog_cache",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tools_catalog", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("resources_catalog", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("prompts_catalog", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version_snapshot", sa.String(length=128), nullable=True),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_server_registrations.id"], ondelete="CASCADE"),
    )
    op.create_index("uq_mcp_catalog_cache_server", "mcp_catalog_cache", ["server_id"], unique=True)
    op.create_index("ix_mcp_catalog_cache_next_refresh_at", "mcp_catalog_cache", ["next_refresh_at"], unique=False)

    op.create_table(
        "mcp_invocation_audit_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_fqn", sa.String(length=512), nullable=True),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tool_identifier", sa.String(length=512), nullable=False),
        sa.Column("direction", mcp_invocation_direction, nullable=False),
        sa.Column("outcome", mcp_invocation_outcome, nullable=False),
        sa.Column("policy_decision", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("payload_size_bytes", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_classification", sa.String(length=32), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["agent_id"], ["registry_agent_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_server_registrations.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_mcp_invocation_audit_workspace_time", "mcp_invocation_audit_records", ["workspace_id", "timestamp"], unique=False)
    op.create_index("ix_mcp_invocation_audit_agent_time", "mcp_invocation_audit_records", ["agent_id", "timestamp"], unique=False)
    op.create_index("ix_mcp_invocation_audit_server_time", "mcp_invocation_audit_records", ["server_id", "timestamp"], unique=False)
    op.create_index("ix_mcp_invocation_audit_outcome", "mcp_invocation_audit_records", ["outcome"], unique=False)

    op.add_column(
        "registry_agent_profiles",
        sa.Column(
            "mcp_server_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index(
        "ix_registry_agent_profiles_mcp_server_refs",
        "registry_agent_profiles",
        ["mcp_server_refs"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_registry_agent_profiles_mcp_server_refs", table_name="registry_agent_profiles")
    op.drop_column("registry_agent_profiles", "mcp_server_refs")

    op.drop_index("ix_mcp_invocation_audit_outcome", table_name="mcp_invocation_audit_records")
    op.drop_index("ix_mcp_invocation_audit_server_time", table_name="mcp_invocation_audit_records")
    op.drop_index("ix_mcp_invocation_audit_agent_time", table_name="mcp_invocation_audit_records")
    op.drop_index("ix_mcp_invocation_audit_workspace_time", table_name="mcp_invocation_audit_records")
    op.drop_table("mcp_invocation_audit_records")

    op.drop_index("ix_mcp_catalog_cache_next_refresh_at", table_name="mcp_catalog_cache")
    op.drop_index("uq_mcp_catalog_cache_server", table_name="mcp_catalog_cache")
    op.drop_table("mcp_catalog_cache")

    op.drop_index("ix_mcp_exposed_tools_exposed", table_name="mcp_exposed_tools")
    op.drop_table("mcp_exposed_tools")

    op.drop_index("ix_mcp_server_registrations_status", table_name="mcp_server_registrations")
    op.drop_index("ix_mcp_server_registrations_workspace", table_name="mcp_server_registrations")
    op.drop_table("mcp_server_registrations")

    bind = op.get_bind()
    mcp_invocation_outcome.drop(bind, checkfirst=True)
    mcp_invocation_direction.drop(bind, checkfirst=True)
    mcp_server_status.drop(bind, checkfirst=True)
