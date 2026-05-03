"""Data Lifecycle (UPD-051) — workspace + tenant export jobs, two-phase
deletion jobs, and the public sub-processors registry.

Adds 3 new tables that back the data-lifecycle bounded context per
``specs/104-data-lifecycle/data-model.md``:

* ``data_export_jobs`` — async export job ledger (workspace + tenant scope)
* ``deletion_jobs`` — two-phase deletion ledger (workspace + tenant scope)
* ``sub_processors`` — platform-level public sub-processor registry

Also extends the ``workspaces_workspace_status`` PostgreSQL enum with the
new ``pending_deletion`` value (the existing ``tenants.status`` CHECK
constraint already accepts ``pending_deletion`` as of UPD-046, so no
tenant-side change is required).

The ``data_export_jobs`` and ``deletion_jobs`` tables are tenant-scoped
and gain the canonical ``tenant_isolation`` RLS policy; ``sub_processors``
is platform-level (no RLS) because the public page reads it without a
tenant context.

Revision ID: 111_data_lifecycle
Revises: 110_abuse_prevention
Create Date: 2026-05-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "111_data_lifecycle"
down_revision: str | None = "110_abuse_prevention"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PG_UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())

SCOPE_TYPE_VALUES = ("workspace", "tenant")
EXPORT_STATUS_VALUES = ("pending", "processing", "completed", "failed")
DELETION_PHASE_VALUES = ("phase_1", "phase_2", "completed", "aborted")

DEFAULT_SUB_PROCESSORS = (
    {
        "name": "Anthropic, PBC",
        "category": "LLM provider",
        "location": "USA",
        "data_categories": ["prompts", "outputs"],
        "privacy_policy_url": "https://www.anthropic.com/legal/privacy",
        "dpa_url": None,
        "started_using_at": "2024-09-01",
        "notes": None,
    },
    {
        "name": "OpenAI, L.L.C.",
        "category": "LLM provider",
        "location": "USA",
        "data_categories": ["prompts", "outputs"],
        "privacy_policy_url": "https://openai.com/policies/privacy-policy",
        "dpa_url": "https://openai.com/policies/data-processing-addendum",
        "started_using_at": "2024-09-01",
        "notes": None,
    },
    {
        "name": "Hetzner Online GmbH",
        "category": "Infrastructure",
        "location": "Germany",
        "data_categories": ["all_platform_data_at_rest"],
        "privacy_policy_url": "https://www.hetzner.com/legal/privacy-policy",
        "dpa_url": "https://www.hetzner.com/AV/DPA_en.pdf",
        "started_using_at": "2024-09-01",
        "notes": None,
    },
    {
        "name": "Stripe Payments Europe Ltd",
        "category": "Billing",
        "location": "Ireland",
        "data_categories": ["payment_method_metadata", "invoices"],
        "privacy_policy_url": "https://stripe.com/privacy",
        "dpa_url": "https://stripe.com/legal/dpa",
        "started_using_at": "2024-09-01",
        "notes": None,
    },
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Extend the workspaces_workspace_status enum with pending_deletion.
    #    Postgres requires ALTER TYPE ... ADD VALUE outside a transaction
    #    (no explicit BEGIN/COMMIT) but Alembic's transactional_ddl
    #    handling is fine in a fresh migration since it autocommits the
    #    individual statement when ``IF NOT EXISTS`` is present.
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TYPE workspaces_workspace_status ADD VALUE IF NOT EXISTS 'pending_deletion'"
    )

    # ------------------------------------------------------------------
    # 2. data_export_jobs
    # ------------------------------------------------------------------
    op.create_table(
        "data_export_jobs",
        sa.Column(
            "id",
            PG_UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            PG_UUID,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", PG_UUID, nullable=False),
        sa.Column(
            "requested_by_user_id",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output_url", sa.Text(), nullable=True),
        sa.Column("output_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("output_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("correlation_id", PG_UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            f"scope_type IN {SCOPE_TYPE_VALUES!r}",
            name="ck_data_export_jobs_scope_type",
        ),
        sa.CheckConstraint(
            f"status IN {EXPORT_STATUS_VALUES!r}",
            name="ck_data_export_jobs_status",
        ),
    )
    op.create_index(
        "data_export_jobs_tenant_status_idx",
        "data_export_jobs",
        ["tenant_id", "status", sa.text("created_at DESC")],
    )
    op.create_index(
        "data_export_jobs_scope_idx",
        "data_export_jobs",
        ["scope_type", "scope_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "data_export_jobs_active_idx",
        "data_export_jobs",
        ["status"],
        postgresql_where=sa.text("status IN ('pending','processing')"),
    )
    _enable_rls("data_export_jobs")

    # ------------------------------------------------------------------
    # 3. deletion_jobs
    # ------------------------------------------------------------------
    op.create_table(
        "deletion_jobs",
        sa.Column(
            "id",
            PG_UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            PG_UUID,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", PG_UUID, nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column(
            "requested_by_user_id",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("two_pa_token_id", PG_UUID, nullable=True),
        sa.Column("grace_period_days", sa.Integer(), nullable=False),
        sa.Column("grace_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_token_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("cancel_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cascade_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cascade_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tombstone_id", PG_UUID, nullable=True),
        sa.Column(
            "final_export_job_id",
            PG_UUID,
            sa.ForeignKey("data_export_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("abort_reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", PG_UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            f"scope_type IN {SCOPE_TYPE_VALUES!r}",
            name="ck_deletion_jobs_scope_type",
        ),
        sa.CheckConstraint(
            f"phase IN {DELETION_PHASE_VALUES!r}",
            name="ck_deletion_jobs_phase",
        ),
        sa.CheckConstraint(
            "grace_period_days BETWEEN 1 AND 365",
            name="ck_deletion_jobs_grace_bounds",
        ),
    )
    op.create_index(
        "deletion_jobs_scope_idx",
        "deletion_jobs",
        ["tenant_id", "scope_type", "scope_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "deletion_jobs_grace_scan_idx",
        "deletion_jobs",
        ["grace_ends_at"],
        postgresql_where=sa.text("phase = 'phase_1'"),
    )
    op.create_index(
        "deletion_jobs_cancel_token_uq",
        "deletion_jobs",
        ["cancel_token_hash"],
        unique=True,
    )
    op.create_index(
        "uq_deletion_jobs_active_per_scope",
        "deletion_jobs",
        ["scope_type", "scope_id"],
        unique=True,
        postgresql_where=sa.text("phase IN ('phase_1','phase_2')"),
    )
    _enable_rls("deletion_jobs")

    # ------------------------------------------------------------------
    # 4. sub_processors (platform-level — no RLS)
    # ------------------------------------------------------------------
    op.create_table(
        "sub_processors",
        sa.Column(
            "id",
            PG_UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("location", sa.String(length=64), nullable=False),
        sa.Column(
            "data_categories",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column("privacy_policy_url", sa.Text(), nullable=True),
        sa.Column("dpa_url", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("started_using_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "updated_by_user_id",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
        sa.UniqueConstraint("name", name="uq_sub_processors_name"),
    )
    op.create_index(
        "sub_processors_active_category_idx",
        "sub_processors",
        ["is_active", "category"],
    )

    # Idempotent default-row seed. ``ON CONFLICT (name) DO NOTHING``
    # ensures rerunning the migration in a partial-rollback scenario
    # does not duplicate or clobber operator edits.
    for row in DEFAULT_SUB_PROCESSORS:
        op.execute(
            sa.text(
                """
                INSERT INTO sub_processors
                    (name, category, location, data_categories,
                     privacy_policy_url, dpa_url, started_using_at, notes)
                VALUES
                    (:name, :category, :location,
                     CAST(:data_categories AS text[]),
                     :privacy_policy_url, :dpa_url,
                     CAST(:started_using_at AS date), :notes)
                ON CONFLICT (name) DO NOTHING
                """
            ).bindparams(
                name=row["name"],
                category=row["category"],
                location=row["location"],
                data_categories="{" + ",".join(row["data_categories"]) + "}",
                privacy_policy_url=row["privacy_policy_url"],
                dpa_url=row["dpa_url"],
                started_using_at=row["started_using_at"],
                notes=row["notes"],
            )
        )


def downgrade() -> None:
    # sub_processors first — no RLS to detach.
    op.drop_index("sub_processors_active_category_idx", table_name="sub_processors")
    op.drop_table("sub_processors")

    # deletion_jobs
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "deletion_jobs"')
    op.execute('ALTER TABLE "deletion_jobs" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "deletion_jobs" DISABLE ROW LEVEL SECURITY')
    op.drop_index("uq_deletion_jobs_active_per_scope", table_name="deletion_jobs")
    op.drop_index("deletion_jobs_cancel_token_uq", table_name="deletion_jobs")
    op.drop_index("deletion_jobs_grace_scan_idx", table_name="deletion_jobs")
    op.drop_index("deletion_jobs_scope_idx", table_name="deletion_jobs")
    op.drop_table("deletion_jobs")

    # data_export_jobs
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "data_export_jobs"')
    op.execute('ALTER TABLE "data_export_jobs" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "data_export_jobs" DISABLE ROW LEVEL SECURITY')
    op.drop_index("data_export_jobs_active_idx", table_name="data_export_jobs")
    op.drop_index("data_export_jobs_scope_idx", table_name="data_export_jobs")
    op.drop_index("data_export_jobs_tenant_status_idx", table_name="data_export_jobs")
    op.drop_table("data_export_jobs")

    # NOTE: ALTER TYPE ... DROP VALUE is not supported by PostgreSQL.
    # The ``pending_deletion`` enum value remains after downgrade.
    # This is acceptable — a re-applied upgrade will use the value as-is.


def _enable_rls(table_name: str) -> None:
    quoted = '"' + table_name.replace('"', '""') + '"'
    op.execute(f"ALTER TABLE {quoted} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {quoted} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {quoted}
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )
