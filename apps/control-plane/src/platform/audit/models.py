from __future__ import annotations

from datetime import datetime
from platform.common.models import Base, UUIDMixin
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class AuditChainEntry(Base, UUIDMixin):
    __tablename__ = "audit_chain_entries"
    __table_args__ = (
        UniqueConstraint("sequence_number", name="uq_audit_chain_entries_sequence_number"),
        UniqueConstraint("entry_hash", name="uq_audit_chain_entries_entry_hash"),
        Index("ix_audit_chain_source_time", "audit_event_source", "created_at"),
    )

    sequence_number: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        autoincrement=True,
    )
    previous_hash: Mapped[str] = mapped_column(String(length=64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(length=64), nullable=False, unique=True)
    audit_event_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    audit_event_source: Mapped[str] = mapped_column(String(length=64), nullable=False)
    canonical_payload_hash: Mapped[str] = mapped_column(String(length=64), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(length=100), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(length=50), nullable=True)
    severity: Mapped[str] = mapped_column(String(length=20), nullable=False, default="info")
    canonical_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    impersonation_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
