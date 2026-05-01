from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from platform.common.models import Base, UUIDMixin
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class Plan(Base, UUIDMixin):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("tier IN ('free','pro','enterprise')", name="ck_plans_tier"),
        CheckConstraint(
            "allowed_model_tier IN ('cheap_only','standard','all')",
            name="ck_plans_allowed_model_tier",
        ),
        Index("plans_tier_active_idx", "tier", "is_active"),
    )

    slug: Mapped[str] = mapped_column(String(length=32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tier: Mapped[str] = mapped_column(String(length=16), nullable=False)
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    allowed_model_tier: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default="all",
        server_default="all",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class PlanVersion(Base, UUIDMixin):
    __tablename__ = "plan_versions"
    __table_args__ = (
        UniqueConstraint("plan_id", "version", name="plan_versions_plan_version_key"),
        Index(
            "plan_versions_plan_published_idx",
            "plan_id",
            "published_at",
            postgresql_where=text("deprecated_at IS NULL"),
        ),
        CheckConstraint("price_monthly >= 0", name="ck_plan_versions_price_nonnegative"),
        CheckConstraint(
            "executions_per_day >= 0 AND executions_per_month >= 0 "
            "AND minutes_per_day >= 0 AND minutes_per_month >= 0 "
            "AND max_workspaces >= 0 AND max_agents_per_workspace >= 0 "
            "AND max_users_per_workspace >= 0 AND trial_days >= 0",
            name="ck_plan_versions_quotas_nonnegative",
        ),
        CheckConstraint(
            "overage_price_per_minute >= 0",
            name="ck_plan_versions_overage_price_nonnegative",
        ),
        CheckConstraint(
            "quota_period_anchor IN ('calendar_month','subscription_anniversary')",
            name="ck_plan_versions_quota_period_anchor",
        ),
    )

    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(nullable=False)
    price_monthly: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    executions_per_day: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    executions_per_month: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
    )
    minutes_per_day: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    minutes_per_month: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    max_workspaces: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    max_agents_per_workspace: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
    )
    max_users_per_workspace: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
    )
    overage_price_per_minute: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=4),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    trial_days: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    quota_period_anchor: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default="calendar_month",
        server_default="calendar_month",
    )
    extras_json: Mapped[dict[str, object]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
