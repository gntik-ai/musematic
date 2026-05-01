from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TenantScopedMixin
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class ActionType(StrEnum):
    workspace_transfer_ownership = "workspace_transfer_ownership"
    tenant_schedule_deletion = "tenant_schedule_deletion"
    tenant_force_cascade_deletion = "tenant_force_cascade_deletion"


class ChallengeStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    consumed = "consumed"
    expired = "expired"


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_cls]


class TwoPersonApprovalChallenge(Base, TenantScopedMixin):
    __tablename__ = "two_person_approval_challenges"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    action_type: Mapped[ActionType] = mapped_column(
        Enum(
            ActionType,
            name="two_person_approval_action_type",
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    action_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    initiator_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    co_signer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[ChallengeStatus] = mapped_column(
        Enum(
            ChallengeStatus,
            name="two_person_approval_challenge_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ChallengeStatus.pending,
        server_default=text("'pending'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def consumed(self) -> bool:
        return self.status == ChallengeStatus.consumed

    @consumed.setter
    def consumed(self, value: bool) -> None:
        if value:
            self.status = ChallengeStatus.consumed
            self.consumed_at = self.consumed_at or datetime.now(UTC)
        elif self.status == ChallengeStatus.consumed:
            self.status = ChallengeStatus.approved if self.approved_at else ChallengeStatus.pending
            self.consumed_at = None
