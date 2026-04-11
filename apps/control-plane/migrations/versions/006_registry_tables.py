"""Registry bounded context schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "006_registry_tables"
down_revision = "005_analytics_cost_models"
branch_labels = None
depends_on = None


registry_lifecycle_status = postgresql.ENUM(
    "draft",
    "validated",
    "published",
    "disabled",
    "deprecated",
    "archived",
    name="registry_lifecycle_status",
    create_type=False,
)
registry_embedding_status = postgresql.ENUM(
    "pending",
    "complete",
    "failed",
    name="registry_embedding_status",
    create_type=False,
)
registry_assessment_method = postgresql.ENUM(
    "manifest_declared",
    "system_assessed",
    name="registry_assessment_method",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    registry_lifecycle_status.create(bind, checkfirst=True)
    registry_embedding_status.create(bind, checkfirst=True)
    registry_assessment_method.create(bind, checkfirst=True)

    op.create_table(
        "registry_namespaces",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "name", name="uq_registry_ns_workspace_name"),
    )
    op.create_index("ix_registry_namespaces_workspace_id", "registry_namespaces", ["workspace_id"], unique=False)

    op.create_table(
        "registry_agent_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("namespace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("local_name", sa.String(length=63), nullable=False),
        sa.Column("fqn", sa.String(length=127), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("approach", sa.Text(), nullable=True),
        sa.Column(
            "role_types",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("custom_role_description", sa.Text(), nullable=True),
        sa.Column(
            "visibility_agents",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "visibility_tools",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "status",
            registry_lifecycle_status,
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("maturity_level", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "embedding_status",
            registry_embedding_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("needs_reindex", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["namespace_id"],
            ["registry_namespaces.id"],
            name="fk_registry_agent_profiles_namespace_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("namespace_id", "local_name", name="uq_registry_profile_ns_local"),
        sa.UniqueConstraint("fqn", name="uq_registry_profile_fqn"),
    )
    op.create_index(
        "ix_registry_profile_workspace_status",
        "registry_agent_profiles",
        ["workspace_id", "status"],
        unique=False,
    )
    op.create_index("ix_registry_profile_fqn", "registry_agent_profiles", ["fqn"], unique=False)
    op.create_index(
        "ix_registry_profile_needs_reindex",
        "registry_agent_profiles",
        ["needs_reindex"],
        unique=False,
    )

    op.create_table(
        "registry_agent_revisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("sha256_digest", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("manifest_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["agent_profile_id"],
            ["registry_agent_profiles.id"],
            name="fk_registry_agent_revisions_profile_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("agent_profile_id", "version", name="uq_registry_revision_profile_version"),
    )
    op.create_index(
        "ix_registry_revision_profile_id",
        "registry_agent_revisions",
        ["agent_profile_id"],
        unique=False,
    )

    op.create_table(
        "registry_maturity_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_level", sa.Integer(), nullable=False),
        sa.Column("new_level", sa.Integer(), nullable=False),
        sa.Column("assessment_method", registry_assessment_method, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["agent_profile_id"],
            ["registry_agent_profiles.id"],
            name="fk_registry_maturity_records_profile_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_registry_maturity_records_workspace_id",
        "registry_maturity_records",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_registry_maturity_records_profile_id",
        "registry_maturity_records",
        ["agent_profile_id"],
        unique=False,
    )

    op.create_table(
        "registry_lifecycle_audit",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_status", registry_lifecycle_status, nullable=False),
        sa.Column("new_status", registry_lifecycle_status, nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["agent_profile_id"],
            ["registry_agent_profiles.id"],
            name="fk_registry_lifecycle_audit_profile_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_registry_lifecycle_audit_profile",
        "registry_lifecycle_audit",
        ["agent_profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_registry_lifecycle_audit_workspace_id",
        "registry_lifecycle_audit",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_registry_lifecycle_audit_workspace_id", table_name="registry_lifecycle_audit")
    op.drop_index("ix_registry_lifecycle_audit_profile", table_name="registry_lifecycle_audit")
    op.drop_table("registry_lifecycle_audit")

    op.drop_index("ix_registry_maturity_records_profile_id", table_name="registry_maturity_records")
    op.drop_index("ix_registry_maturity_records_workspace_id", table_name="registry_maturity_records")
    op.drop_table("registry_maturity_records")

    op.drop_index("ix_registry_revision_profile_id", table_name="registry_agent_revisions")
    op.drop_table("registry_agent_revisions")

    op.drop_index("ix_registry_profile_needs_reindex", table_name="registry_agent_profiles")
    op.drop_index("ix_registry_profile_fqn", table_name="registry_agent_profiles")
    op.drop_index("ix_registry_profile_workspace_status", table_name="registry_agent_profiles")
    op.drop_table("registry_agent_profiles")

    op.drop_index("ix_registry_namespaces_workspace_id", table_name="registry_namespaces")
    op.drop_table("registry_namespaces")

    bind = op.get_bind()
    registry_assessment_method.drop(bind, checkfirst=True)
    registry_embedding_status.drop(bind, checkfirst=True)
    registry_lifecycle_status.drop(bind, checkfirst=True)
