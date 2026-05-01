from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import (
    AuditMixin,
    TenantScopedMixin,
    TimestampMixin,
    UUIDMixin,
    WorkspaceScopedMixin,
)
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class CertificationStatus(StrEnum):
    pending = "pending"
    active = "active"
    expiring = "expiring"
    expired = "expired"
    suspended = "suspended"
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
    pre_screener = "pre_screener"
    input_sanitization = "input_sanitization"
    prompt_injection = "prompt_injection"
    output_moderation = "output_moderation"
    dlp_scan = "dlp_scan"
    tool_control = "tool_control"
    memory_write = "memory_write"
    action_commit = "action_commit"


class OJEVerdictType(StrEnum):
    compliant = "COMPLIANT"
    warning = "WARNING"
    violation = "VIOLATION"
    escalate_to_human = "ESCALATE_TO_HUMAN"


class TrustCertification(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, AuditMixin):
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
    external_certifier_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("certifiers.id", ondelete="SET NULL"),
        nullable=True,
    )
    reassessment_schedule: Mapped[str | None] = mapped_column(String(length=64), nullable=True)

    evidence_refs: Mapped[list[TrustCertificationEvidenceRef]] = relationship(
        "platform.trust.models.TrustCertificationEvidenceRef",
        back_populates="certification",
        cascade="all, delete-orphan",
        order_by="platform.trust.models.TrustCertificationEvidenceRef.created_at.asc()",
    )
    certifier: Mapped[Certifier | None] = relationship(
        "platform.trust.models.Certifier",
        back_populates="certifications",
    )
    reassessment_records: Mapped[list[ReassessmentRecord]] = relationship(
        "platform.trust.models.ReassessmentRecord",
        back_populates="certification",
        cascade="all, delete-orphan",
        order_by="platform.trust.models.ReassessmentRecord.created_at.asc()",
    )
    recertification_requests: Mapped[list[TrustRecertificationRequest]] = relationship(
        "platform.trust.models.TrustRecertificationRequest",
        back_populates="certification",
        cascade="all, delete-orphan",
        order_by="platform.trust.models.TrustRecertificationRequest.created_at.asc()",
    )


class Certifier(Base, UUIDMixin, TimestampMixin, AuditMixin):
    __tablename__ = "certifiers"
    __table_args__ = (Index("ix_certifiers_name", "name"),)

    name: Mapped[str] = mapped_column(String(length=256), nullable=False)
    organization: Mapped[str | None] = mapped_column(String(length=256), nullable=True)
    credentials: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    permitted_scopes: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    certifications: Mapped[list[TrustCertification]] = relationship(
        "platform.trust.models.TrustCertification",
        back_populates="certifier",
    )


class AgentContract(
    Base, TenantScopedMixin, UUIDMixin, TimestampMixin, AuditMixin, WorkspaceScopedMixin
):
    __tablename__ = "agent_contracts"
    __table_args__ = (
        Index("ix_agent_contracts_agent_id", "agent_id"),
        Index("ix_agent_contracts_workspace_agent", "workspace_id", "agent_id"),
    )

    agent_id: Mapped[str] = mapped_column(String(length=512), nullable=False)
    task_scope: Mapped[str] = mapped_column(Text(), nullable=False)
    expected_outputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    quality_thresholds: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    time_constraint_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_limit_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    success_criteria: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    enforcement_policy: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default="warn",
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attached_revision_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("registry_agent_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )

    breach_events: Mapped[list[ContractBreachEvent]] = relationship(
        "platform.trust.models.ContractBreachEvent",
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="platform.trust.models.ContractBreachEvent.created_at.asc()",
    )


class ContractTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "contract_templates"
    __table_args__ = (
        Index("ix_contract_templates_category", "category"),
        Index("ix_contract_templates_published", "is_published"),
    )

    name: Mapped[str] = mapped_column(String(length=255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    category: Mapped[str] = mapped_column(String(length=64), nullable=False)
    template_content: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    forked_from_template_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("contract_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_platform_authored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ContractBreachEvent(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "contract_breach_events"
    __table_args__ = (
        Index("ix_contract_breach_events_contract_id", "contract_id"),
        Index("ix_contract_breach_events_target", "target_type", "target_id"),
        Index("ix_contract_breach_events_created_at", "created_at"),
    )

    contract_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_contracts.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    breached_term: Mapped[str] = mapped_column(String(length=64), nullable=False)
    observed_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    threshold_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    enforcement_action: Mapped[str] = mapped_column(String(length=32), nullable=False)
    enforcement_outcome: Mapped[str] = mapped_column(String(length=32), nullable=False)
    contract_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    contract: Mapped[AgentContract | None] = relationship(
        "platform.trust.models.AgentContract",
        back_populates="breach_events",
    )


class ReassessmentRecord(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, AuditMixin):
    __tablename__ = "reassessment_records"
    __table_args__ = (Index("ix_reassessment_records_certification_id", "certification_id"),)

    certification_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trust_certifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    verdict: Mapped[str] = mapped_column(String(length=32), nullable=False)
    reassessor_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    certification: Mapped[TrustCertification] = relationship(
        "platform.trust.models.TrustCertification",
        back_populates="reassessment_records",
    )


class TrustRecertificationRequest(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_recertification_requests"
    __table_args__ = (
        Index("ix_trust_recertification_requests_certification_id", "certification_id"),
    )

    certification_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trust_certifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    trigger_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    trigger_reference: Mapped[str] = mapped_column(Text(), nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default="pending",
    )
    dismissal_justification: Mapped[str | None] = mapped_column(Text(), nullable=True)

    certification: Mapped[TrustCertification] = relationship(
        "platform.trust.models.TrustCertification",
        back_populates="recertification_requests",
    )


cast(Any, TrustRecertificationRequest.__table__).append_constraint(
    Index(
        "ix_trust_recertification_requests_deadline",
        TrustRecertificationRequest.__table__.c.deadline,
        postgresql_where=TrustRecertificationRequest.__table__.c.resolution_status == "pending",
    )
)


class TrustCertificationEvidenceRef(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
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


class TrustTier(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
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


class TrustSignal(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
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


class TrustProofLink(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
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


class TrustRecertificationTrigger(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
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


class TrustBlockedActionRecord(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
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


class TrustATEConfiguration(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
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


class TrustGuardrailPipelineConfig(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
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


class TrustOJEPipelineConfig(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
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


class TrustCircuitBreakerConfig(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
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


class TrustSafetyPreScreenerRuleSet(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
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


class ContentModerationPolicy(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "content_moderation_policies"
    __table_args__ = (
        CheckConstraint(
            "default_action IN ('block','redact','flag')",
            name="ck_content_moderation_policy_default_action",
        ),
        CheckConstraint(
            "provider_failure_action IN ('fail_closed','fail_open')",
            name="ck_content_moderation_policy_failure_action",
        ),
        CheckConstraint(
            "tie_break_rule IN ('max_score','min_score','primary_only')",
            name="ck_content_moderation_policy_tie_break_rule",
        ),
        CheckConstraint(
            "per_call_timeout_ms > 0 AND per_execution_budget_ms > 0",
            name="ck_content_moderation_policy_timeouts_positive",
        ),
        Index(
            "uq_content_moderation_policy_workspace_active",
            "workspace_id",
            unique=True,
            postgresql_where=text("active = TRUE"),
        ),
        Index(
            "idx_content_moderation_policy_workspace_version",
            "workspace_id",
            "version",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    categories: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, default=list
    )
    thresholds: Mapped[dict[str, float]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, default=dict
    )
    action_map: Mapped[dict[str, str]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, default=dict
    )
    default_action: Mapped[str] = mapped_column(String(length=32), nullable=False, default="flag")
    primary_provider: Mapped[str] = mapped_column(String(length=64), nullable=False)
    fallback_provider: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    tie_break_rule: Mapped[str] = mapped_column(
        String(length=32), nullable=False, default="max_score"
    )
    provider_failure_action: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default="fail_closed",
    )
    language_pins: Mapped[dict[str, str]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, default=dict
    )
    agent_allowlist: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, default=list
    )
    monthly_cost_cap_eur: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=False,
        default=Decimal("50.0"),
    )
    per_call_timeout_ms: Mapped[int] = mapped_column(Integer(), nullable=False, default=2000)
    per_execution_budget_ms: Mapped[int] = mapped_column(Integer(), nullable=False, default=5000)
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class ContentModerationEvent(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "content_moderation_events"
    __table_args__ = (
        CheckConstraint(
            "action_taken IN ('block','redact','flag','none',"
            "'fail_closed_blocked','fail_open_delivered')",
            name="ck_content_moderation_event_action",
        ),
        Index("idx_moderation_events_workspace_created", "workspace_id", "created_at"),
        Index(
            "idx_moderation_events_workspace_agent_created",
            "workspace_id",
            "agent_id",
            "created_at",
        ),
        Index(
            "idx_moderation_events_workspace_action",
            "workspace_id",
            "action_taken",
            postgresql_where=text("action_taken IN ('block','redact','flag')"),
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    agent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("registry_agent_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    policy_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_moderation_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(length=64), nullable=False)
    triggered_categories: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, default=list
    )
    scores: Mapped[dict[str, float]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, default=dict
    )
    action_taken: Mapped[str] = mapped_column(String(length=32), nullable=False)
    language_detected: Mapped[str | None] = mapped_column(String(length=32), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    audit_chain_ref: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
