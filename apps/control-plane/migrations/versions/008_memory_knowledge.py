"""Memory and knowledge subsystem schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "008_memory_knowledge"
down_revision = "007_context_engineering"
branch_labels = None
depends_on = None


memory_scope = postgresql.ENUM(
    "per_agent",
    "per_workspace",
    "shared_orchestrator",
    name="memory_scope",
    create_type=False,
)
memory_retention_policy = postgresql.ENUM(
    "permanent",
    "time_limited",
    "session_only",
    name="memory_retention_policy",
    create_type=False,
)
memory_embedding_status = postgresql.ENUM(
    "pending",
    "completed",
    "failed",
    name="memory_embedding_status",
    create_type=False,
)
memory_conflict_status = postgresql.ENUM(
    "open",
    "dismissed",
    "resolved",
    name="memory_conflict_status",
    create_type=False,
)
memory_embedding_job_status = postgresql.ENUM(
    "pending",
    "processing",
    "completed",
    "failed",
    name="memory_embedding_job_status",
    create_type=False,
)
memory_pattern_status = postgresql.ENUM(
    "pending",
    "approved",
    "rejected",
    name="memory_pattern_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    memory_scope.create(bind, checkfirst=True)
    memory_retention_policy.create(bind, checkfirst=True)
    memory_embedding_status.create(bind, checkfirst=True)
    memory_conflict_status.create(bind, checkfirst=True)
    memory_embedding_job_status.create(bind, checkfirst=True)
    memory_pattern_status.create(bind, checkfirst=True)

    op.create_table(
        "memory_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=255), nullable=False),
        sa.Column("namespace", sa.String(length=255), nullable=False),
        sa.Column("scope", memory_scope, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "content_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', coalesce(content, ''))", persisted=True),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_authority", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column(
            "retention_policy",
            memory_retention_policy,
            nullable=False,
            server_default=sa.text("'permanent'"),
        ),
        sa.Column("ttl_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "embedding_status",
            memory_embedding_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("qdrant_point_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provenance_consolidated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
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
            name="fk_memory_entries_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_consolidated_by"],
            ["memory_entries.id"],
            name="fk_memory_entries_provenance_consolidated_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_memory_entries_workspace_id",
        "memory_entries",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_entries_agent_fqn",
        "memory_entries",
        ["agent_fqn"],
        unique=False,
    )
    op.create_index(
        "ix_memory_entries_scope",
        "memory_entries",
        ["scope"],
        unique=False,
    )
    op.create_index(
        "ix_memory_entries_workspace_scope",
        "memory_entries",
        ["workspace_id", "scope"],
        unique=False,
    )
    op.create_index(
        "ix_memory_entries_agent_scope",
        "memory_entries",
        ["agent_fqn", "scope"],
        unique=False,
    )
    op.create_index(
        "ix_memory_entries_content_tsv",
        "memory_entries",
        ["content_tsv"],
        unique=False,
        postgresql_using="gin",
    )

    op.create_table(
        "evidence_conflicts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_entry_id_a", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_entry_id_b", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conflict_description", sa.Text(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column(
            "status",
            memory_conflict_status,
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
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
            name="fk_evidence_conflicts_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["memory_entry_id_a"],
            ["memory_entries.id"],
            name="fk_evidence_conflicts_memory_entry_id_a",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["memory_entry_id_b"],
            ["memory_entries.id"],
            name="fk_evidence_conflicts_memory_entry_id_b",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_evidence_conflicts_workspace_id",
        "evidence_conflicts",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_conflicts_status",
        "evidence_conflicts",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_conflicts_pair",
        "evidence_conflicts",
        ["memory_entry_id_a", "memory_entry_id_b"],
        unique=True,
    )

    op.create_table(
        "embedding_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("memory_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            memory_embedding_job_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["memory_entry_id"],
            ["memory_entries.id"],
            name="fk_embedding_jobs_memory_entry_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("memory_entry_id", name="uq_embedding_jobs_memory_entry_id"),
    )
    op.create_index(
        "ix_embedding_jobs_status",
        "embedding_jobs",
        ["status"],
        unique=False,
    )

    op.create_table(
        "trajectory_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=255), nullable=False),
        sa.Column(
            "actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "tool_invocations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "reasoning_snapshots",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "verdicts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            name="fk_trajectory_records_workspace_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("execution_id", name="uq_trajectory_records_execution_id"),
    )
    op.create_index(
        "ix_trajectory_records_workspace_id",
        "trajectory_records",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_trajectory_records_execution_id",
        "trajectory_records",
        ["execution_id"],
        unique=False,
    )
    op.create_index(
        "ix_trajectory_records_agent_fqn",
        "trajectory_records",
        ["agent_fqn"],
        unique=False,
    )
    op.create_index(
        "ix_trajectory_records_workspace_agent",
        "trajectory_records",
        ["workspace_id", "agent_fqn"],
        unique=False,
    )

    op.create_table(
        "pattern_assets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trajectory_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("nominated_by", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "status",
            memory_pattern_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("memory_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            name="fk_pattern_assets_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trajectory_record_id"],
            ["trajectory_records.id"],
            name="fk_pattern_assets_trajectory_record_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["memory_entry_id"],
            ["memory_entries.id"],
            name="fk_pattern_assets_memory_entry_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_pattern_assets_workspace_id",
        "pattern_assets",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_pattern_assets_status",
        "pattern_assets",
        ["status"],
        unique=False,
    )

    op.create_table(
        "knowledge_nodes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("neo4j_element_id", sa.String(length=255), nullable=False),
        sa.Column("node_type", sa.String(length=100), nullable=False),
        sa.Column("external_name", sa.String(length=500), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by_fqn", sa.String(length=255), nullable=False),
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
            name="fk_knowledge_nodes_workspace_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_knowledge_nodes_workspace_id",
        "knowledge_nodes",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_nodes_workspace_type",
        "knowledge_nodes",
        ["workspace_id", "node_type"],
        unique=False,
    )
    op.create_index(
        "uq_knowledge_nodes_workspace_neo4j_element_id",
        "knowledge_nodes",
        ["workspace_id", "neo4j_element_id"],
        unique=True,
    )

    op.create_table(
        "knowledge_edges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("neo4j_element_id", sa.String(length=255), nullable=False),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(length=100), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_knowledge_edges_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id"],
            ["knowledge_nodes.id"],
            name="fk_knowledge_edges_source_node_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"],
            ["knowledge_nodes.id"],
            name="fk_knowledge_edges_target_node_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_knowledge_edges_workspace_id",
        "knowledge_edges",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_edges_source_target",
        "knowledge_edges",
        ["source_node_id", "target_node_id"],
        unique=False,
    )
    op.create_index(
        "uq_knowledge_edges_workspace_neo4j_element_id",
        "knowledge_edges",
        ["workspace_id", "neo4j_element_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_knowledge_edges_workspace_neo4j_element_id", table_name="knowledge_edges")
    op.drop_index("ix_knowledge_edges_source_target", table_name="knowledge_edges")
    op.drop_index("ix_knowledge_edges_workspace_id", table_name="knowledge_edges")
    op.drop_table("knowledge_edges")

    op.drop_index("uq_knowledge_nodes_workspace_neo4j_element_id", table_name="knowledge_nodes")
    op.drop_index("ix_knowledge_nodes_workspace_type", table_name="knowledge_nodes")
    op.drop_index("ix_knowledge_nodes_workspace_id", table_name="knowledge_nodes")
    op.drop_table("knowledge_nodes")

    op.drop_index("ix_pattern_assets_status", table_name="pattern_assets")
    op.drop_index("ix_pattern_assets_workspace_id", table_name="pattern_assets")
    op.drop_table("pattern_assets")

    op.drop_index("ix_trajectory_records_workspace_agent", table_name="trajectory_records")
    op.drop_index("ix_trajectory_records_agent_fqn", table_name="trajectory_records")
    op.drop_index("ix_trajectory_records_execution_id", table_name="trajectory_records")
    op.drop_index("ix_trajectory_records_workspace_id", table_name="trajectory_records")
    op.drop_table("trajectory_records")

    op.drop_index("ix_embedding_jobs_status", table_name="embedding_jobs")
    op.drop_table("embedding_jobs")

    op.drop_index("ix_evidence_conflicts_pair", table_name="evidence_conflicts")
    op.drop_index("ix_evidence_conflicts_status", table_name="evidence_conflicts")
    op.drop_index("ix_evidence_conflicts_workspace_id", table_name="evidence_conflicts")
    op.drop_table("evidence_conflicts")

    op.drop_index("ix_memory_entries_content_tsv", table_name="memory_entries")
    op.drop_index("ix_memory_entries_agent_scope", table_name="memory_entries")
    op.drop_index("ix_memory_entries_workspace_scope", table_name="memory_entries")
    op.drop_index("ix_memory_entries_scope", table_name="memory_entries")
    op.drop_index("ix_memory_entries_agent_fqn", table_name="memory_entries")
    op.drop_index("ix_memory_entries_workspace_id", table_name="memory_entries")
    op.drop_table("memory_entries")

    bind = op.get_bind()
    memory_pattern_status.drop(bind, checkfirst=True)
    memory_embedding_job_status.drop(bind, checkfirst=True)
    memory_conflict_status.drop(bind, checkfirst=True)
    memory_embedding_status.drop(bind, checkfirst=True)
    memory_retention_policy.drop(bind, checkfirst=True)
    memory_scope.drop(bind, checkfirst=True)
