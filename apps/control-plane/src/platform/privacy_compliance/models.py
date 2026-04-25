from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class DSRRequestType(StrEnum):
    access = "access"
    rectification = "rectification"
    erasure = "erasure"
    portability = "portability"
    restriction = "restriction"
    objection = "objection"


class DSRStatus(StrEnum):
    received = "received"
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class DLPClassification(StrEnum):
    pii = "pii"
    phi = "phi"
    financial = "financial"
    confidential = "confidential"


class DLPAction(StrEnum):
    redact = "redact"
    block = "block"
    flag = "flag"


class PIAStatus(StrEnum):
    draft = "draft"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"
    superseded = "superseded"


class PIASubjectType(StrEnum):
    agent = "agent"
    workspace = "workspace"
    workflow = "workflow"


class ConsentType(StrEnum):
    ai_interaction = "ai_interaction"
    data_collection = "data_collection"
    training_use = "training_use"


class PrivacyDSRRequest(Base, UUIDMixin):
    __tablename__ = "privacy_dsr_requests"
    __table_args__ = (
        CheckConstraint(
            "request_type IN ('access','rectification','erasure','portability',"
            "'restriction','objection')",
            name="ck_privacy_dsr_request_type",
        ),
        CheckConstraint(
            "status IN ('received','scheduled','in_progress','completed','failed','cancelled')",
            name="ck_privacy_dsr_status",
        ),
        Index("ix_dsr_subject_status", "subject_user_id", "status"),
        Index("ix_dsr_scheduled_release", "status", "scheduled_release_at"),
    )

    subject_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    request_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="received")
    legal_basis: Mapped[str | None] = mapped_column(String(length=256), nullable=True)
    scheduled_release_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completion_proof_hash: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    tombstone_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("privacy_deletion_tombstones.id"),
        nullable=True,
    )


class PrivacyDeletionTombstone(Base, UUIDMixin):
    __tablename__ = "privacy_deletion_tombstones"
    __table_args__ = (
        UniqueConstraint("proof_hash", name="uq_privacy_tombstone_proof_hash"),
        Index("ix_tombstone_subject_hash", "subject_user_id_hash", "salt_version"),
    )

    subject_user_id_hash: Mapped[str] = mapped_column(String(length=64), nullable=False)
    salt_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    entities_deleted: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    cascade_log: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    proof_hash: Mapped[str] = mapped_column(String(length=64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PrivacyResidencyConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "privacy_residency_configs"
    __table_args__ = (UniqueConstraint("workspace_id", name="uq_privacy_residency_workspace"),)

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    region_code: Mapped[str] = mapped_column(String(length=32), nullable=False)
    allowed_transfer_regions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class PrivacyDLPRule(Base, UUIDMixin):
    __tablename__ = "privacy_dlp_rules"
    __table_args__ = (
        CheckConstraint(
            "classification IN ('pii','phi','financial','confidential')",
            name="ck_privacy_dlp_classification",
        ),
        CheckConstraint("action IN ('redact','block','flag')", name="ck_privacy_dlp_action"),
        Index("ix_dlp_rule_ws_enabled", "workspace_id", "enabled"),
    )

    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(length=256), nullable=False)
    classification: Mapped[str] = mapped_column(String(length=32), nullable=False)
    pattern: Mapped[str] = mapped_column(Text(), nullable=False)
    action: Mapped[str] = mapped_column(String(length=32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    seeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PrivacyDLPEvent(Base, UUIDMixin):
    __tablename__ = "privacy_dlp_events"
    __table_args__ = (
        CheckConstraint(
            "action_taken IN ('redact','block','flag')",
            name="ck_privacy_dlp_event_action",
        ),
        Index("ix_dlp_events_by_rule_time", "rule_id", "created_at"),
        Index("ix_dlp_events_by_execution", "execution_id"),
    )

    rule_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("privacy_dlp_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    execution_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    match_summary: Mapped[str] = mapped_column(String(length=128), nullable=False)
    action_taken: Mapped[str] = mapped_column(String(length=32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PrivacyImpactAssessment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "privacy_impact_assessments"
    __table_args__ = (
        CheckConstraint(
            "subject_type IN ('agent','workspace','workflow')",
            name="ck_privacy_pia_subject_type",
        ),
        CheckConstraint(
            "status IN ('draft','under_review','approved','rejected','superseded')",
            name="ck_privacy_pia_status",
        ),
        CheckConstraint("length(legal_basis) >= 10", name="ck_privacy_pia_legal_basis_len"),
        CheckConstraint(
            "approved_by IS NULL OR approved_by != submitted_by",
            name="ck_privacy_pia_approver_differs",
        ),
        Index("ix_pia_by_subject", "subject_type", "subject_id", "status"),
    )

    subject_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    data_categories: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    legal_basis: Mapped[str] = mapped_column(Text(), nullable=False)
    retention_policy: Mapped[str | None] = mapped_column(Text(), nullable=True)
    risks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    mitigations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="draft")
    submitted_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    approved_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_feedback: Mapped[str | None] = mapped_column(Text(), nullable=True)
    superseded_by_pia_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("privacy_impact_assessments.id"),
        nullable=True,
    )


class PrivacyConsentRecord(Base, UUIDMixin):
    __tablename__ = "privacy_consent_records"
    __table_args__ = (
        CheckConstraint(
            "consent_type IN ('ai_interaction','data_collection','training_use')",
            name="ck_privacy_consent_type",
        ),
        UniqueConstraint("user_id", "consent_type", name="uq_privacy_consent_user_type"),
        Index("ix_consent_user_type_revoked", "user_id", "consent_type", "revoked_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    consent_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
