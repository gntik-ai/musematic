"""Add creator context profile versions and contract templates.

Revision ID: 072_creator_context_contracts
Revises: 071_workspace_owner_workbench
Create Date: 2026-04-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "072_creator_context_contracts"
down_revision: str | None = "071_workspace_owner_workbench"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PLATFORM_TEMPLATE_NAMES = (
    "Customer support agent contract",
    "Code review agent contract",
    "Data analysis agent contract",
    "Database write agent contract",
    "External API call agent contract",
)


def upgrade() -> None:
    op.create_table(
        "context_engineering_profile_versions",
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
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "content_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["context_engineering_profiles.id"],
            name="fk_context_profile_versions_profile_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_context_profile_versions_created_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "profile_id",
            "version_number",
            name="uq_context_profile_versions_profile_version",
        ),
    )
    op.create_index(
        "ix_context_profile_versions_profile",
        "context_engineering_profile_versions",
        ["profile_id", "version_number"],
        unique=False,
    )

    op.create_table(
        "contract_templates",
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
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column(
            "template_content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("forked_from_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_platform_authored",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["forked_from_template_id"],
            ["contract_templates.id"],
            name="fk_contract_templates_forked_from",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_contract_templates_created_by_user_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_contract_templates_category",
        "contract_templates",
        ["category"],
        unique=False,
    )
    op.create_index(
        "ix_contract_templates_published",
        "contract_templates",
        ["is_published"],
        unique=False,
    )

    op.add_column(
        "agent_contracts",
        sa.Column("attached_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_contracts_attached_revision_id",
        "agent_contracts",
        "registry_agent_revisions",
        ["attached_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )

    templates = [
        (
            "Customer support agent contract",
            "Baseline contract for support agents handling customer-facing tickets.",
            "customer-support",
            '{"task_scope":"Resolve customer support questions using approved knowledge sources.","expected_outputs":{"required":["answer","citations","handoff_reason"]},"quality_thresholds":{"minimum_confidence":0.72},"escalation_conditions":{"pii_detected":"escalate","refund_request":"warn"},"success_criteria":{"must_include_citation":true},"enforcement_policy":"warn"}',
        ),
        (
            "Code review agent contract",
            "Guardrails for agents reviewing code changes and suggesting fixes.",
            "code-review",
            '{"task_scope":"Review code for correctness, tests, security, and maintainability.","expected_outputs":{"required":["findings","risk_level","test_notes"]},"quality_thresholds":{"minimum_actionable_findings":1},"escalation_conditions":{"secret_detected":"terminate","license_risk":"escalate"},"success_criteria":{"requires_file_references":true},"enforcement_policy":"escalate"}',
        ),
        (
            "Data analysis agent contract",
            "Contract for analytical agents operating on workspace datasets.",
            "data-analysis",
            '{"task_scope":"Analyze approved datasets and report assumptions, methods, and confidence.","expected_outputs":{"required":["summary","method","confidence","limitations"]},"quality_thresholds":{"minimum_confidence":0.7},"escalation_conditions":{"sensitive_data":"escalate"},"success_criteria":{"no_unapproved_export":true},"enforcement_policy":"warn"}',
        ),
        (
            "Database write agent contract",
            "Strict contract for agents that can propose or execute database writes.",
            "database",
            '{"task_scope":"Perform database writes only after validation and approval gates pass.","expected_outputs":{"required":["change_plan","rollback_plan","approval_ref"]},"quality_thresholds":{"requires_transaction":true},"escalation_conditions":{"missing_approval":"terminate","destructive_change":"escalate"},"success_criteria":{"rollback_plan_required":true},"enforcement_policy":"terminate"}',
        ),
        (
            "External API call agent contract",
            "Contract for agents that call external services or connectors.",
            "external-api",
            '{"task_scope":"Call external APIs only within workspace visibility and rate-limit policy.","expected_outputs":{"required":["request_summary","response_summary","error_handling"]},"quality_thresholds":{"max_retries":3},"escalation_conditions":{"secret_in_payload":"terminate","rate_limit_exceeded":"throttle"},"success_criteria":{"logs_redact_secrets":true},"enforcement_policy":"throttle"}',
        ),
    ]
    for name, description, category, content in templates:
        op.execute(
            sa.text(
                """
                INSERT INTO contract_templates (
                    name,
                    description,
                    category,
                    template_content,
                    version_number,
                    is_platform_authored,
                    is_published
                )
                VALUES (
                    :name,
                    :description,
                    :category,
                    CAST(:template_content AS jsonb),
                    1,
                    true,
                    true
                )
                ON CONFLICT (name) DO NOTHING
                """
            ).bindparams(
                name=name,
                description=description,
                category=category,
                template_content=content,
            )
        )


def downgrade() -> None:
    quoted_names = ", ".join("'" + name.replace("'", "''") + "'" for name in PLATFORM_TEMPLATE_NAMES)
    op.execute(f"DELETE FROM contract_templates WHERE name IN ({quoted_names})")
    op.drop_constraint(
        "fk_agent_contracts_attached_revision_id",
        "agent_contracts",
        type_="foreignkey",
    )
    op.drop_column("agent_contracts", "attached_revision_id")
    op.drop_index("ix_contract_templates_published", table_name="contract_templates")
    op.drop_index("ix_contract_templates_category", table_name="contract_templates")
    op.drop_table("contract_templates")
    op.drop_index(
        "ix_context_profile_versions_profile",
        table_name="context_engineering_profile_versions",
    )
    op.drop_table("context_engineering_profile_versions")
