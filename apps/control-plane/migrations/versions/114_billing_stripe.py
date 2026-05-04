"""Billing Stripe (UPD-052) — payment methods, invoices, processed webhooks,
and the failed-payment grace ledger.

Adds the four tables that back the Stripe-driven billing surface introduced
by UPD-052 per ``specs/105-billing-payment-provider/data-model.md``:

* ``payment_methods`` — local mirror of Stripe payment methods (tenant-scoped, RLS)
* ``invoices`` — local mirror of Stripe invoices (tenant-scoped, RLS)
* ``processed_webhooks`` — Stripe event-id idempotency table (platform-level)
* ``payment_failure_grace`` — 7-day failed-payment grace state machine
  (tenant-scoped, RLS; partial unique index enforces "one open grace per
  subscription")

Also adds the deferred FK on ``subscriptions.payment_method_id`` →
``payment_methods.id``. The column already exists from UPD-047 with NULL
semantics; the FK was deferred until ``payment_methods`` existed. The
constraint is ``DEFERRABLE INITIALLY DEFERRED`` so upgrade paths can create
the payment-method row and assign it to the subscription within a single
transaction.

Revision ID: 114_billing_stripe
Revises: 113_subproc_email_subs
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "114_billing_stripe"
down_revision: str | None = "113_subproc_email_subs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PG_UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())

INVOICE_STATUS_VALUES = ("draft", "open", "paid", "void", "uncollectible")
GRACE_RESOLUTION_VALUES = (
    "payment_recovered",
    "downgraded_to_free",
    "manually_resolved",
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # payment_methods
    # ------------------------------------------------------------------
    op.create_table(
        "payment_methods",
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
        sa.Column("workspace_id", PG_UUID, nullable=True),
        sa.Column(
            "stripe_payment_method_id",
            sa.String(length=64),
            nullable=False,
            unique=True,
        ),
        sa.Column("brand", sa.String(length=32), nullable=True),
        sa.Column("last4", sa.String(length=4), nullable=True),
        sa.Column("exp_month", sa.Integer(), nullable=True),
        sa.Column("exp_year", sa.Integer(), nullable=True),
        sa.Column(
            "is_default",
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
    )
    op.create_index(
        "ix_payment_methods_tenant_workspace",
        "payment_methods",
        ["tenant_id", "workspace_id"],
    )
    op.create_index(
        "ix_payment_methods_default",
        "payment_methods",
        ["tenant_id", "workspace_id"],
        postgresql_where=sa.text("is_default = true"),
    )
    _enable_rls("payment_methods")

    # ------------------------------------------------------------------
    # invoices
    # ------------------------------------------------------------------
    op.create_table(
        "invoices",
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
        sa.Column(
            "subscription_id",
            PG_UUID,
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stripe_invoice_id",
            sa.String(length=64),
            nullable=False,
            unique=True,
        ),
        sa.Column("invoice_number", sa.String(length=64), nullable=True),
        sa.Column(
            "amount_total",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
        ),
        sa.Column(
            "amount_subtotal",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
        ),
        sa.Column(
            "amount_tax",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default=sa.text("'EUR'"),
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pdf_url", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            f"status IN {INVOICE_STATUS_VALUES}",
            name="invoices_status_check",
        ),
    )
    op.create_index(
        "ix_invoices_tenant_period",
        "invoices",
        ["tenant_id", sa.text("period_end DESC")],
    )
    op.create_index(
        "ix_invoices_subscription",
        "invoices",
        ["subscription_id", sa.text("period_end DESC")],
    )
    op.create_index(
        "ix_invoices_status_open",
        "invoices",
        ["tenant_id"],
        postgresql_where=sa.text("status = 'open'"),
    )
    _enable_rls("invoices")

    # ------------------------------------------------------------------
    # processed_webhooks (platform-level — no RLS, no tenant_id)
    # ------------------------------------------------------------------
    op.create_table(
        "processed_webhooks",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("provider", "event_id"),
    )

    # ------------------------------------------------------------------
    # payment_failure_grace
    # ------------------------------------------------------------------
    op.create_table(
        "payment_failure_grace",
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
        sa.Column(
            "subscription_id",
            PG_UUID,
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("grace_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "reminders_sent",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            f"resolution IS NULL OR resolution IN {GRACE_RESOLUTION_VALUES}",
            name="payment_failure_grace_resolution_check",
        ),
    )
    op.create_index(
        "ix_payment_failure_grace_open",
        "payment_failure_grace",
        ["grace_ends_at"],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_index(
        "uq_payment_failure_grace_one_open_per_sub",
        "payment_failure_grace",
        ["subscription_id"],
        unique=True,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    _enable_rls("payment_failure_grace")

    # ------------------------------------------------------------------
    # Deferred FK from subscriptions.payment_method_id → payment_methods.id
    # ------------------------------------------------------------------
    op.create_foreign_key(
        "subscriptions_payment_method_fk",
        "subscriptions",
        "payment_methods",
        ["payment_method_id"],
        ["id"],
        deferrable=True,
        initially="DEFERRED",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "subscriptions_payment_method_fk",
        "subscriptions",
        type_="foreignkey",
    )

    # payment_failure_grace
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "payment_failure_grace"')
    op.execute('ALTER TABLE "payment_failure_grace" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "payment_failure_grace" DISABLE ROW LEVEL SECURITY')
    op.drop_index(
        "uq_payment_failure_grace_one_open_per_sub",
        table_name="payment_failure_grace",
    )
    op.drop_index(
        "ix_payment_failure_grace_open",
        table_name="payment_failure_grace",
    )
    op.drop_table("payment_failure_grace")

    # processed_webhooks
    op.drop_table("processed_webhooks")

    # invoices
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "invoices"')
    op.execute('ALTER TABLE "invoices" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "invoices" DISABLE ROW LEVEL SECURITY')
    op.drop_index("ix_invoices_status_open", table_name="invoices")
    op.drop_index("ix_invoices_subscription", table_name="invoices")
    op.drop_index("ix_invoices_tenant_period", table_name="invoices")
    op.drop_table("invoices")

    # payment_methods
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "payment_methods"')
    op.execute('ALTER TABLE "payment_methods" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "payment_methods" DISABLE ROW LEVEL SECURITY')
    op.drop_index("ix_payment_methods_default", table_name="payment_methods")
    op.drop_index("ix_payment_methods_tenant_workspace", table_name="payment_methods")
    op.drop_table("payment_methods")


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
