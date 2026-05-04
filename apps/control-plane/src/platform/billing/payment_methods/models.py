"""SQLAlchemy model for the ``payment_methods`` table (UPD-052 / migration 114)."""

from __future__ import annotations

from datetime import datetime
from platform.common.models.base import Base
from platform.common.models.mixins import TenantScopedMixin, UUIDMixin
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class PaymentMethod(Base, UUIDMixin, TenantScopedMixin):
    """Local mirror of a Stripe payment method.

    Tenant-scoped (RLS). One row per Stripe ``pm_*`` id. ``workspace_id`` is
    NULL for tenant-level (Enterprise) payment methods and set for default-
    tenant workspace payment methods.
    """

    __tablename__ = "payment_methods"
    __table_args__ = (
        Index(
            "ix_payment_methods_tenant_workspace",
            "tenant_id",
            "workspace_id",
        ),
        Index(
            "ix_payment_methods_default",
            "tenant_id",
            "workspace_id",
            postgresql_where=text("is_default = true"),
        ),
    )

    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    stripe_payment_method_id: Mapped[str] = mapped_column(
        String(length=64),
        nullable=False,
        unique=True,
    )
    brand: Mapped[str | None] = mapped_column(String(length=32), nullable=True)
    last4: Mapped[str | None] = mapped_column(String(length=4), nullable=True)
    exp_month: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    exp_year: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        server_default=text("false"),
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
