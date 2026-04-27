from __future__ import annotations

from datetime import datetime
from platform.common.models.base import Base
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class TwoPersonApprovalChallenge(Base):
    __tablename__ = "two_person_auth_requests"

    id: Mapped[UUID] = mapped_column(
        "request_id",
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    action_type: Mapped[str] = mapped_column("action", Text(), nullable=False)
    action_payload: Mapped[dict] = mapped_column(
        "payload",
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    initiator_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    co_signer_id: Mapped[UUID | None] = mapped_column(
        "approved_by_id",
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    consumed: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

    @property
    def status(self) -> str:
        if self.consumed:
            return "consumed"
        if self.rejected_at is not None:
            return "rejected"
        if self.approved_at is not None:
            return "approved"
        return "pending"
