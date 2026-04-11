"""Connector plugin framework schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "010_connectors"
down_revision = "009_interactions_conversations"
branch_labels = None
depends_on = None


connectors_instance_status = postgresql.ENUM(
    "enabled",
    "disabled",
    name="connectors_instance_status",
    create_type=False,
)
connectors_health_status = postgresql.ENUM(
    "healthy",
    "degraded",
    "unreachable",
    "unknown",
    name="connectors_health_status",
    create_type=False,
)
connectors_delivery_status = postgresql.ENUM(
    "pending",
    "in_flight",
    "delivered",
    "failed",
    "dead_lettered",
    name="connectors_delivery_status",
    create_type=False,
)
connectors_dead_letter_resolution = postgresql.ENUM(
    "pending",
    "redelivered",
    "discarded",
    name="connectors_dead_letter_resolution",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    connectors_instance_status.create(bind, checkfirst=True)
    connectors_health_status.create(bind, checkfirst=True)
    connectors_delivery_status.create(bind, checkfirst=True)
    connectors_dead_letter_resolution.create(bind, checkfirst=True)

    op.create_table(
        "connector_types",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "config_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_deprecated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deprecation_note", sa.Text(), nullable=True),
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
    op.create_index("ix_connector_types_slug", "connector_types", ["slug"], unique=True)

    op.create_table(
        "connector_instances",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            connectors_instance_status,
            nullable=False,
            server_default=sa.text("'enabled'"),
        ),
        sa.Column(
            "health_status",
            connectors_health_status,
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_check_error", sa.Text(), nullable=True),
        sa.Column("messages_sent", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("messages_failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("messages_retried", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "messages_dead_lettered",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_connector_instances_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["connector_type_id"],
            ["connector_types.id"],
            name="fk_connector_instances_connector_type_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_connector_instances_workspace_id",
        "connector_instances",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_connector_instances_status",
        "connector_instances",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_connector_instances_workspace_type",
        "connector_instances",
        ["workspace_id", "connector_type_id"],
        unique=False,
    )
    op.create_index(
        "uq_connector_instances_workspace_name_active",
        "connector_instances",
        ["workspace_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "connector_credential_refs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("connector_instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_key", sa.String(length=255), nullable=False),
        sa.Column("vault_path", sa.String(length=1024), nullable=False),
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
            ["connector_instance_id"],
            ["connector_instances.id"],
            name="fk_connector_credential_refs_instance_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_connector_credential_refs_workspace_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_connector_credential_refs_connector_instance_id",
        "connector_credential_refs",
        ["connector_instance_id"],
        unique=False,
    )
    op.create_index(
        "ix_connector_credential_refs_workspace_id",
        "connector_credential_refs",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "uq_connector_credential_refs_instance_key",
        "connector_credential_refs",
        ["connector_instance_id", "credential_key"],
        unique=True,
    )

    op.create_table(
        "connector_routes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("channel_pattern", sa.String(length=512), nullable=True),
        sa.Column("sender_pattern", sa.String(length=512), nullable=True),
        sa.Column(
            "conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("target_agent_fqn", sa.String(length=512), nullable=True),
        sa.Column("target_workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(target_agent_fqn IS NOT NULL) OR (target_workflow_id IS NOT NULL)",
            name="ck_connector_routes_has_target",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_connector_routes_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["connector_instance_id"],
            ["connector_instances.id"],
            name="fk_connector_routes_connector_instance_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_connector_routes_workspace_id",
        "connector_routes",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_connector_routes_instance_priority",
        "connector_routes",
        ["connector_instance_id", "priority"],
        unique=False,
    )

    op.create_table(
        "outbound_deliveries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("destination", sa.String(length=1024), nullable=False),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column(
            "status",
            connectors_delivery_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "error_history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("source_interaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_outbound_deliveries_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["connector_instance_id"],
            ["connector_instances.id"],
            name="fk_outbound_deliveries_connector_instance_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_outbound_deliveries_workspace_id",
        "outbound_deliveries",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_outbound_deliveries_status",
        "outbound_deliveries",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_outbound_deliveries_status_retry",
        "outbound_deliveries",
        ["status", "next_retry_at"],
        unique=False,
    )
    op.create_index(
        "ix_outbound_deliveries_connector_status",
        "outbound_deliveries",
        ["connector_instance_id", "status"],
        unique=False,
    )

    op.create_table(
        "dead_letter_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outbound_delivery_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "resolution_status",
            connectors_dead_letter_resolution,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("archive_path", sa.String(length=1024), nullable=True),
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
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_dead_letter_entries_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["outbound_delivery_id"],
            ["outbound_deliveries.id"],
            name="fk_dead_letter_entries_outbound_delivery_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["connector_instance_id"],
            ["connector_instances.id"],
            name="fk_dead_letter_entries_connector_instance_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_dead_letter_entries_workspace_id",
        "dead_letter_entries",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "uq_dead_letter_entries_outbound_delivery_id",
        "dead_letter_entries",
        ["outbound_delivery_id"],
        unique=True,
    )
    op.create_index(
        "ix_dead_letter_entries_connector_resolution",
        "dead_letter_entries",
        ["connector_instance_id", "resolution_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_dead_letter_entries_connector_resolution", table_name="dead_letter_entries")
    op.drop_index("uq_dead_letter_entries_outbound_delivery_id", table_name="dead_letter_entries")
    op.drop_index("ix_dead_letter_entries_workspace_id", table_name="dead_letter_entries")
    op.drop_table("dead_letter_entries")

    op.drop_index("ix_outbound_deliveries_connector_status", table_name="outbound_deliveries")
    op.drop_index("ix_outbound_deliveries_status_retry", table_name="outbound_deliveries")
    op.drop_index("ix_outbound_deliveries_status", table_name="outbound_deliveries")
    op.drop_index("ix_outbound_deliveries_workspace_id", table_name="outbound_deliveries")
    op.drop_table("outbound_deliveries")

    op.drop_index("ix_connector_routes_instance_priority", table_name="connector_routes")
    op.drop_index("ix_connector_routes_workspace_id", table_name="connector_routes")
    op.drop_table("connector_routes")

    op.drop_index(
        "uq_connector_credential_refs_instance_key",
        table_name="connector_credential_refs",
    )
    op.drop_index(
        "ix_connector_credential_refs_workspace_id",
        table_name="connector_credential_refs",
    )
    op.drop_index(
        "ix_connector_credential_refs_connector_instance_id",
        table_name="connector_credential_refs",
    )
    op.drop_table("connector_credential_refs")

    op.drop_index(
        "uq_connector_instances_workspace_name_active",
        table_name="connector_instances",
    )
    op.drop_index("ix_connector_instances_workspace_type", table_name="connector_instances")
    op.drop_index("ix_connector_instances_status", table_name="connector_instances")
    op.drop_index("ix_connector_instances_workspace_id", table_name="connector_instances")
    op.drop_table("connector_instances")

    op.drop_index("ix_connector_types_slug", table_name="connector_types")
    op.drop_table("connector_types")

    connectors_dead_letter_resolution.drop(op.get_bind(), checkfirst=True)
    connectors_delivery_status.drop(op.get_bind(), checkfirst=True)
    connectors_health_status.drop(op.get_bind(), checkfirst=True)
    connectors_instance_status.drop(op.get_bind(), checkfirst=True)
