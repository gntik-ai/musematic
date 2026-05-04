"""SQLAlchemy model for the ``invoices`` table (UPD-052 / migration 114)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from platform.common.models.base import Base
from platform.common.models.mixins import TenantScopedMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class Invoice(Base, UUIDMixin, TenantScopedMixin):
    """Local mirror of a Stripe invoice.

    Tenant-scoped (RLS). One row per Stripe ``in_*`` id. The ``status`` mirrors
    Stripe's invoice lifecycle (draft → open → paid | void | uncollectible).
    """

    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','open','paid','void','uncollectible')",
            name="invoices_status_check",
        ),
        Index(
            "ix_invoices_tenant_period",
            "tenant_id",
            text("period_end DESC"),
        ),
        Index(
            "ix_invoices_subscription",
            "subscription_id",
            text("period_end DESC"),
        ),
        Index(
            "ix_invoices_status_open",
            "tenant_id",
            postgresql_where=text("status = 'open'"),
        ),
    )

    subscription_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    stripe_invoice_id: Mapped[str] = mapped_column(
        String(length=64),
        nullable=False,
        unique=True,
    )
    invoice_number: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    amount_total: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=False,
    )
    amount_subtotal: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=False,
    )
    amount_tax: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=False,
        server_default=text("0"),
        default=Decimal("0"),
    )
    currency: Mapped[str] = mapped_column(
        String(length=3),
        nullable=False,
        server_default=text("'EUR'"),
        default="EUR",
    )
    status: Mapped[str] = mapped_column(String(length=32), nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    pdf_url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
