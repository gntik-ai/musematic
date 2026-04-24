from __future__ import annotations

from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class RateLimitPrincipalType(StrEnum):
    user = "user"
    service_account = "service_account"
    external_a2a = "external_a2a"


class SubscriptionTier(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "api_subscription_tiers"
    __table_args__ = (
        UniqueConstraint("name", name="uq_api_subscription_tiers_name"),
        CheckConstraint("requests_per_minute > 0", name="ck_api_subscription_tiers_rpm_positive"),
        CheckConstraint("requests_per_hour > 0", name="ck_api_subscription_tiers_rph_positive"),
        CheckConstraint("requests_per_day > 0", name="ck_api_subscription_tiers_rpd_positive"),
    )

    name: Mapped[str] = mapped_column(String(length=32), nullable=False)
    requests_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    requests_per_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    requests_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    rate_limit_configs: Mapped[list[RateLimitConfig]] = relationship(
        back_populates="subscription_tier",
        cascade="all, delete-orphan",
    )


class RateLimitConfig(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "api_rate_limits"
    __table_args__ = (
        UniqueConstraint("principal_type", "principal_id", name="uq_api_rate_limits_principal"),
        CheckConstraint(
            "principal_type IN ('user', 'service_account', 'external_a2a')",
            name="ck_api_rate_limits_principal_type",
        ),
        CheckConstraint(
            "requests_per_minute_override IS NULL OR requests_per_minute_override > 0",
            name="ck_api_rate_limits_rpm_override_positive",
        ),
        CheckConstraint(
            "requests_per_hour_override IS NULL OR requests_per_hour_override > 0",
            name="ck_api_rate_limits_rph_override_positive",
        ),
        CheckConstraint(
            "requests_per_day_override IS NULL OR requests_per_day_override > 0",
            name="ck_api_rate_limits_rpd_override_positive",
        ),
    )

    principal_type: Mapped[RateLimitPrincipalType] = mapped_column(
        String(length=32), nullable=False
    )
    principal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    subscription_tier_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("api_subscription_tiers.id"),
        nullable=False,
        index=True,
    )
    requests_per_minute_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requests_per_hour_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requests_per_day_override: Mapped[int | None] = mapped_column(Integer, nullable=True)

    subscription_tier: Mapped[SubscriptionTier] = relationship(back_populates="rate_limit_configs")
