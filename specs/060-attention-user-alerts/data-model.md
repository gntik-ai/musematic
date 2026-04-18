# Data Model: Attention Pattern and Configurable User Alerts (Feature 060)

**Migration**: `047_notifications_alerts.py`  
`down_revision = "046_workspace_goal_lifecycle_and_decision"`

---

## 1. Alembic Migration DDL

```sql
-- Enums

CREATE TYPE deliverymethod AS ENUM ('in_app', 'email', 'webhook');

CREATE TYPE deliveryoutcome AS ENUM ('success', 'failed', 'timed_out', 'fallback');

-- Table: user_alert_settings
-- One record per user. Default values applied when no record exists.

CREATE TABLE user_alert_settings (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    state_transitions JSONB  NOT NULL DEFAULT '["working_to_pending","any_to_complete","any_to_failed"]',
    delivery_method   deliverymethod NOT NULL DEFAULT 'in_app',
    webhook_url VARCHAR(512),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_alert_settings_user UNIQUE (user_id)
);

-- Table: user_alerts
-- Immutable record produced when a qualifying event occurs.
-- Only `read` mutates after creation.

CREATE TABLE user_alerts (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    interaction_id   UUID        REFERENCES interactions(id) ON DELETE SET NULL,
    source_reference JSONB,      -- {"type": "attention_request"|"state_change", "id": "uuid"}
    alert_type       VARCHAR(64) NOT NULL,   -- "attention_request" | "state_change"
    title            VARCHAR(256) NOT NULL,
    body             TEXT,
    urgency          VARCHAR(32) NOT NULL DEFAULT 'medium',
    read             BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_alerts_user_unread
    ON user_alerts (user_id, created_at DESC)
    WHERE NOT read;

CREATE INDEX idx_user_alerts_user_created
    ON user_alerts (user_id, created_at DESC);

-- Table: alert_delivery_outcomes
-- Tracks delivery attempt state for email and webhook deliveries.
-- In-app delivery is fire-and-forget (no retry tracking needed).

CREATE TABLE alert_delivery_outcomes (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id        UUID          NOT NULL REFERENCES user_alerts(id) ON DELETE CASCADE,
    delivery_method deliverymethod NOT NULL,
    attempt_count   INTEGER       NOT NULL DEFAULT 1,
    outcome         deliveryoutcome,       -- NULL while pending/in-flight
    next_retry_at   TIMESTAMPTZ,           -- NULL when not scheduled for retry
    error_detail    TEXT,
    delivered_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_alert_delivery_outcomes_alert UNIQUE (alert_id)
);
```

---

## 2. SQLAlchemy Models (`notifications/models.py`)

```python
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin


class DeliveryMethod(StrEnum):
    IN_APP  = "in_app"
    EMAIL   = "email"
    WEBHOOK = "webhook"


class DeliveryOutcome(StrEnum):
    SUCCESS   = "success"
    FAILED    = "failed"
    TIMED_OUT = "timed_out"
    FALLBACK  = "fallback"


class UserAlertSettings(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_alert_settings"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    state_transitions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False,
        default=lambda: ["working_to_pending", "any_to_complete", "any_to_failed"],
    )
    delivery_method: Mapped[DeliveryMethod] = mapped_column(
        SAEnum(DeliveryMethod, name="deliverymethod"), nullable=False, default=DeliveryMethod.IN_APP
    )
    webhook_url: Mapped[str | None] = mapped_column(String(512))


class UserAlert(Base, UUIDMixin):
    __tablename__ = "user_alerts"
    __table_args__ = (
        Index("idx_user_alerts_user_unread", "user_id", "created_at",
              postgresql_where="NOT read"),
        Index("idx_user_alerts_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    interaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interactions.id", ondelete="SET NULL"), nullable=True
    )
    source_reference: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    urgency: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    delivery_outcome: Mapped[AlertDeliveryOutcome | None] = relationship(
        "AlertDeliveryOutcome", back_populates="alert", uselist=False, lazy="select"
    )


class AlertDeliveryOutcome(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "alert_delivery_outcomes"

    alert_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_alerts.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    delivery_method: Mapped[DeliveryMethod] = mapped_column(
        SAEnum(DeliveryMethod, name="deliverymethod"), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    outcome: Mapped[DeliveryOutcome | None] = mapped_column(
        SAEnum(DeliveryOutcome, name="deliveryoutcome"), nullable=True
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)

    alert: Mapped[UserAlert] = relationship(
        "UserAlert", back_populates="delivery_outcome"
    )
```

---

## 3. Pydantic Schemas (`notifications/schemas.py`)

```python
class UserAlertSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    state_transitions: list[str]
    delivery_method: DeliveryMethod
    webhook_url: str | None
    created_at: datetime
    updated_at: datetime

class UserAlertSettingsUpdate(BaseModel):
    state_transitions: list[str] = Field(min_length=1)
    delivery_method: DeliveryMethod
    webhook_url: str | None = None

    @model_validator(mode="after")
    def _webhook_requires_url(self) -> "UserAlertSettingsUpdate":
        if self.delivery_method == DeliveryMethod.WEBHOOK and not self.webhook_url:
            raise ValueError("webhook_url is required when delivery_method is webhook")
        return self

class UserAlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    alert_type: str
    title: str
    body: str | None
    urgency: str
    read: bool
    interaction_id: UUID | None
    source_reference: dict[str, Any] | None
    created_at: datetime

class AlertDeliveryOutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    delivery_method: DeliveryMethod
    attempt_count: int
    outcome: DeliveryOutcome | None
    error_detail: str | None
    next_retry_at: datetime | None
    delivered_at: datetime | None

class UserAlertDetail(UserAlertRead):
    delivery_outcome: AlertDeliveryOutcomeRead | None

class AlertListResponse(BaseModel):
    items: list[UserAlertRead]
    next_cursor: str | None
    total_unread: int

class UnreadCountResponse(BaseModel):
    count: int
```

---

## 4. Modified: interactions/events.py

**Add to `InteractionsEventType` enum** (additive):
```python
state_changed = "interaction.state_changed"
```

**Add new payload class**:
```python
class InteractionStateChangedPayload(BaseModel):
    interaction_id: UUID
    workspace_id: UUID
    from_state: str   # e.g., "running"
    to_state: str     # e.g., "waiting", "completed", "failed"
    occurred_at: datetime

async def publish_interaction_state_changed(
    producer: EventProducer | None,
    payload: InteractionStateChangedPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    await _publish(
        producer=producer,
        topic="interaction.events",
        event_type=InteractionsEventType.state_changed,
        key=str(payload.interaction_id),
        payload=payload,
        correlation_ctx=correlation_ctx,
    )
```

**Add `context_summary` to `AttentionRequestedPayload`** (additive, optional):
```python
class AttentionRequestedPayload(BaseModel):
    request_id: UUID
    workspace_id: UUID
    source_agent_fqn: str
    target_identity: str
    urgency: AttentionUrgency
    context_summary: str | None = None   # NEW — from AttentionRequest.context_summary
    related_interaction_id: UUID | None
    related_goal_id: UUID | None
```

---

## 5. New Kafka Topic

| Topic | Key | Producer | Consumer |
|---|---|---|---|
| `notifications.alerts` | `user_id` | notifications service | ws_hub (alerts channel) |

---

## 6. Transition Pattern Matching

State alias table in `notifications/service.py`:

```python
_STATE_ALIASES: dict[str, str] = {
    "working": "running",
    "pending": "waiting",
    "complete": "completed",
}

def _resolve(name: str) -> str:
    return _STATE_ALIASES.get(name, name)

def matches_transition_pattern(pattern: str, from_state: str, to_state: str) -> bool:
    if pattern.startswith("any_to_"):
        return _resolve(pattern[len("any_to_"):]) == to_state
    parts = pattern.split("_to_", 1)
    if len(parts) == 2:
        return _resolve(parts[0]) == from_state and _resolve(parts[1]) == to_state
    return False
```
