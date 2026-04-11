from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from platform.common.models.base import Base
from platform.common.models.mixins import AuditMixin, TimestampMixin, UUIDMixin

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column


class CostModel(Base, UUIDMixin, TimestampMixin, AuditMixin):
    __tablename__ = "analytics_cost_models"
    __table_args__ = (
        Index("ix_analytics_cost_models_model_id_is_active", "model_id", "is_active"),
        Index(
            "uq_analytics_cost_models_model_id_active",
            "model_id",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    model_id: Mapped[str] = mapped_column(String(length=128), nullable=False)
    provider: Mapped[str] = mapped_column(String(length=64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(length=256), nullable=False)
    input_token_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    output_token_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    per_second_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
