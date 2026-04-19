"""Agent contracts and certification enhancements."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "049_agent_contracts_and_certs"
down_revision = "048_governance_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE trust_certification_status "
        "ADD VALUE IF NOT EXISTS 'expiring' BEFORE 'expired'"
    )
    op.execute("ALTER TYPE trust_certification_status ADD VALUE IF NOT EXISTS 'suspended'")

    op.create_table(
        "certifiers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("organization", sa.String(length=256), nullable=True),
        sa.Column("credentials", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("permitted_scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_certifiers_name", "certifiers", ["name"], unique=False)

    op.create_table(
        "agent_contracts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(length=512), nullable=False),
        sa.Column("task_scope", sa.Text(), nullable=False),
        sa.Column("expected_outputs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("quality_thresholds", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("time_constraint_seconds", sa.Integer(), nullable=True),
        sa.Column("cost_limit_tokens", sa.Integer(), nullable=True),
        sa.Column("escalation_conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("success_criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "enforcement_policy",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'warn'"),
        ),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_agent_contracts_workspace_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_agent_contracts_workspace_id",
        "agent_contracts",
        ["workspace_id"],
        unique=False,
    )
    op.create_index("ix_agent_contracts_agent_id", "agent_contracts", ["agent_id"], unique=False)
    op.create_index(
        "ix_agent_contracts_workspace_agent",
        "agent_contracts",
        ["workspace_id", "agent_id"],
        unique=False,
    )

    op.create_table(
        "contract_breach_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
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
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("breached_term", sa.String(length=64), nullable=False),
        sa.Column("observed_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("threshold_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enforcement_action", sa.String(length=32), nullable=False),
        sa.Column("enforcement_outcome", sa.String(length=32), nullable=False),
        sa.Column("contract_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["agent_contracts.id"],
            name="fk_contract_breach_events_contract_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_contract_breach_events_contract_id",
        "contract_breach_events",
        ["contract_id"],
        unique=False,
    )
    op.create_index(
        "ix_contract_breach_events_target",
        "contract_breach_events",
        ["target_type", "target_id"],
        unique=False,
    )
    op.create_index(
        "ix_contract_breach_events_created_at",
        "contract_breach_events",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "reassessment_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("certification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("reassessor_id", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["certification_id"],
            ["trust_certifications.id"],
            name="fk_reassessment_records_certification_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_reassessment_records_certification_id",
        "reassessment_records",
        ["certification_id"],
        unique=False,
    )

    op.create_table(
        "trust_recertification_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
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
        sa.Column("certification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("trigger_reference", sa.Text(), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolution_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("dismissal_justification", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["certification_id"],
            ["trust_certifications.id"],
            name="fk_trust_recertification_requests_certification_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_trust_recertification_requests_certification_id",
        "trust_recertification_requests",
        ["certification_id"],
        unique=False,
    )
    op.create_index(
        "ix_trust_recertification_requests_deadline",
        "trust_recertification_requests",
        ["deadline"],
        unique=False,
        postgresql_where=sa.text("resolution_status = 'pending'"),
    )

    op.add_column(
        "trust_certifications",
        sa.Column("external_certifier_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "trust_certifications",
        sa.Column("reassessment_schedule", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_trust_certifications_external_certifier_id",
        "trust_certifications",
        "certifiers",
        ["external_certifier_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "interactions",
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "interactions",
        sa.Column("contract_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        "fk_interactions_contract_id",
        "interactions",
        "agent_contracts",
        ["contract_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_interactions_contract_id",
        "interactions",
        ["contract_id"],
        unique=False,
        postgresql_where=sa.text("contract_id IS NOT NULL"),
    )

    op.add_column(
        "executions",
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "executions",
        sa.Column("contract_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        "fk_executions_contract_id",
        "executions",
        "agent_contracts",
        ["contract_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_executions_contract_id",
        "executions",
        ["contract_id"],
        unique=False,
        postgresql_where=sa.text("contract_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_executions_contract_id", table_name="executions")
    op.drop_constraint("fk_executions_contract_id", "executions", type_="foreignkey")
    op.drop_column("executions", "contract_snapshot")
    op.drop_column("executions", "contract_id")

    op.drop_index("ix_interactions_contract_id", table_name="interactions")
    op.drop_constraint("fk_interactions_contract_id", "interactions", type_="foreignkey")
    op.drop_column("interactions", "contract_snapshot")
    op.drop_column("interactions", "contract_id")

    op.drop_constraint(
        "fk_trust_certifications_external_certifier_id",
        "trust_certifications",
        type_="foreignkey",
    )
    op.drop_column("trust_certifications", "reassessment_schedule")
    op.drop_column("trust_certifications", "external_certifier_id")

    op.drop_index(
        "ix_trust_recertification_requests_deadline",
        table_name="trust_recertification_requests",
    )
    op.drop_index(
        "ix_trust_recertification_requests_certification_id",
        table_name="trust_recertification_requests",
    )
    op.drop_table("trust_recertification_requests")

    op.drop_index("ix_reassessment_records_certification_id", table_name="reassessment_records")
    op.drop_table("reassessment_records")

    op.drop_index("ix_contract_breach_events_created_at", table_name="contract_breach_events")
    op.drop_index("ix_contract_breach_events_target", table_name="contract_breach_events")
    op.drop_index("ix_contract_breach_events_contract_id", table_name="contract_breach_events")
    op.drop_table("contract_breach_events")

    op.drop_index("ix_agent_contracts_workspace_agent", table_name="agent_contracts")
    op.drop_index("ix_agent_contracts_agent_id", table_name="agent_contracts")
    op.drop_index("ix_agent_contracts_workspace_id", table_name="agent_contracts")
    op.drop_table("agent_contracts")

    op.drop_index("ix_certifiers_name", table_name="certifiers")
    op.drop_table("certifiers")

    op.execute("UPDATE trust_certifications SET status = 'active' WHERE status = 'expiring'")
    op.execute("UPDATE trust_certifications SET status = 'revoked' WHERE status = 'suspended'")
    op.execute("ALTER TABLE trust_certifications ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE trust_certification_status RENAME TO trust_certification_status_old")
    old_status = postgresql.ENUM(
        "pending",
        "active",
        "expired",
        "revoked",
        "superseded",
        name="trust_certification_status",
    )
    old_status.create(op.get_bind(), checkfirst=False)
    op.execute(
        "ALTER TABLE trust_certifications ALTER COLUMN status TYPE trust_certification_status "
        "USING status::text::trust_certification_status"
    )
    op.execute(
        "ALTER TABLE trust_certifications ALTER COLUMN status SET DEFAULT 'pending'"
    )
    op.execute("DROP TYPE trust_certification_status_old")
