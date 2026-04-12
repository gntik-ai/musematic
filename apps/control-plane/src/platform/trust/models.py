from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import AuditMixin, TimestampMixin, UUIDMixin
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class CertificationStatus(StrEnum):
    pending = "pending"
    active = "active"
    expired = "expired"
    revoked = "revoked"
    superseded = "superseded"


class EvidenceType(StrEnum):
    package_validation = "package_validation"
    test_results = "test_results"
    policy_check = "policy_check"
    guardrail_outcomes = "guardrail_outcomes"
    behavioral_regression = "behavioral_regression"
    ate_results = "ate_results"


class TrustTierName(StrEnum):
    certified = "certified"
    provisional = "provisional"
    untrusted = "untrusted"


class RecertificationTriggerType(StrEnum):
    revision_changed = "revision_changed"
    policy_changed = "policy_changed"
    expiry_approaching = "expiry_approaching"
    conformance_failed = "conformance_failed"


class RecertificationTriggerStatus(StrEnum):
    pending = "pending"
    processed = "processed"
    deduplicated = "deduplicated"


class GuardrailLayer(StrEnum):
    input_sanitization = "input_sanitization"
    prompt_injection = "prompt_injection"
    output_moderation = "output_moderation"
    tool_control = "tool_control"
    memory_write = "memory_write"
    action_commit = "action_commit"


class OJEVerdictType(StrEnum):
    compliant = "COMPLIANT"
    warning = "WARNING"
    violation = "VIOLATION"
    escalate_to_human = "ESCALATE_TO_HUMAN"


class TrustCertification(Base, UUIDMixin, TimestampMixin, AuditMixin):
    __tablename__ = "trust_certifications"
    __table_args__ = (
        Index("ix_trust_certifications_agent_id", "agent_id"),
        Index("ix_trust_certifications_agent_status", "agent_id", "status"),
        Index("ix_trust_certifications_revision", "agent_revision_id"),
    )

    agent_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    agent_revision_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    status: Mapped[CertificationStatus] = mapped_column(
        SAEnum(CertificationStatus, name="trust_certification_status"),
        nullable=False,
        default=CertificationStatus.pending,
    )
    issued_by: Mapped[str] = mapped_column(String(length=255), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    superseded_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trust_certifications.id", ondelete="SET NULL"),
        nullable=True,
    )

    evidence_refs: Mapped[list[TrustCertificationEvidenceRef]] = relationship(
        "platform.trust.models.TrustCertificationEvidenceRef",
        back_populates="certification",
        cascade="all, delete-orphan",
        order_by="platform.trust.models.TrustCertificationEvidenceRef.created_at.asc()",
    )


class TrustCertificationEvidenceRef(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_certification_evidence_refs"
    __table_args__ = (
        Index("ix_trust_certification_evidence_refs_certification_id", "certification_id"),
        Index(
            "ix_trust_certification_evidence_refs_source_ref", "source_ref_type", "source_ref_id"
        ),
    )

    certification_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trust_certifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_type: Mapped[EvidenceType] = mapped_column(
        SAEnum(EvidenceType, name="trust_evidence_type"),
        nullable=False,
    )
    source_ref_type: Mapped[str] = mapped_column(String(length=255), nullable=False)
    source_ref_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    storage_ref: Mapped[str | None] = mapped_column(String(length=1024), nullable=True)

    certification: Mapped[TrustCertification] = relationship(
        "platform.trust.models.TrustCertification",
        back_populates="evidence_refs",
    )


class TrustTier(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_tiers"
    __table_args__ = (
        Index("uq_trust_tiers_agent_id", "agent_id", unique=True),
        Index("ix_trust_tiers_tier", "tier"),
    )

    agent_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    tier: Mapped[TrustTierName] = mapped_column(
        SAEnum(TrustTierName, name="trust_tier_name"),
        nullable=False,
        default=TrustTierName.untrusted,
    )
    trust_score: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=4),
        nullable=False,
        default=Decimal("0.0000"),
    )
    certification_component: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=4),
        nullable=False,
        default=Decimal("0.0000"),
    )
    guardrail_component: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=4),
        nullable=False,
        default=Decimal("0.0000"),
    )
    behavioral_component: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=4),
        nullable=False,
        default=Decimal("0.0000"),
    )
    last_computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TrustSignal(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_signals"
    __table_args__ = (
        Index("ix_trust_signals_agent_id", "agent_id"),
        Index("ix_trust_signals_agent_type", "agent_id", "signal_type"),
        Index("ix_trust_signals_source", "source_type", "source_id"),
    )

    agent_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(length=128), nullable=False)
    score_contribution: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=4), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(length=128), nullable=False)
    source_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)

    proof_links: Mapped[list[TrustProofLink]] = relationship(
        "platform.trust.models.TrustProofLink",
        back_populates="signal",
        cascade="all, delete-orphan",
        order_by="platform.trust.models.TrustProofLink.created_at.asc()",
    )


class TrustProofLink(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_proof_links"
    __table_args__ = (
        Index("ix_trust_proof_links_signal_id", "signal_id"),
        Index("ix_trust_proof_links_reference", "proof_reference_type", "proof_reference_id"),
    )

    signal_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trust_signals.id", ondelete="CASCADE"),
        nullable=False,
    )
    proof_type: Mapped[str] = mapped_column(String(length=128), nullable=False)
    proof_reference_type: Mapped[str] = mapped_column(String(length=128), nullable=False)
    proof_reference_id: Mapped[str] = mapped_column(String(length=255), nullable=False)

    signal: Mapped[TrustSignal] = relationship(
        "platform.trust.models.TrustSignal",
        back_populates="proof_links",
    )


class TrustRecertificationTrigger(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_recertification_triggers"
    __table_args__ = (Index("ix_trust_recertification_triggers_agent_id", "agent_id"),)

    agent_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    agent_revision_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    trigger_type: Mapped[RecertificationTriggerType] = mapped_column(
        SAEnum(RecertificationTriggerType, name="trust_recertification_trigger_type"),
        nullable=False,
    )
    originating_event_type: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    originating_event_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    original_certification_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trust_certifications.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[RecertificationTriggerStatus] = mapped_column(
        SAEnum(RecertificationTriggerStatus, name="trust_recertification_trigger_status"),
        nullable=False,
        default=RecertificationTriggerStatus.pending,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_certification_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trust_certifications.id", ondelete="SET NULL"),
        nullable=True,
    )


cast(Any, TrustRecertificationTrigger.__table__).append_constraint(
    Index(
        "uq_trust_recertification_trigger_pending",
        TrustRecertificationTrigger.__table__.c.agent_id,
        TrustRecertificationTrigger.__table__.c.agent_revision_id,
        TrustRecertificationTrigger.__table__.c.trigger_type,
        unique=True,
        postgresql_where=TrustRecertificationTrigger.__table__.c.status == "pending",
    )
)


class TrustBlockedActionRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_blocked_action_records"
    __table_args__ = (
        Index("ix_trust_blocked_action_records_agent_id", "agent_id"),
        Index("ix_trust_blocked_action_records_execution_id", "execution_id"),
        Index("ix_trust_blocked_action_records_workspace_id", "workspace_id"),
        Index("ix_trust_blocked_action_records_agent_layer", "agent_id", "layer"),
    )

    agent_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    layer: Mapped[GuardrailLayer] = mapped_column(
        SAEnum(GuardrailLayer, name="trust_guardrail_layer"),
        nullable=False,
    )
    policy_basis: Mapped[str] = mapped_column(String(length=255), nullable=False)
    policy_basis_detail: Mapped[str | None] = mapped_column(Text(), nullable=True)
    input_context_hash: Mapped[str] = mapped_column(String(length=64), nullable=False)
    input_context_preview: Mapped[str | None] = mapped_column(String(length=500), nullable=True)
    execution_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    interaction_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)


class TrustATEConfiguration(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_ate_configurations"
    __table_args__ = (
        Index("ix_trust_ate_configurations_workspace_id", "workspace_id"),
        Index("ix_trust_ate_configurations_active", "workspace_id", "is_active"),
        Index(
            "uq_trust_ate_configurations_version", "workspace_id", "name", "version", unique=True
        ),
    )

    workspace_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    version: Mapped[int] = mapped_column(Integer(), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    test_scenarios: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    golden_dataset_ref: Mapped[str | None] = mapped_column(String(length=1024), nullable=True)
    scoring_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer(), nullable=False, default=3600)


class TrustGuardrailPipelineConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_guardrail_pipeline_configs"
    __table_args__ = (
        Index("ix_trust_guardrail_pipeline_configs_workspace_id", "workspace_id"),
        Index("ix_trust_guardrail_pipeline_configs_fleet_id", "fleet_id"),
        Index(
            "ix_trust_guardrail_pipeline_configs_workspace_fleet_active",
            "workspace_id",
            "fleet_id",
            "is_active",
        ),
    )

    workspace_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    fleet_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)


class TrustOJEPipelineConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_oje_pipeline_configs"
    __table_args__ = (
        Index("ix_trust_oje_pipeline_configs_workspace_id", "workspace_id"),
        Index("ix_trust_oje_pipeline_configs_fleet_id", "fleet_id"),
        Index(
            "ix_trust_oje_pipeline_configs_workspace_fleet_active",
            "workspace_id",
            "fleet_id",
            "is_active",
        ),
    )

    workspace_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    fleet_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    observer_fqns: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, default=list
    )
    judge_fqns: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, default=list
    )
    enforcer_fqns: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, default=list
    )
    policy_refs: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, default=list
    )
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)


class TrustCircuitBreakerConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_circuit_breaker_configs"
    __table_args__ = (
        Index("ix_trust_circuit_breaker_configs_workspace_id", "workspace_id"),
        Index("ix_trust_circuit_breaker_configs_agent_id", "agent_id"),
        Index("ix_trust_circuit_breaker_configs_fleet_id", "fleet_id"),
    )

    workspace_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    fleet_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    failure_threshold: Mapped[int] = mapped_column(Integer(), nullable=False, default=5)
    time_window_seconds: Mapped[int] = mapped_column(Integer(), nullable=False, default=600)
    tripped_ttl_seconds: Mapped[int] = mapped_column(Integer(), nullable=False, default=3600)
    enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)


class TrustSafetyPreScreenerRuleSet(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_prescreener_rule_sets"
    __table_args__ = (
        Index("uq_trust_prescreener_rule_sets_version", "version", unique=True),
        Index("ix_trust_prescreener_rule_sets_active", "is_active"),
    )

    version: Mapped[int] = mapped_column(Integer(), nullable=False)
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    rules_ref: Mapped[str] = mapped_column(String(length=1024), nullable=False)
    rule_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
