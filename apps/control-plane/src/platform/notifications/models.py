from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class DeliveryMethod(StrEnum):
    in_app = "in_app"
    email = "email"
    webhook = "webhook"


class DeliveryOutcome(StrEnum):
    success = "success"
    failed = "failed"
    timed_out = "timed_out"
    fallback = "fallback"


class UserAlertSettings(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_alert_settings"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    state_transitions: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: [
            "working_to_pending",
            "any_to_complete",
            "any_to_failed",
        ],
        server_default=text(
            """'[\"working_to_pending\",\"any_to_complete\",\"any_to_failed\"]'::jsonb"""
        ),
    )
    delivery_method: Mapped[DeliveryMethod] = mapped_column(
        SAEnum(DeliveryMethod, name="deliverymethod"),
        nullable=False,
        default=DeliveryMethod.in_app,
        server_default=text("'in_app'"),
    )
    webhook_url: Mapped[str | None] = mapped_column(String(length=512), nullable=True)


class UserAlert(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_alerts"
    __table_args__ = (
        Index(
            "idx_user_alerts_user_unread",
            "user_id",
            "created_at",
            "id",
            postgresql_where=text("NOT read"),
        ),
        Index("idx_user_alerts_user_created", "user_id", "created_at", "id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    interaction_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("interactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_reference: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="medium",
        server_default=text("'medium'"),
    )
    read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    delivery_outcome: Mapped[AlertDeliveryOutcome | None] = relationship(
        "platform.notifications.models.AlertDeliveryOutcome",
        back_populates="alert",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class AlertDeliveryOutcome(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "alert_delivery_outcomes"

    alert_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user_alerts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    delivery_method: Mapped[DeliveryMethod] = mapped_column(
        SAEnum(DeliveryMethod, name="deliverymethod"),
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    outcome: Mapped[DeliveryOutcome | None] = mapped_column(
        SAEnum(DeliveryOutcome, name="deliveryoutcome"),
        nullable=True,
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)

    alert: Mapped[UserAlert] = relationship(
        "platform.notifications.models.UserAlert",
        back_populates="delivery_outcome",
    )
