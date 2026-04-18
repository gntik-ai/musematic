"""Add IBOR connector tables and registry decommission support.

Downgrade intentionally leaves the `decommissioned` value in
`registry_lifecycle_status` because PostgreSQL cannot drop enum values safely.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "044_ibor_and_decommission"
down_revision = "043_runtime_warm_pool_targets"
branch_labels = None
depends_on = None


auth_ibor_source_type = postgresql.ENUM(
    "ldap",
    "oidc",
    "scim",
    name="auth_ibor_source_type",
    create_type=False,
)
auth_ibor_sync_mode = postgresql.ENUM(
    "pull",
    "push",
    name="auth_ibor_sync_mode",
    create_type=False,
)
auth_ibor_sync_run_status = postgresql.ENUM(
    "running",
    "succeeded",
    "partial_success",
    "failed",
    name="auth_ibor_sync_run_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("ALTER TYPE registry_lifecycle_status ADD VALUE IF NOT EXISTS 'decommissioned'")

    auth_ibor_source_type.create(bind, checkfirst=True)
    auth_ibor_sync_mode.create(bind, checkfirst=True)
    auth_ibor_sync_run_status.create(bind, checkfirst=True)

    op.add_column(
        "registry_agent_profiles",
        sa.Column("decommissioned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "registry_agent_profiles",
        sa.Column("decommission_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "registry_agent_profiles",
        sa.Column("decommissioned_by", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.drop_constraint(
        "uq_registry_profile_ns_local",
        "registry_agent_profiles",
        type_="unique",
    )
    op.drop_constraint(
        "uq_registry_profile_fqn",
        "registry_agent_profiles",
        type_="unique",
    )
    op.create_index(
        "uq_registry_profile_ns_local_active",
        "registry_agent_profiles",
        ["namespace_id", "local_name"],
        unique=True,
        postgresql_where=sa.text("decommissioned_at IS NULL"),
    )
    op.create_index(
        "uq_registry_profile_fqn_active",
        "registry_agent_profiles",
        ["fqn"],
        unique=True,
        postgresql_where=sa.text("decommissioned_at IS NULL"),
    )

    op.create_table(
        "ibor_connectors",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", auth_ibor_source_type, nullable=False),
        sa.Column("sync_mode", auth_ibor_sync_mode, nullable=False),
        sa.Column(
            "cadence_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3600"),
        ),
        sa.Column("credential_ref", sa.String(length=255), nullable=False),
        sa.Column(
            "role_mapping_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", auth_ibor_sync_run_status, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_ibor_connectors_name"),
    )

    op.create_table(
        "ibor_sync_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("connector_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", auth_ibor_sync_mode, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", auth_ibor_sync_run_status, nullable=False),
        sa.Column(
            "counts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "error_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["connector_id"],
            ["ibor_connectors.id"],
            name="fk_ibor_sync_runs_connector_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ibor_sync_runs_connector_started",
        "ibor_sync_runs",
        ["connector_id", "started_at"],
        unique=False,
    )

    op.add_column(
        "user_roles",
        sa.Column("source_connector_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_user_roles_source_connector",
        "user_roles",
        ["source_connector_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_roles_source_connector", table_name="user_roles")
    op.drop_column("user_roles", "source_connector_id")

    op.drop_index("ix_ibor_sync_runs_connector_started", table_name="ibor_sync_runs")
    op.drop_table("ibor_sync_runs")
    op.drop_table("ibor_connectors")

    op.drop_index("uq_registry_profile_fqn_active", table_name="registry_agent_profiles")
    op.drop_index("uq_registry_profile_ns_local_active", table_name="registry_agent_profiles")
    op.create_unique_constraint(
        "uq_registry_profile_ns_local",
        "registry_agent_profiles",
        ["namespace_id", "local_name"],
    )
    op.create_unique_constraint(
        "uq_registry_profile_fqn",
        "registry_agent_profiles",
        ["fqn"],
    )

    op.drop_column("registry_agent_profiles", "decommissioned_by")
    op.drop_column("registry_agent_profiles", "decommission_reason")
    op.drop_column("registry_agent_profiles", "decommissioned_at")

    bind = op.get_bind()
    auth_ibor_sync_run_status.drop(bind, checkfirst=True)
    auth_ibor_sync_mode.drop(bind, checkfirst=True)
    auth_ibor_source_type.drop(bind, checkfirst=True)
