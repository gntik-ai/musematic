from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class DeliveryMethod(StrEnum):
    in_app = "in_app"
    email = "email"
    webhook = "webhook"
    slack = "slack"
    teams = "teams"
    sms = "sms"


class DeliveryOutcome(StrEnum):
    success = "success"
    failed = "failed"
    timed_out = "timed_out"
    fallback = "fallback"


class WebhookDeliveryStatus(StrEnum):
    pending = "pending"
    delivering = "delivering"
    delivered = "delivered"
    failed = "failed"
    dead_letter = "dead_letter"


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
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    alert: Mapped[UserAlert] = relationship(
        "platform.notifications.models.UserAlert",
        back_populates="delivery_outcome",
    )


class NotificationChannelConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "notification_channel_configs"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "channel_type",
            "target",
            name="uq_notification_channel_configs_user_channel_target",
        ),
        Index("idx_channel_configs_user_enabled", "user_id", "enabled"),
        Index(
            "idx_channel_configs_user_type_active",
            "user_id",
            "channel_type",
            postgresql_where=text("enabled AND verified_at IS NOT NULL"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_type: Mapped[DeliveryMethod] = mapped_column(
        SAEnum(DeliveryMethod, name="deliverymethod"),
        nullable=False,
    )
    target: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    signing_secret_ref: Mapped[str | None] = mapped_column(String(length=256), nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_token_hash: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    verification_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    quiet_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    alert_type_filter: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    severity_floor: Mapped[str | None] = mapped_column(String(length=16), nullable=True)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class OutboundWebhook(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "outbound_webhooks"
    __table_args__ = (
        Index("idx_outbound_webhooks_workspace_active", "workspace_id", "active"),
        Index("idx_outbound_webhooks_workspace", "workspace_id"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(length=120), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    event_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    signing_secret_ref: Mapped[str] = mapped_column(String(length=256), nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    retry_policy: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "max_retries": 3,
            "backoff_seconds": [60, 300, 1800],
            "total_window_seconds": 86_400,
        },
    )
    region_pinned_to: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    deliveries: Mapped[list[WebhookDelivery]] = relationship(
        "platform.notifications.models.WebhookDelivery",
        back_populates="webhook",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class WebhookDelivery(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index(
            "uq_webhook_deliveries_webhook_idempotency_original",
            "webhook_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("replayed_from IS NULL"),
        ),
        Index("idx_webhook_deliveries_status_next_attempt", "status", "next_attempt_at"),
        Index(
            "idx_webhook_deliveries_workspace_dlq",
            "webhook_id",
            "dead_lettered_at",
            postgresql_where=text("status = 'dead_letter'"),
        ),
    )

    webhook_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("outbound_webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(length=96), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(length=16),
        nullable=False,
        default=WebhookDeliveryStatus.pending.value,
        server_default=text("'pending'"),
    )
    failure_reason: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    replayed_from: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("webhook_deliveries.id", ondelete="SET NULL"),
        nullable=True,
    )
    replayed_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    webhook: Mapped[OutboundWebhook] = relationship(
        "platform.notifications.models.OutboundWebhook",
        back_populates="deliveries",
    )
