"""Status page persistence models for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy import (
    UUID as SQLUUID,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

JSONBType = postgresql.JSONB(astext_type=Text())


class PlatformOverallState(StrEnum):
    operational = "operational"
    degraded = "degraded"
    partial_outage = "partial_outage"
    full_outage = "full_outage"
    maintenance = "maintenance"


class PlatformStatusSourceKind(StrEnum):
    kafka = "kafka"
    poll = "poll"
    fallback = "fallback"
    manual = "manual"


class StatusSubscriptionChannel(StrEnum):
    email = "email"
    rss = "rss"
    atom = "atom"
    webhook = "webhook"
    slack = "slack"


class StatusSubscriptionHealth(StrEnum):
    pending = "pending"
    healthy = "healthy"
    unhealthy = "unhealthy"
    unsubscribed = "unsubscribed"


STATUS_SUBSCRIPTION_PENDING = StatusSubscriptionHealth.pending.value
STATUS_SUBSCRIPTION_HEALTHY = StatusSubscriptionHealth.healthy.value
STATUS_SUBSCRIPTION_UNHEALTHY = StatusSubscriptionHealth.unhealthy.value
STATUS_SUBSCRIPTION_UNSUBSCRIBED = StatusSubscriptionHealth.unsubscribed.value


class SubscriptionDispatchOutcome(StrEnum):
    sent = "sent"
    retrying = "retrying"
    dead_lettered = "dead_lettered"
    dropped = "dropped"


STATUS_EVENT_KINDS = (
    "incident.created",
    "incident.updated",
    "incident.resolved",
    "maintenance.scheduled",
    "maintenance.started",
    "maintenance.ended",
    "component.degraded",
    "component.recovered",
)


def _values(values: type[StrEnum] | tuple[str, ...]) -> str:
    iterable = tuple(item.value for item in values) if isinstance(values, type) else values
    return ",".join(f"'{value}'" for value in iterable)


class PlatformStatusSnapshot(Base, UUIDMixin):
    __tablename__ = "platform_status_snapshots"
    __table_args__ = (
        Index(
            "IX_platform_status_snapshots_generated_at_desc",
            text("generated_at DESC"),
        ),
        Index(
            "IX_platform_status_snapshots_non_operational",
            "overall_state",
            postgresql_where=text("overall_state != 'operational'"),
        ),
        CheckConstraint(
            f"overall_state IN ({_values(PlatformOverallState)})",
            name="CK_platform_status_snapshots_overall_state",
        ),
        CheckConstraint(
            f"source_kind IN ({_values(PlatformStatusSourceKind)})",
            name="CK_platform_status_snapshots_source_kind",
        ),
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    overall_state: Mapped[str] = mapped_column(String(length=32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONBType,
        nullable=False,
        default=dict,
    )
    source_kind: Mapped[str] = mapped_column(String(length=32), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class StatusSubscription(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "status_subscriptions"
    __table_args__ = (
        Index("IX_status_subscriptions_user_id", "user_id"),
        Index("IX_status_subscriptions_workspace_id", "workspace_id"),
        Index(
            "UQ_status_subscriptions_channel_target_confirmed",
            "channel",
            "target",
            unique=True,
            postgresql_where=text("confirmed_at IS NOT NULL"),
        ),
        CheckConstraint(
            f"channel IN ({_values(StatusSubscriptionChannel)})",
            name="CK_status_subscriptions_channel",
        ),
        CheckConstraint(
            f"health IN ({_values(StatusSubscriptionHealth)})",
            name="CK_status_subscriptions_health",
        ),
    )

    channel: Mapped[str] = mapped_column(String(length=16), nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    scope_components: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(Text()),
        nullable=False,
        default=list,
    )
    confirmation_token_hash: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health: Mapped[str] = mapped_column(
        String(length=16),
        nullable=False,
        default=STATUS_SUBSCRIPTION_PENDING,
    )
    workspace_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    webhook_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("outbound_webhooks.id", ondelete="CASCADE"),
        nullable=True,
    )


class SubscriptionDispatch(Base, UUIDMixin):
    __tablename__ = "subscription_dispatches"
    __table_args__ = (
        Index(
            "IX_subscription_dispatches_subscription_id_dispatched_at",
            "subscription_id",
            text("dispatched_at DESC"),
        ),
        Index(
            "IX_subscription_dispatches_event_kind_dispatched_at",
            "event_kind",
            text("dispatched_at DESC"),
        ),
        CheckConstraint(
            f"event_kind IN ({_values(STATUS_EVENT_KINDS)})",
            name="CK_subscription_dispatches_event_kind",
        ),
        CheckConstraint(
            f"outcome IN ({_values(SubscriptionDispatchOutcome)})",
            name="CK_subscription_dispatches_outcome",
        ),
    )

    subscription_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("status_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_kind: Mapped[str] = mapped_column(String(length=48), nullable=False)
    event_id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), nullable=False)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(length=16), nullable=False)
    webhook_signature_kid: Mapped[str | None] = mapped_column(
        String(length=64),
        nullable=True,
    )
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
