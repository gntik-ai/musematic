"""SQLAlchemy model for the ``processed_webhooks`` table (UPD-052).

This table is platform-level (not tenant-scoped). The ``(provider, event_id)``
composite primary key is the durable idempotency record — one row per
distinct webhook event the platform has acknowledged. Holds zero customer
data; the row exists purely to enforce "process once."
"""

from __future__ import annotations

from datetime import datetime
from platform.common.models.base import Base

from sqlalchemy import DateTime, PrimaryKeyConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column


class ProcessedWebhook(Base):
    __tablename__ = "processed_webhooks"
    __table_args__ = (
        PrimaryKeyConstraint("provider", "event_id", name="pk_processed_webhooks"),
    )

    provider: Mapped[str] = mapped_column(String(length=32), nullable=False)
    event_id: Mapped[str] = mapped_column(String(length=128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
