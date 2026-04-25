"""Privacy compliance tables and seeded DLP rules.

Revision ID: 060
Revises: 057
Create Date: 2026-04-25
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "060"
down_revision: str | None = "059_model_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DLP_SEEDS: tuple[tuple[str, str, str, str], ...] = (
    ("ssn_us", "pii", r"\b\d{3}-\d{2}-\d{4}\b", "redact"),
    ("phone_us", "pii", r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "flag"),
    ("email", "pii", r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", "redact"),
    ("iban", "pii", r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", "flag"),
    ("credit_card", "financial", r"\b(?:\d[ -]*?){13,16}\b", "block"),
    ("us_routing_number", "financial", r"\b\d{9}\b", "flag"),
    ("jwt", "confidential", r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "redact"),
    ("platform_api_key", "confidential", r"msk_[A-Za-z0-9]{32,}", "redact"),
    ("bearer_token", "confidential", r"Bearer\s+[A-Za-z0-9_\-.=]+", "redact"),
    ("openai_api_key", "confidential", r"sk-[A-Za-z0-9]{48}", "redact"),
)


def upgrade() -> None:
    _create_deletion_tombstones_table()
    _create_dsr_requests_table()
    _create_residency_configs_table()
    _create_dlp_rules_table()
    _create_dlp_events_table()
    _create_pia_table()
    _create_consent_records_table()
    _install_tombstone_trigger()
    _seed_dlp_patterns()
    _extend_role_type_enum_with_privacy_officer()
    _seed_privacy_officer_permissions()
    _extend_registry_agent_profiles_data_categories()
    _alter_clickhouse_rollups_add_is_deleted()


def downgrade() -> None:
    _drop_registry_agent_profiles_data_categories()
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trg_privacy_tombstones_immutable ON privacy_deletion_tombstones"
    )
    op.execute("DROP FUNCTION IF EXISTS privacy_tombstones_immutable()")
    op.drop_table("privacy_consent_records")
    op.drop_table("privacy_impact_assessments")
    op.drop_table("privacy_dlp_events")
    op.drop_table("privacy_dlp_rules")
    op.drop_table("privacy_residency_configs")
    op.drop_table("privacy_dsr_requests")
    op.drop_table("privacy_deletion_tombstones")


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=None if nullable else sa.text("now()"),
    )


def _jsonb(name: str, nullable: bool = False, default: str | None = None) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=nullable,
        server_default=sa.text(default) if default is not None else None,
    )


def _create_dsr_requests_table() -> None:
    op.create_table(
        "privacy_dsr_requests",
        _uuid_pk(),
        sa.Column(
            "subject_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("request_type", sa.String(length=32), nullable=False),
        sa.Column(
            "requested_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column("legal_basis", sa.String(length=256), nullable=True),
        _ts("scheduled_release_at", nullable=True),
        _ts("requested_at"),
        _ts("completed_at", nullable=True),
        sa.Column("completion_proof_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "tombstone_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("privacy_deletion_tombstones.id"),
            nullable=True,
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "request_type IN ('access','rectification','erasure',"
            "'portability','restriction','objection')",
            name="ck_privacy_dsr_request_type",
        ),
        sa.CheckConstraint(
            "status IN ('received','scheduled','in_progress','completed','failed','cancelled')",
            name="ck_privacy_dsr_status",
        ),
    )
    op.create_index("ix_dsr_subject_status", "privacy_dsr_requests", ["subject_user_id", "status"])
    op.create_index(
        "ix_dsr_scheduled_release",
        "privacy_dsr_requests",
        ["status", "scheduled_release_at"],
    )


def _create_deletion_tombstones_table() -> None:
    op.create_table(
        "privacy_deletion_tombstones",
        _uuid_pk(),
        sa.Column("subject_user_id_hash", sa.String(length=64), nullable=False),
        sa.Column("salt_version", sa.Integer(), nullable=False, server_default="1"),
        _jsonb("entities_deleted", default="'{}'::jsonb"),
        _jsonb("cascade_log", default="'[]'::jsonb"),
        sa.Column("proof_hash", sa.String(length=64), nullable=False),
        _ts("created_at"),
        sa.UniqueConstraint("proof_hash", name="uq_privacy_tombstone_proof_hash"),
    )
    op.create_index(
        "ix_tombstone_subject_hash",
        "privacy_deletion_tombstones",
        ["subject_user_id_hash", "salt_version"],
    )


def _create_residency_configs_table() -> None:
    op.create_table(
        "privacy_residency_configs",
        _uuid_pk(),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("region_code", sa.String(length=32), nullable=False),
        _jsonb("allowed_transfer_regions", default="'[]'::jsonb"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("workspace_id", name="uq_privacy_residency_workspace"),
    )


def _create_dlp_rules_table() -> None:
    op.create_table(
        "privacy_dlp_rules",
        _uuid_pk(),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("seeded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.CheckConstraint(
            "classification IN ('pii','phi','financial','confidential')",
            name="ck_privacy_dlp_classification",
        ),
        sa.CheckConstraint("action IN ('redact','block','flag')", name="ck_privacy_dlp_action"),
    )
    op.create_index("ix_dlp_rule_ws_enabled", "privacy_dlp_rules", ["workspace_id", "enabled"])


def _create_dlp_events_table() -> None:
    op.create_table(
        "privacy_dlp_events",
        _uuid_pk(),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("privacy_dlp_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("match_summary", sa.String(length=128), nullable=False),
        sa.Column("action_taken", sa.String(length=32), nullable=False),
        _ts("created_at"),
        sa.CheckConstraint(
            "action_taken IN ('redact','block','flag')",
            name="ck_privacy_dlp_event_action",
        ),
    )
    op.create_index("ix_dlp_events_by_rule_time", "privacy_dlp_events", ["rule_id", "created_at"])
    op.create_index("ix_dlp_events_by_execution", "privacy_dlp_events", ["execution_id"])


def _create_pia_table() -> None:
    op.create_table(
        "privacy_impact_assessments",
        _uuid_pk(),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        _jsonb("data_categories", default="'[]'::jsonb"),
        sa.Column("legal_basis", sa.Text(), nullable=False),
        sa.Column("retention_policy", sa.Text(), nullable=True),
        _jsonb("risks", nullable=True),
        _jsonb("mitigations", nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column(
            "submitted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "approved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        _ts("approved_at", nullable=True),
        sa.Column("rejection_feedback", sa.Text(), nullable=True),
        sa.Column(
            "superseded_by_pia_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("privacy_impact_assessments.id"),
            nullable=True,
        ),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "subject_type IN ('agent','workspace','workflow')",
            name="ck_privacy_pia_subject_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft','under_review','approved','rejected','superseded')",
            name="ck_privacy_pia_status",
        ),
        sa.CheckConstraint("length(legal_basis) >= 10", name="ck_privacy_pia_legal_basis_len"),
        sa.CheckConstraint(
            "approved_by IS NULL OR approved_by != submitted_by",
            name="ck_privacy_pia_approver_differs",
        ),
    )
    op.create_index(
        "ix_pia_by_subject",
        "privacy_impact_assessments",
        ["subject_type", "subject_id", "status"],
    )


def _create_consent_records_table() -> None:
    op.create_table(
        "privacy_consent_records",
        _uuid_pk(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consent_type", sa.String(length=64), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        _ts("granted_at"),
        _ts("revoked_at", nullable=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "consent_type IN ('ai_interaction','data_collection','training_use')",
            name="ck_privacy_consent_type",
        ),
        sa.UniqueConstraint("user_id", "consent_type", name="uq_privacy_consent_user_type"),
    )
    op.create_index(
        "ix_consent_user_type_revoked",
        "privacy_consent_records",
        ["user_id", "consent_type", "revoked_at"],
    )


def _install_tombstone_trigger() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION privacy_tombstones_immutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'privacy deletion tombstones are immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_privacy_tombstones_immutable
        BEFORE UPDATE OR DELETE ON privacy_deletion_tombstones
        FOR EACH ROW EXECUTE FUNCTION privacy_tombstones_immutable();
        """
    )


def _seed_dlp_patterns() -> None:
    table = sa.table(
        "privacy_dlp_rules",
        sa.column("name", sa.String),
        sa.column("classification", sa.String),
        sa.column("pattern", sa.Text),
        sa.column("action", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("seeded", sa.Boolean),
    )
    op.bulk_insert(
        table,
        [
            {
                "name": name,
                "classification": classification,
                "pattern": pattern,
                "action": action,
                "enabled": True,
                "seeded": True,
            }
            for name, classification, pattern, action in DLP_SEEDS
        ],
    )


def _extend_role_type_enum_with_privacy_officer() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'roletype') THEN
                ALTER TYPE roletype ADD VALUE IF NOT EXISTS 'privacy_officer';
            END IF;
        END $$;
        """
    )


def _seed_privacy_officer_permissions() -> None:
    permissions = (
        ("privacy_officer", "dsr", "read"),
        ("privacy_officer", "dsr", "write"),
        ("privacy_officer", "pia", "read"),
        ("privacy_officer", "pia", "write"),
        ("privacy_officer", "consent", "read"),
        ("privacy_officer", "consent", "write"),
        ("privacy_officer", "dlp", "read"),
        ("privacy_officer", "dlp", "write"),
        ("privacy_officer", "audit", "read"),
        ("privacy_officer", "tombstone", "read"),
    )
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("role_permissions"):
        return
    for role, resource, action in permissions:
        op.execute(
            sa.text(
                """
                INSERT INTO role_permissions (role, resource_type, action, scope)
                VALUES (:role, :resource, :action, 'platform')
                ON CONFLICT DO NOTHING
                """
            ).bindparams(role=role, resource=resource, action=action)
        )


def _extend_registry_agent_profiles_data_categories() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("registry_agent_profiles"):
        return
    with op.batch_alter_table("registry_agent_profiles") as batch:
        batch.add_column(
            sa.Column(
                "data_categories",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            )
        )


def _drop_registry_agent_profiles_data_categories() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("registry_agent_profiles"):
        return
    with op.batch_alter_table("registry_agent_profiles") as batch:
        batch.drop_column("data_categories")


def _alter_clickhouse_rollups_add_is_deleted() -> None:
    tables_raw = os.getenv(
        "PRIVACY_CLICKHOUSE_PII_TABLES",
        "execution_metrics,agent_performance,token_usage",
    )
    tables = [table.strip() for table in tables_raw.split(",") if table.strip()]
    if not tables or os.getenv("ALEMBIC_SKIP_CLICKHOUSE_PRIVACY") == "1":
        return

    async def _run() -> None:
        from platform.common.clients.clickhouse import AsyncClickHouseClient
        from platform.common.config import settings

        client = AsyncClickHouseClient.from_settings(settings)
        await client.connect()
        try:
            for table in tables:
                await client.execute_command(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS is_deleted UInt8 DEFAULT 0"
                )
        finally:
            await client.close()

    try:
        asyncio.run(_run())
    except Exception:
        # Postgres schema changes must not be rolled back by an unavailable analytics store.
        return
