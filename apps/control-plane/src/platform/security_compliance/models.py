from __future__ import annotations

from datetime import date, datetime
from platform.common.models import Base, TenantScopedMixin, UUIDMixin
from uuid import UUID

from sqlalchemy import UUID as SQLUUID
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class SoftwareBillOfMaterials(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "software_bills_of_materials"
    __table_args__ = (
        UniqueConstraint("release_version", "format", name="uq_sbom_release_format"),
        CheckConstraint("format IN ('spdx', 'cyclonedx')", name="ck_sbom_format"),
    )

    release_version: Mapped[str] = mapped_column(String(length=64), nullable=False)
    format: Mapped[str] = mapped_column(String(length=32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(length=64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class VulnerabilityScanResult(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "vulnerability_scan_results"
    __table_args__ = (
        CheckConstraint(
            "scanner IN "
            "('trivy','grype','pip_audit','npm_audit','govulncheck','bandit','gosec','gitleaks')",
            name="ck_vuln_scan_scanner",
        ),
        CheckConstraint(
            "max_severity IS NULL OR max_severity IN ('critical','high','medium','low','info')",
            name="ck_vuln_scan_max_severity",
        ),
        CheckConstraint("gating_result IN ('passed','blocked')", name="ck_vuln_scan_gate"),
        Index("ix_vuln_scan_release", "release_version", "scanned_at"),
        Index("ix_vuln_scan_severity", "max_severity", "gating_result"),
    )

    scanner: Mapped[str] = mapped_column(String(length=64), nullable=False)
    release_version: Mapped[str] = mapped_column(String(length=64), nullable=False)
    findings: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    max_severity: Mapped[str | None] = mapped_column(String(length=32), nullable=True)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    gating_result: Mapped[str] = mapped_column(String(length=16), nullable=False)


class VulnerabilityException(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "vulnerability_exceptions"
    __table_args__ = (
        CheckConstraint("length(justification) >= 20", name="ck_vuln_exception_justification"),
        Index("ix_vuln_exception_active", "scanner", "vulnerability_id", "expires_at"),
    )

    scanner: Mapped[str] = mapped_column(String(length=64), nullable=False)
    vulnerability_id: Mapped[str] = mapped_column(String(length=128), nullable=False)
    component_pattern: Mapped[str] = mapped_column(String(length=256), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PenetrationTest(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "penetration_tests"

    scheduled_for: Mapped[date] = mapped_column(Date, nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    firm: Mapped[str | None] = mapped_column(String(length=256), nullable=True)
    report_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    attestation_hash: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PentestFinding(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "pentest_findings"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('critical','high','medium','low')", name="ck_pentest_finding_severity"
        ),
        CheckConstraint(
            "remediation_status IN ('open','in_progress','remediated','accepted','wont_fix')",
            name="ck_pentest_finding_status",
        ),
        Index(
            "ix_pentest_overdue",
            "remediation_status",
            "remediation_due_date",
            postgresql_where=text("remediation_status = 'open'"),
        ),
    )

    pentest_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("penetration_tests.id", ondelete="CASCADE"),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(String(length=16), nullable=False)
    title: Mapped[str] = mapped_column(String(length=512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation_status: Mapped[str] = mapped_column(
        String(length=32), nullable=False, default="open"
    )
    remediation_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    remediated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remediation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PentestSlaPolicy(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "pentest_sla_policies"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('critical','high','medium','low')", name="ck_pentest_sla_severity"
        ),
        CheckConstraint("max_days > 0", name="ck_pentest_sla_max_days"),
        UniqueConstraint("severity", name="uq_pentest_sla_severity"),
    )

    severity: Mapped[str] = mapped_column(String(length=16), nullable=False)
    max_days: Mapped[int] = mapped_column(Integer, nullable=False)
    ceiling_days: Mapped[int] = mapped_column(Integer, nullable=False)


class SecretRotationSchedule(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "secret_rotation_schedules"
    __table_args__ = (
        UniqueConstraint("secret_name", name="uq_secret_rotation_secret_name"),
        CheckConstraint(
            "rotation_interval_days > 0 AND rotation_interval_days <= 365",
            name="ck_rotation_interval_days",
        ),
        CheckConstraint(
            "overlap_window_hours >= 24 AND overlap_window_hours <= 168",
            name="ck_rotation_overlap_hours",
        ),
        CheckConstraint(
            "rotation_state IN ('idle','rotating','overlap','finalising','failed')",
            name="ck_rotation_state",
        ),
        Index(
            "ix_rotation_due", "next_rotation_at", postgresql_where=text("rotation_state = 'idle'")
        ),
    )

    secret_name: Mapped[str] = mapped_column(String(length=256), nullable=False)
    secret_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    rotation_interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    overlap_window_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_rotation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    overlap_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotation_state: Mapped[str] = mapped_column(String(length=32), nullable=False, default="idle")
    vault_path: Mapped[str] = mapped_column(String(length=512), nullable=False)


class JitCredentialGrant(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "jit_credential_grants"
    __table_args__ = (
        CheckConstraint("length(purpose) >= 20", name="ck_jit_purpose_length"),
        CheckConstraint(
            "status IN ('pending','approved','rejected','expired','revoked')",
            name="ck_jit_status",
        ),
        CheckConstraint(
            "approved_by IS NULL OR approved_by != user_id", name="ck_jit_no_self_approval"
        ),
        Index("ix_jit_user_status", "user_id", "status", "expires_at"),
        Index(
            "ix_jit_pending", "status", "requested_at", postgresql_where=text("status = 'pending'")
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    operation: Mapped[str] = mapped_column(String(length=256), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="pending")
    approved_by: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    usage_audit: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )


class JitApproverPolicy(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "jit_approver_policies"
    __table_args__ = (
        UniqueConstraint("operation_pattern", name="uq_jit_policy_operation_pattern"),
        CheckConstraint(
            "min_approvers > 0 AND min_approvers <= 5", name="ck_jit_policy_min_approvers"
        ),
        CheckConstraint(
            "max_expiry_minutes > 0 AND max_expiry_minutes <= 1440",
            name="ck_jit_policy_max_expiry",
        ),
    )

    operation_pattern: Mapped[str] = mapped_column(String(length=256), nullable=False)
    required_roles: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    min_approvers: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_expiry_minutes: Mapped[int] = mapped_column(Integer, nullable=False)


class ComplianceControl(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "compliance_controls"
    __table_args__ = (
        UniqueConstraint(
            "framework", "control_id", name="uq_compliance_controls_framework_control"
        ),
        CheckConstraint(
            "framework IN ('soc2','iso27001','hipaa','pci_dss')", name="ck_compliance_framework"
        ),
    )

    framework: Mapped[str] = mapped_column(String(length=32), nullable=False)
    control_id: Mapped[str] = mapped_column(String(length=64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_requirements: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)


class ComplianceEvidenceMapping(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "compliance_evidence_mappings"
    __table_args__ = (Index("ix_mapping_by_evidence", "evidence_type"),)

    evidence_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    control_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("compliance_controls.id", ondelete="CASCADE"),
        nullable=False,
    )
    filter_expression: Mapped[str | None] = mapped_column(Text, nullable=True)


class ComplianceEvidence(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "compliance_evidence"
    __table_args__ = (Index("ix_evidence_by_control", "control_id", "collected_at"),)

    control_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("compliance_controls.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    evidence_ref: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_hash: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    collected_by: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
