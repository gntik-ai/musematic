from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class RecommendationType(StrEnum):
    collaborative = "collaborative"
    content_based = "content_based"
    popularity_fallback = "popularity_fallback"


class MarketplaceAgentRating(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "marketplace_agent_ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", name="uq_marketplace_rating_user_agent"),
        CheckConstraint("score >= 1 AND score <= 5", name="ck_marketplace_rating_score_range"),
        Index("ix_marketplace_agent_ratings_agent_id", "agent_id"),
        Index("ix_marketplace_agent_ratings_user_id", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[UUID] = mapped_column(nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    review_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class MarketplaceQualityAggregate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "marketplace_quality_aggregates"
    __table_args__ = (Index("uq_marketplace_quality_aggregates_agent_id", "agent_id", unique=True),)

    agent_id: Mapped[UUID] = mapped_column(nullable=False)
    has_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    execution_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    self_correction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_score_sum: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=4),
        nullable=False,
        default=Decimal("0"),
    )
    quality_score_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    satisfaction_sum: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=4),
        nullable=False,
        default=Decimal("0"),
    )
    satisfaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    certification_status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default="uncertified",
    )
    data_source_last_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    source_unavailable_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.execution_count, 1)

    @property
    def self_correction_rate(self) -> float:
        return self.self_correction_count / max(self.execution_count, 1)

    @property
    def quality_score_avg(self) -> float:
        return float(self.quality_score_sum or 0) / max(self.quality_score_count, 1)

    @property
    def satisfaction_avg(self) -> float:
        return float(self.satisfaction_sum or 0) / max(self.satisfaction_count, 1)


class MarketplaceRecommendation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "marketplace_recommendations"
    __table_args__ = (
        Index("ix_marketplace_recommendations_user_id", "user_id"),
        Index("ix_marketplace_recommendations_expires_at", "expires_at"),
        Index(
            "ix_marketplace_recommendations_user_type",
            "user_id",
            "recommendation_type",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[UUID] = mapped_column(nullable=False)
    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    recommendation_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=6), nullable=False)
    reasoning: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketplaceTrendingSnapshot(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "marketplace_trending_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "agent_id",
            name="uq_marketplace_trending_date_agent",
        ),
        Index(
            "ix_marketplace_trending_date_rank",
            "snapshot_date",
            "rank",
        ),
    )

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    agent_id: Mapped[UUID] = mapped_column(nullable=False)
    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    trending_score: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=6), nullable=False)
    growth_rate: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=4), nullable=False)
    invocations_this_week: Mapped[int] = mapped_column(Integer, nullable=False)
    invocations_last_week: Mapped[int] = mapped_column(Integer, nullable=False)
    trending_reason: Mapped[str] = mapped_column(String(length=256), nullable=False)
    satisfaction_delta: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=6, scale=4),
        nullable=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

