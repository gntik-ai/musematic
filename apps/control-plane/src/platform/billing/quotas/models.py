from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from platform.common.models import Base, TenantScopedMixin, UUIDMixin
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class UsageRecord(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "usage_records"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "subscription_id",
            "metric",
            "period_start",
            "is_overage",
            name="usage_records_unique_aggregate",
        ),
        CheckConstraint("metric IN ('executions','minutes')", name="ck_usage_records_metric"),
        Index("usage_records_subscription_period_idx", "subscription_id", "period_start", "metric"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    subscription_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric: Mapped[str] = mapped_column(String(length=32), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    is_overage: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )


class OverageAuthorization(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "overage_authorizations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "billing_period_start",
            name="overage_authorizations_workspace_period_unique",
        ),
        Index(
            "overage_authorizations_subscription_period_idx",
            "subscription_id",
            "billing_period_start",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    subscription_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    billing_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    billing_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    authorized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    authorized_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
    max_overage_eur: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class ProcessedEventID(Base):
    __tablename__ = "processed_event_ids"
    __table_args__ = (
        Index("processed_event_ids_consumer_idx", "consumer_name", "processed_at"),
    )

    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    consumer_name: Mapped[str] = mapped_column(String(length=64), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
