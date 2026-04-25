from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SecurityComplianceHealthResponse(BaseModel):
    status: str = "ok"


class SbomIngestRequest(BaseModel):
    release_version: str = Field(min_length=1, max_length=64)
    format: str = Field(pattern="^(spdx|cyclonedx)$")
    content: str = Field(min_length=2)


class SbomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    release_version: str
    format: str
    content: str
    content_sha256: str
    generated_at: datetime


class SbomHashResponse(BaseModel):
    release_version: str
    format: str
    content_sha256: str
    valid: bool = True


class ScanFinding(BaseModel):
    vulnerability_id: str
    component: str = ""
    severity: str = Field(pattern="^(critical|high|medium|low|info)$")
    title: str = ""
    fixed_version: str | None = None
    dev_only: bool = False
    excepted: bool = False


class ScanIngestRequest(BaseModel):
    scanner: str
    findings: list[ScanFinding] = Field(default_factory=list)
    max_severity: str | None = Field(default=None, pattern="^(critical|high|medium|low|info)$")
    gating_result: str | None = Field(default=None, pattern="^(passed|blocked)$")


class ScanResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scanner: str
    release_version: str
    findings: list[dict[str, object]]
    max_severity: str | None
    scanned_at: datetime
    gating_result: str


class ScanStatusResponse(BaseModel):
    release_version: str
    gating_result: str
    scanners: list[str]
    blocked_findings: list[dict[str, object]]


class VulnerabilityExceptionCreate(BaseModel):
    scanner: str
    vulnerability_id: str
    component_pattern: str = "*"
    justification: str = Field(min_length=20)
    approved_by: UUID
    expires_at: datetime


class VulnerabilityExceptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scanner: str
    vulnerability_id: str
    component_pattern: str
    justification: str
    approved_by: UUID
    expires_at: datetime
    created_at: datetime


class RotationScheduleCreate(BaseModel):
    secret_name: str
    secret_type: str
    rotation_interval_days: int = Field(default=90, ge=1, le=365)
    overlap_window_hours: int = Field(default=24, ge=24, le=168)
    vault_path: str
    next_rotation_at: datetime | None = None


class RotationScheduleUpdate(BaseModel):
    rotation_interval_days: int | None = Field(default=None, ge=1, le=365)
    overlap_window_hours: int | None = Field(default=None, ge=24, le=168)
    next_rotation_at: datetime | None = None


class RotationTriggerRequest(BaseModel):
    emergency: bool = False
    skip_overlap: bool = False
    approved_by: UUID | None = None


class RotationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    secret_name: str
    secret_type: str
    rotation_interval_days: int
    overlap_window_hours: int
    last_rotated_at: datetime | None
    next_rotation_at: datetime | None
    overlap_ends_at: datetime | None = None
    rotation_state: str
    vault_path: str


class RotationTriggerResponse(BaseModel):
    rotation_id: UUID
    status: str
    next_rotation_at: datetime | None = None
    overlap_ends_at: datetime | None = None


class JitGrantRequest(BaseModel):
    operation: str
    purpose: str = Field(min_length=20)
    requested_expiry_minutes: int = Field(default=30, ge=1, le=1440)


class JitApprovalRequest(BaseModel):
    reason: str | None = None


class JitRejectRequest(BaseModel):
    reason: str = Field(min_length=3)


class JitUsageRequest(BaseModel):
    operation: str
    target: str
    outcome: str


class JitGrantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    operation: str
    purpose: str
    status: str
    approved_by: UUID | None
    requested_at: datetime
    approved_at: datetime | None
    issued_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    revoked_by: UUID | None
    usage_audit: list[dict[str, object]]
    jwt: str | None = None
    required_approvers: list[str] = Field(default_factory=list)
    min_approvers: int = 1
    max_expiry_minutes: int = 1440


class JitApproverPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    operation_pattern: str
    required_roles: list[str]
    min_approvers: int
    max_expiry_minutes: int


class PentestScheduleRequest(BaseModel):
    scheduled_for: date
    firm: str | None = None


class PentestExecuteRequest(BaseModel):
    report_url: str
    report_sha256: str | None = None


class PentestFindingCreate(BaseModel):
    severity: str | None = Field(default=None, pattern="^(critical|high|medium|low)$")
    title: str
    description: str | None = None


class PentestFindingsImportRequest(BaseModel):
    findings: list[PentestFindingCreate]


class PentestFindingUpdate(BaseModel):
    remediation_status: str | None = Field(
        default=None,
        pattern="^(open|in_progress|remediated|accepted|wont_fix)$",
    )
    remediation_due_date: date | None = None
    remediation_notes: str | None = None


class PentestFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pentest_id: UUID
    severity: str
    title: str
    description: str | None
    remediation_status: str
    remediation_due_date: date
    remediated_at: datetime | None
    remediation_notes: str | None


class PentestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scheduled_for: date
    executed_at: datetime | None
    firm: str | None
    report_url: str | None
    attestation_hash: str | None
    created_at: datetime
    findings: list[PentestFindingResponse] = Field(default_factory=list)


class ComplianceControlSummary(BaseModel):
    id: UUID
    framework: str
    control_id: str
    description: str
    evidence_count: int
    latest_evidence_at: datetime | None = None
    gap: bool
    suggested_source: str | None = None


class FrameworkResponse(BaseModel):
    framework: str
    controls: list[ComplianceControlSummary]


class FrameworkListResponse(BaseModel):
    frameworks: list[str]


class ManualEvidenceRequest(BaseModel):
    control_id: UUID
    description: str
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"
    collected_by: UUID | None = None


class ManualEvidenceFormResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    control_id: UUID
    evidence_type: str
    evidence_ref: str
    evidence_hash: str | None
    collected_at: datetime
    collected_by: UUID | None


class BundleExportRequest(BaseModel):
    framework: str
    window_start: datetime
    window_end: datetime


class BundleExportResponse(BaseModel):
    id: UUID
    framework: str
    url: str
    manifest_hash: str
    signature: str


class ComplianceEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    control_id: UUID
    evidence_type: str
    evidence_ref: str
    evidence_hash: str | None
    collected_at: datetime
    collected_by: UUID | None
