from __future__ import annotations

from datetime import datetime
from platform.common.models import Base, TenantScopedMixin, TimestampMixin, UUIDMixin
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class Subscription(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", name="subscriptions_scope_unique"),
        ForeignKeyConstraint(
            ["plan_id", "plan_version"],
            ["plan_versions.plan_id", "plan_versions.version"],
            name="subscriptions_plan_version_fk",
        ),
        CheckConstraint("scope_type IN ('workspace','tenant')", name="ck_subscriptions_scope"),
        CheckConstraint(
            "status IN ('trial','active','past_due','cancellation_pending','canceled','suspended')",
            name="ck_subscriptions_status",
        ),
        Index("subscriptions_tenant_idx", "tenant_id"),
        Index("subscriptions_status_period_end_idx", "status", "current_period_end"),
        Index("subscriptions_plan_version_idx", "plan_id", "plan_version"),
    )

    scope_type: Mapped[str] = mapped_column(String(length=16), nullable=False)
    scope_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("plans.id"),
        nullable=False,
    )
    plan_version: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    payment_method_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
