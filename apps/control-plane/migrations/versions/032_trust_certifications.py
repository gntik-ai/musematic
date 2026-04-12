"""Trust certifications, guardrails, and trust signals schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "032_trust_certifications"
down_revision = "013_marketplace_schema"
branch_labels = None
depends_on = None


trust_certification_status = postgresql.ENUM(
    "pending",
    "active",
    "expired",
    "revoked",
    "superseded",
    name="trust_certification_status",
    create_type=False,
)
trust_evidence_type = postgresql.ENUM(
    "package_validation",
    "test_results",
    "policy_check",
    "guardrail_outcomes",
    "behavioral_regression",
    "ate_results",
    name="trust_evidence_type",
    create_type=False,
)
trust_tier_name = postgresql.ENUM(
    "certified",
    "provisional",
    "untrusted",
    name="trust_tier_name",
    create_type=False,
)
trust_recertification_trigger_type = postgresql.ENUM(
    "revision_changed",
    "policy_changed",
    "expiry_approaching",
    "conformance_failed",
    name="trust_recertification_trigger_type",
    create_type=False,
)
trust_recertification_trigger_status = postgresql.ENUM(
    "pending",
    "processed",
    "deduplicated",
    name="trust_recertification_trigger_status",
    create_type=False,
)
trust_guardrail_layer = postgresql.ENUM(
    "input_sanitization",
    "prompt_injection",
    "output_moderation",
    "tool_control",
    "memory_write",
    "action_commit",
    name="trust_guardrail_layer",
    create_type=False,
)
trust_oje_verdict_type = postgresql.ENUM(
    "COMPLIANT",
    "WARNING",
    "VIOLATION",
    "ESCALATE_TO_HUMAN",
    name="trust_oje_verdict_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    trust_certification_status.create(bind, checkfirst=True)
    trust_evidence_type.create(bind, checkfirst=True)
    trust_tier_name.create(bind, checkfirst=True)
    trust_recertification_trigger_type.create(bind, checkfirst=True)
    trust_recertification_trigger_status.create(bind, checkfirst=True)
    trust_guardrail_layer.create(bind, checkfirst=True)
    trust_oje_verdict_type.create(bind, checkfirst=True)

    op.create_table(
        "trust_certifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("agent_revision_id", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            trust_certification_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("issued_by", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
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
    op.create_foreign_key(
        "fk_trust_certifications_superseded_by_id",
        "trust_certifications",
        "trust_certifications",
        ["superseded_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_trust_certifications_agent_id", "trust_certifications", ["agent_id"], unique=False
    )
    op.create_index(
        "ix_trust_certifications_agent_status",
        "trust_certifications",
        ["agent_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_trust_certifications_revision",
        "trust_certifications",
        ["agent_revision_id"],
        unique=False,
    )

    op.create_table(
        "trust_certification_evidence_refs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("certification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", trust_evidence_type, nullable=False),
        sa.Column("source_ref_type", sa.String(length=255), nullable=False),
        sa.Column("source_ref_id", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("storage_ref", sa.String(length=1024), nullable=True),
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
            ["certification_id"],
            ["trust_certifications.id"],
            name="fk_trust_certification_evidence_refs_certification_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_trust_certification_evidence_refs_certification_id",
        "trust_certification_evidence_refs",
        ["certification_id"],
        unique=False,
    )
    op.create_index(
        "ix_trust_certification_evidence_refs_source_ref",
        "trust_certification_evidence_refs",
        ["source_ref_type", "source_ref_id"],
        unique=False,
    )

    op.create_table(
        "trust_tiers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column(
            "tier",
            trust_tier_name,
            nullable=False,
            server_default=sa.text("'untrusted'"),
        ),
        sa.Column(
            "trust_score",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "certification_component",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "guardrail_component",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "behavioral_component",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_computed_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("uq_trust_tiers_agent_id", "trust_tiers", ["agent_id"], unique=True)
    op.create_index("ix_trust_tiers_tier", "trust_tiers", ["tier"], unique=False)

    op.create_table(
        "trust_signals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("signal_type", sa.String(length=128), nullable=False),
        sa.Column("score_contribution", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("source_type", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=True),
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
    op.create_index("ix_trust_signals_agent_id", "trust_signals", ["agent_id"], unique=False)
    op.create_index(
        "ix_trust_signals_agent_type", "trust_signals", ["agent_id", "signal_type"], unique=False
    )
    op.create_index(
        "ix_trust_signals_source", "trust_signals", ["source_type", "source_id"], unique=False
    )

    op.create_table(
        "trust_proof_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proof_type", sa.String(length=128), nullable=False),
        sa.Column("proof_reference_type", sa.String(length=128), nullable=False),
        sa.Column("proof_reference_id", sa.String(length=255), nullable=False),
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
            ["signal_id"],
            ["trust_signals.id"],
            name="fk_trust_proof_links_signal_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_trust_proof_links_signal_id", "trust_proof_links", ["signal_id"], unique=False
    )
    op.create_index(
        "ix_trust_proof_links_reference",
        "trust_proof_links",
        ["proof_reference_type", "proof_reference_id"],
        unique=False,
    )

    op.create_table(
        "trust_recertification_triggers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("agent_revision_id", sa.String(length=255), nullable=False),
        sa.Column("trigger_type", trust_recertification_trigger_type, nullable=False),
        sa.Column("originating_event_type", sa.String(length=128), nullable=True),
        sa.Column("originating_event_id", sa.String(length=255), nullable=True),
        sa.Column("original_certification_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            trust_recertification_trigger_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_certification_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            ["original_certification_id"],
            ["trust_certifications.id"],
            name="fk_trust_recertification_triggers_original_certification_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["new_certification_id"],
            ["trust_certifications.id"],
            name="fk_trust_recertification_triggers_new_certification_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_trust_recertification_triggers_agent_id",
        "trust_recertification_triggers",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "uq_trust_recertification_trigger_pending",
        "trust_recertification_triggers",
        ["agent_id", "agent_revision_id", "trigger_type"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "trust_blocked_action_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("layer", trust_guardrail_layer, nullable=False),
        sa.Column("policy_basis", sa.String(length=255), nullable=False),
        sa.Column("policy_basis_detail", sa.Text(), nullable=True),
        sa.Column("input_context_hash", sa.String(length=64), nullable=False),
        sa.Column("input_context_preview", sa.String(length=500), nullable=True),
        sa.Column("execution_id", sa.String(length=255), nullable=True),
        sa.Column("interaction_id", sa.String(length=255), nullable=True),
        sa.Column("workspace_id", sa.String(length=255), nullable=True),
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
        "ix_trust_blocked_action_records_agent_id",
        "trust_blocked_action_records",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "ix_trust_blocked_action_records_execution_id",
        "trust_blocked_action_records",
        ["execution_id"],
        unique=False,
    )
    op.create_index(
        "ix_trust_blocked_action_records_workspace_id",
        "trust_blocked_action_records",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_trust_blocked_action_records_agent_layer",
        "trust_blocked_action_records",
        ["agent_id", "layer"],
        unique=False,
    )

    op.create_table(
        "trust_ate_configurations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "test_scenarios",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("golden_dataset_ref", sa.String(length=1024), nullable=True),
        sa.Column(
            "scoring_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("3600")),
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
        "ix_trust_ate_configurations_workspace_id",
        "trust_ate_configurations",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_trust_ate_configurations_active",
        "trust_ate_configurations",
        ["workspace_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "uq_trust_ate_configurations_version",
        "trust_ate_configurations",
        ["workspace_id", "name", "version"],
        unique=True,
    )

    op.create_table(
        "trust_guardrail_pipeline_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("fleet_id", sa.String(length=255), nullable=True),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        "ix_trust_guardrail_pipeline_configs_workspace_id",
        "trust_guardrail_pipeline_configs",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_trust_guardrail_pipeline_configs_fleet_id",
        "trust_guardrail_pipeline_configs",
        ["fleet_id"],
        unique=False,
    )
    op.create_index(
        "ix_trust_guardrail_pipeline_configs_workspace_fleet_active",
        "trust_guardrail_pipeline_configs",
        ["workspace_id", "fleet_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "trust_oje_pipeline_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("fleet_id", sa.String(length=255), nullable=True),
        sa.Column(
            "observer_fqns",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "judge_fqns",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "enforcer_fqns",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "policy_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        "ix_trust_oje_pipeline_configs_workspace_id",
        "trust_oje_pipeline_configs",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_trust_oje_pipeline_configs_fleet_id",
        "trust_oje_pipeline_configs",
        ["fleet_id"],
        unique=False,
    )
    op.create_index(
        "ix_trust_oje_pipeline_configs_workspace_fleet_active",
        "trust_oje_pipeline_configs",
        ["workspace_id", "fleet_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "trust_circuit_breaker_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=True),
        sa.Column("fleet_id", sa.String(length=255), nullable=True),
        sa.Column("failure_threshold", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column(
            "time_window_seconds", sa.Integer(), nullable=False, server_default=sa.text("600")
        ),
        sa.Column(
            "tripped_ttl_seconds", sa.Integer(), nullable=False, server_default=sa.text("3600")
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        "ix_trust_circuit_breaker_configs_workspace_id",
        "trust_circuit_breaker_configs",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_trust_circuit_breaker_configs_agent_id",
        "trust_circuit_breaker_configs",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "ix_trust_circuit_breaker_configs_fleet_id",
        "trust_circuit_breaker_configs",
        ["fleet_id"],
        unique=False,
    )

    op.create_table(
        "trust_prescreener_rule_sets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("rules_ref", sa.String(length=1024), nullable=False),
        sa.Column("rule_count", sa.Integer(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
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
        "uq_trust_prescreener_rule_sets_version",
        "trust_prescreener_rule_sets",
        ["version"],
        unique=True,
    )
    op.create_index(
        "ix_trust_prescreener_rule_sets_active",
        "trust_prescreener_rule_sets",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trust_prescreener_rule_sets_active", table_name="trust_prescreener_rule_sets")
    op.drop_index(
        "uq_trust_prescreener_rule_sets_version", table_name="trust_prescreener_rule_sets"
    )
    op.drop_table("trust_prescreener_rule_sets")

    op.drop_index(
        "ix_trust_circuit_breaker_configs_fleet_id", table_name="trust_circuit_breaker_configs"
    )
    op.drop_index(
        "ix_trust_circuit_breaker_configs_agent_id", table_name="trust_circuit_breaker_configs"
    )
    op.drop_index(
        "ix_trust_circuit_breaker_configs_workspace_id", table_name="trust_circuit_breaker_configs"
    )
    op.drop_table("trust_circuit_breaker_configs")

    op.drop_index(
        "ix_trust_oje_pipeline_configs_workspace_fleet_active",
        table_name="trust_oje_pipeline_configs",
    )
    op.drop_index("ix_trust_oje_pipeline_configs_fleet_id", table_name="trust_oje_pipeline_configs")
    op.drop_index(
        "ix_trust_oje_pipeline_configs_workspace_id", table_name="trust_oje_pipeline_configs"
    )
    op.drop_table("trust_oje_pipeline_configs")

    op.drop_index(
        "ix_trust_guardrail_pipeline_configs_workspace_fleet_active",
        table_name="trust_guardrail_pipeline_configs",
    )
    op.drop_index(
        "ix_trust_guardrail_pipeline_configs_fleet_id",
        table_name="trust_guardrail_pipeline_configs",
    )
    op.drop_index(
        "ix_trust_guardrail_pipeline_configs_workspace_id",
        table_name="trust_guardrail_pipeline_configs",
    )
    op.drop_table("trust_guardrail_pipeline_configs")

    op.drop_index("uq_trust_ate_configurations_version", table_name="trust_ate_configurations")
    op.drop_index("ix_trust_ate_configurations_active", table_name="trust_ate_configurations")
    op.drop_index("ix_trust_ate_configurations_workspace_id", table_name="trust_ate_configurations")
    op.drop_table("trust_ate_configurations")

    op.drop_index(
        "ix_trust_blocked_action_records_agent_layer", table_name="trust_blocked_action_records"
    )
    op.drop_index(
        "ix_trust_blocked_action_records_workspace_id", table_name="trust_blocked_action_records"
    )
    op.drop_index(
        "ix_trust_blocked_action_records_execution_id", table_name="trust_blocked_action_records"
    )
    op.drop_index(
        "ix_trust_blocked_action_records_agent_id", table_name="trust_blocked_action_records"
    )
    op.drop_table("trust_blocked_action_records")

    op.drop_index(
        "uq_trust_recertification_trigger_pending", table_name="trust_recertification_triggers"
    )
    op.drop_index(
        "ix_trust_recertification_triggers_agent_id", table_name="trust_recertification_triggers"
    )
    op.drop_table("trust_recertification_triggers")

    op.drop_index("ix_trust_proof_links_reference", table_name="trust_proof_links")
    op.drop_index("ix_trust_proof_links_signal_id", table_name="trust_proof_links")
    op.drop_table("trust_proof_links")

    op.drop_index("ix_trust_signals_source", table_name="trust_signals")
    op.drop_index("ix_trust_signals_agent_type", table_name="trust_signals")
    op.drop_index("ix_trust_signals_agent_id", table_name="trust_signals")
    op.drop_table("trust_signals")

    op.drop_index("ix_trust_tiers_tier", table_name="trust_tiers")
    op.drop_index("uq_trust_tiers_agent_id", table_name="trust_tiers")
    op.drop_table("trust_tiers")

    op.drop_index(
        "ix_trust_certification_evidence_refs_source_ref",
        table_name="trust_certification_evidence_refs",
    )
    op.drop_index(
        "ix_trust_certification_evidence_refs_certification_id",
        table_name="trust_certification_evidence_refs",
    )
    op.drop_table("trust_certification_evidence_refs")

    op.drop_index("ix_trust_certifications_revision", table_name="trust_certifications")
    op.drop_index("ix_trust_certifications_agent_status", table_name="trust_certifications")
    op.drop_index("ix_trust_certifications_agent_id", table_name="trust_certifications")
    op.drop_table("trust_certifications")

    trust_oje_verdict_type.drop(op.get_bind(), checkfirst=True)
    trust_guardrail_layer.drop(op.get_bind(), checkfirst=True)
    trust_recertification_trigger_status.drop(op.get_bind(), checkfirst=True)
    trust_recertification_trigger_type.drop(op.get_bind(), checkfirst=True)
    trust_tier_name.drop(op.get_bind(), checkfirst=True)
    trust_evidence_type.drop(op.get_bind(), checkfirst=True)
    trust_certification_status.drop(op.get_bind(), checkfirst=True)
