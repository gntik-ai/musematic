from __future__ import annotations

from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TenantScopedMixin, TimestampMixin, UUIDMixin
from uuid import UUID

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class VerdictType(StrEnum):
    COMPLIANT = "COMPLIANT"
    WARNING = "WARNING"
    VIOLATION = "VIOLATION"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"


class ActionType(StrEnum):
    block = "block"
    quarantine = "quarantine"
    notify = "notify"
    revoke_cert = "revoke_cert"
    log_and_continue = "log_and_continue"


TERMINAL_VERDICT_TYPES: frozenset[VerdictType] = frozenset(
    {VerdictType.VIOLATION, VerdictType.ESCALATE_TO_HUMAN}
)


class GovernanceVerdict(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "governance_verdicts"
    __table_args__ = (
        Index("ix_governance_verdicts_workspace_id", "workspace_id"),
        Index("ix_governance_verdicts_fleet_id", "fleet_id"),
        Index("ix_governance_verdicts_verdict_type", "verdict_type"),
        Index("ix_governance_verdicts_created_at", "created_at"),
    )

    judge_agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    verdict_type: Mapped[VerdictType] = mapped_column(
        SAEnum(VerdictType, name="verdicttype", create_type=False),
        nullable=False,
    )
    policy_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("policy_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    rationale: Mapped[str] = mapped_column(Text(), nullable=False)
    recommended_action: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    source_event_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    fleet_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("fleets.id", ondelete="SET NULL"),
        nullable=True,
    )
    workspace_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    enforcement_actions: Mapped[list[EnforcementAction]] = relationship(
        "platform.governance.models.EnforcementAction",
        back_populates="verdict",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class EnforcementAction(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "enforcement_actions"
    __table_args__ = (
        Index("ix_enforcement_actions_verdict_id", "verdict_id"),
        Index("ix_enforcement_actions_action_type", "action_type"),
        Index("ix_enforcement_actions_workspace_id", "workspace_id"),
        Index("ix_enforcement_actions_created_at", "created_at"),
    )

    enforcer_agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    verdict_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("governance_verdicts.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[ActionType] = mapped_column(
        SAEnum(ActionType, name="enforcementactiontype", create_type=False),
        nullable=False,
    )
    target_agent_fqn: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    outcome: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    workspace_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    verdict: Mapped[GovernanceVerdict] = relationship(
        "platform.governance.models.GovernanceVerdict",
        back_populates="enforcement_actions",
        lazy="noload",
    )
