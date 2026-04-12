"""Workflow definition and execution engine schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "012_workflow_execution_engine"
down_revision = "011_policy_governance_engine"
branch_labels = None
depends_on = None


workflow_status = postgresql.ENUM(
    "active",
    "archived",
    "draft",
    name="workflow_status",
    create_type=False,
)
workflow_trigger_type = postgresql.ENUM(
    "webhook",
    "cron",
    "orchestrator",
    "manual",
    "api",
    "event_bus",
    "workspace_goal",
    name="workflow_trigger_type",
    create_type=False,
)
execution_status = postgresql.ENUM(
    "queued",
    "running",
    "waiting_for_approval",
    "completed",
    "failed",
    "canceled",
    "compensating",
    name="execution_status",
    create_type=False,
)
execution_event_type = postgresql.ENUM(
    "created",
    "queued",
    "dispatched",
    "runtime_started",
    "sandbox_requested",
    "waiting_for_approval",
    "approved",
    "rejected",
    "approval_timed_out",
    "resumed",
    "retried",
    "completed",
    "failed",
    "canceled",
    "compensated",
    "compensation_failed",
    "hot_changed",
    "reasoning_trace_emitted",
    "self_correction_started",
    "self_correction_converged",
    "context_assembled",
    "reprioritized",
    name="execution_event_type",
    create_type=False,
)
approval_decision = postgresql.ENUM(
    "approved",
    "rejected",
    "timed_out",
    "escalated",
    name="approval_decision",
    create_type=False,
)
compensation_outcome = postgresql.ENUM(
    "completed",
    "failed",
    "not_available",
    name="compensation_outcome",
    create_type=False,
)
approval_timeout_action = postgresql.ENUM(
    "fail",
    "skip",
    "escalate",
    name="approval_timeout_action",
    create_type=False,
)


LEGACY_EXECUTION_EVENTS_TABLE = "legacy_execution_events"


def _has_table(bind: sa.engine.Connection, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _should_rename_legacy_execution_events(bind: sa.engine.Connection) -> bool:
    if not _has_table(bind, "execution_events"):
        return False
    columns = {
        column["name"] for column in sa.inspect(bind).get_columns("execution_events")
    }
    return "occurred_at" in columns and "sequence" not in columns


def upgrade() -> None:
    bind = op.get_bind()
    workflow_status.create(bind, checkfirst=True)
    workflow_trigger_type.create(bind, checkfirst=True)
    execution_status.create(bind, checkfirst=True)
    execution_event_type.create(bind, checkfirst=True)
    approval_decision.create(bind, checkfirst=True)
    compensation_outcome.create(bind, checkfirst=True)
    approval_timeout_action.create(bind, checkfirst=True)
    if _should_rename_legacy_execution_events(bind):
        op.rename_table("execution_events", LEGACY_EXECUTION_EVENTS_TABLE)

    op.create_table(
        "workflow_definitions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            workflow_status,
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
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
    op.create_index("ix_workflow_definitions_name", "workflow_definitions", ["name"], unique=False)
    op.create_index(
        "ix_workflow_definitions_status",
        "workflow_definitions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_definitions_workspace_id",
        "workflow_definitions",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "uq_workflow_definitions_workspace_name",
        "workflow_definitions",
        ["workspace_id", "name"],
        unique=True,
    )

    op.create_table(
        "workflow_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("yaml_source", sa.Text(), nullable=False),
        sa.Column(
            "compiled_ir",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_valid",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
            ["definition_id"],
            ["workflow_definitions.id"],
            name="fk_workflow_versions_definition_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_workflow_versions_definition_id",
        "workflow_versions",
        ["definition_id"],
        unique=False,
    )
    op.create_index(
        "uq_workflow_versions_definition_version",
        "workflow_versions",
        ["definition_id", "version_number"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_workflow_definitions_current_version_id",
        "workflow_definitions",
        "workflow_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "workflow_trigger_definitions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger_type", workflow_trigger_type, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("max_concurrent_executions", sa.Integer(), nullable=True),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
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
            ["definition_id"],
            ["workflow_definitions.id"],
            name="fk_workflow_trigger_definitions_definition_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_workflow_trigger_definitions_definition_id",
        "workflow_trigger_definitions",
        ["definition_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_trigger_definitions_type",
        "workflow_trigger_definitions",
        ["trigger_type"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_trigger_definitions_is_active",
        "workflow_trigger_definitions",
        ["is_active"],
        unique=False,
    )

    op.create_table(
        "executions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workflow_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "trigger_type",
            workflow_trigger_type,
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
        sa.Column(
            "status",
            execution_status,
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column(
            "input_parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_interaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_fleet_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rerun_of_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=True),
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
            ["workflow_version_id"],
            ["workflow_versions.id"],
            name="fk_executions_workflow_version_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_definition_id"],
            ["workflow_definitions.id"],
            name="fk_executions_workflow_definition_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["trigger_id"],
            ["workflow_trigger_definitions.id"],
            name="fk_executions_trigger_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_execution_id"],
            ["executions.id"],
            name="fk_executions_parent_execution_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["rerun_of_execution_id"],
            ["executions.id"],
            name="fk_executions_rerun_of_execution_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_executions_workspace_status",
        "executions",
        ["workspace_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_executions_workflow_definition_id",
        "executions",
        ["workflow_definition_id"],
        unique=False,
    )
    op.create_index(
        "ix_executions_correlation_goal_id",
        "executions",
        ["correlation_goal_id"],
        unique=False,
    )

    op.create_table(
        "execution_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", execution_event_type, nullable=False),
        sa.Column("step_id", sa.String(length=255), nullable=True),
        sa.Column("agent_fqn", sa.String(length=512), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("correlation_workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_interaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_fleet_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.id"],
            name="fk_execution_events_execution_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_execution_events_execution_sequence",
        "execution_events",
        ["execution_id", "sequence"],
        unique=True,
    )
    op.create_index(
        "ix_execution_events_execution_type",
        "execution_events",
        ["execution_id", "event_type"],
        unique=False,
    )
    op.create_index(
        "ix_execution_events_created_at",
        "execution_events",
        ["created_at"],
        unique=False,
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_execution_event_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'execution_events is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_execution_events_append_only
        BEFORE UPDATE OR DELETE ON execution_events
        FOR EACH ROW EXECUTE FUNCTION prevent_execution_event_mutation();
        """
    )

    op.create_table(
        "execution_checkpoints",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_event_sequence", sa.Integer(), nullable=False),
        sa.Column(
            "step_results",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "completed_step_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "pending_step_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "active_step_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "execution_data",
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
            ["execution_id"],
            ["executions.id"],
            name="fk_execution_checkpoints_execution_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_execution_checkpoints_execution_sequence",
        "execution_checkpoints",
        ["execution_id", "last_event_sequence"],
        unique=False,
    )

    op.create_table(
        "execution_dispatch_leases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", sa.String(length=255), nullable=False),
        sa.Column("scheduler_worker_id", sa.String(length=255), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "expired",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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
            ["execution_id"],
            ["executions.id"],
            name="fk_execution_dispatch_leases_execution_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_execution_dispatch_leases_execution_step",
        "execution_dispatch_leases",
        ["execution_id", "step_id"],
        unique=False,
    )
    op.create_index(
        "ix_execution_dispatch_leases_active",
        "execution_dispatch_leases",
        ["execution_id", "released_at"],
        unique=False,
    )

    op.create_table(
        "execution_task_plan_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", sa.String(length=255), nullable=False),
        sa.Column("selected_agent_fqn", sa.String(length=512), nullable=True),
        sa.Column("selected_tool_fqn", sa.String(length=512), nullable=True),
        sa.Column("rationale_summary", sa.Text(), nullable=True),
        sa.Column(
            "considered_agents_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "considered_tools_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "rejected_alternatives_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "parameter_sources",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("storage_size_bytes", sa.Integer(), nullable=True),
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
            ["execution_id"],
            ["executions.id"],
            name="fk_execution_task_plan_records_execution_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_execution_task_plan_records_execution_id",
        "execution_task_plan_records",
        ["execution_id"],
        unique=False,
    )
    op.create_index(
        "uq_execution_task_plan_records_execution_step",
        "execution_task_plan_records",
        ["execution_id", "step_id"],
        unique=True,
    )

    op.create_table(
        "execution_approval_waits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", sa.String(length=255), nullable=False),
        sa.Column(
            "required_approvers",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "timeout_action",
            approval_timeout_action,
            nullable=False,
            server_default=sa.text("'fail'"),
        ),
        sa.Column("decision", approval_decision, nullable=True),
        sa.Column("decided_by", sa.String(length=255), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interaction_message_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            ["execution_id"],
            ["executions.id"],
            name="fk_execution_approval_waits_execution_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_execution_approval_waits_execution_step",
        "execution_approval_waits",
        ["execution_id", "step_id"],
        unique=False,
    )
    op.create_index(
        "ix_execution_approval_waits_timeout_at",
        "execution_approval_waits",
        ["timeout_at"],
        unique=False,
    )

    op.create_table(
        "execution_compensation_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", sa.String(length=255), nullable=False),
        sa.Column("compensation_handler", sa.String(length=255), nullable=False),
        sa.Column("triggered_by", sa.String(length=64), nullable=False),
        sa.Column(
            "outcome",
            compensation_outcome,
            nullable=False,
            server_default=sa.text("'not_available'"),
        ),
        sa.Column("error_detail", sa.Text(), nullable=True),
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
            ["execution_id"],
            ["executions.id"],
            name="fk_execution_compensation_records_execution_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_execution_compensation_records_execution_id",
        "execution_compensation_records",
        ["execution_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index(
        "ix_execution_compensation_records_execution_id",
        table_name="execution_compensation_records",
    )
    op.drop_table("execution_compensation_records")

    op.drop_index("ix_execution_approval_waits_timeout_at", table_name="execution_approval_waits")
    op.drop_index(
        "ix_execution_approval_waits_execution_step",
        table_name="execution_approval_waits",
    )
    op.drop_table("execution_approval_waits")

    op.drop_index(
        "uq_execution_task_plan_records_execution_step",
        table_name="execution_task_plan_records",
    )
    op.drop_index(
        "ix_execution_task_plan_records_execution_id",
        table_name="execution_task_plan_records",
    )
    op.drop_table("execution_task_plan_records")

    op.drop_index(
        "ix_execution_dispatch_leases_active",
        table_name="execution_dispatch_leases",
    )
    op.drop_index(
        "ix_execution_dispatch_leases_execution_step",
        table_name="execution_dispatch_leases",
    )
    op.drop_table("execution_dispatch_leases")

    op.drop_index(
        "ix_execution_checkpoints_execution_sequence",
        table_name="execution_checkpoints",
    )
    op.drop_table("execution_checkpoints")

    op.execute("DROP TRIGGER IF EXISTS trg_execution_events_append_only ON execution_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_execution_event_mutation()")
    op.drop_index("ix_execution_events_created_at", table_name="execution_events")
    op.drop_index("ix_execution_events_execution_type", table_name="execution_events")
    op.drop_index("uq_execution_events_execution_sequence", table_name="execution_events")
    op.drop_table("execution_events")
    if _has_table(bind, LEGACY_EXECUTION_EVENTS_TABLE):
        op.rename_table(LEGACY_EXECUTION_EVENTS_TABLE, "execution_events")

    op.drop_index("ix_executions_correlation_goal_id", table_name="executions")
    op.drop_index("ix_executions_workflow_definition_id", table_name="executions")
    op.drop_index("ix_executions_workspace_status", table_name="executions")
    op.drop_table("executions")

    op.drop_index(
        "ix_workflow_trigger_definitions_is_active",
        table_name="workflow_trigger_definitions",
    )
    op.drop_index(
        "ix_workflow_trigger_definitions_type",
        table_name="workflow_trigger_definitions",
    )
    op.drop_index(
        "ix_workflow_trigger_definitions_definition_id",
        table_name="workflow_trigger_definitions",
    )
    op.drop_table("workflow_trigger_definitions")

    op.drop_constraint(
        "fk_workflow_definitions_current_version_id",
        "workflow_definitions",
        type_="foreignkey",
    )
    op.drop_index("uq_workflow_versions_definition_version", table_name="workflow_versions")
    op.drop_index("ix_workflow_versions_definition_id", table_name="workflow_versions")
    op.drop_table("workflow_versions")

    op.drop_index(
        "uq_workflow_definitions_workspace_name",
        table_name="workflow_definitions",
    )
    op.drop_index("ix_workflow_definitions_workspace_id", table_name="workflow_definitions")
    op.drop_index("ix_workflow_definitions_status", table_name="workflow_definitions")
    op.drop_index("ix_workflow_definitions_name", table_name="workflow_definitions")
    op.drop_table("workflow_definitions")

    compensation_outcome.drop(op.get_bind(), checkfirst=True)
    approval_timeout_action.drop(op.get_bind(), checkfirst=True)
    approval_decision.drop(op.get_bind(), checkfirst=True)
    execution_event_type.drop(op.get_bind(), checkfirst=True)
    execution_status.drop(op.get_bind(), checkfirst=True)
    workflow_trigger_type.drop(op.get_bind(), checkfirst=True)
    workflow_status.drop(op.get_bind(), checkfirst=True)
