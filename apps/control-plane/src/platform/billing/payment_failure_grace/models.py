"""SQLAlchemy model for the ``payment_failure_grace`` table (UPD-052)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TenantScopedMixin, UUIDMixin
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class GraceResolution(StrEnum):
    """Resolution states for a closed payment_failure_grace row."""

    payment_recovered = "payment_recovered"
    downgraded_to_free = "downgraded_to_free"
    manually_resolved = "manually_resolved"


class PaymentFailureGrace(Base, UUIDMixin, TenantScopedMixin):
    """Open record while a subscription is in the failed-payment grace window.

    Invariant: at most one open row (``resolved_at IS NULL``) per
    subscription, enforced by the ``uq_payment_failure_grace_one_open_per_sub``
    partial unique index.
    """

    __tablename__ = "payment_failure_grace"
    __table_args__ = (
        CheckConstraint(
            "resolution IS NULL OR resolution IN "
            "('payment_recovered','downgraded_to_free','manually_resolved')",
            name="payment_failure_grace_resolution_check",
        ),
        Index(
            "ix_payment_failure_grace_open",
            "grace_ends_at",
            postgresql_where=text("resolved_at IS NULL"),
        ),
        Index(
            "uq_payment_failure_grace_one_open_per_sub",
            "subscription_id",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )

    subscription_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    grace_ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    reminders_sent: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        server_default=text("0"),
        default=0,
    )
    last_reminder_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolution: Mapped[str | None] = mapped_column(String(length=32), nullable=True)
