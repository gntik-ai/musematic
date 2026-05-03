"""Pydantic v2 request/response schemas for the data_lifecycle BC.

Mirrors the 7 contract files at ``specs/104-data-lifecycle/contracts/``.
"""

from __future__ import annotations

from datetime import date, datetime
from platform.data_lifecycle.models import DeletionPhase, ExportStatus, ScopeType
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# Common / shared
# =============================================================================


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=False)


# =============================================================================
# Export — workspace-export-rest.md, tenant-export-rest.md
# =============================================================================


class WorkspaceExportRequest(_Base):
    """POST /api/v1/workspaces/{workspace_id}/data-export — empty body.

    The workspace_id is a path param; this exists to give FastAPI a
    body-less request hook and to allow forward-compatible fields.
    """


class TenantExportDelivery(_Base):
    method: Literal["email_with_otp", "email_and_sms"] = "email_with_otp"
    encrypt_with_password: bool = True


class TenantExportRequest(_Base):
    include_workspaces: bool = True
    include_users: bool = True
    include_audit_chain: bool = True
    include_cost_history: bool = True
    delivery: TenantExportDelivery = Field(default_factory=TenantExportDelivery)


class ExportJobSummary(_Base):
    id: UUID
    scope_type: ScopeType
    scope_id: UUID
    status: ExportStatus
    requested_at: datetime = Field(alias="created_at")
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output_size_bytes: int | None = None
    output_expires_at: datetime | None = None


class ExportJobDetail(ExportJobSummary):
    output_url: str | None = None
    error_message: str | None = None
    estimated_completion: datetime | None = None
    estimated_size_bytes_lower_bound: int | None = None


class ExportJobList(_Base):
    items: list[ExportJobSummary]
    next_cursor: str | None = None


# =============================================================================
# Deletion — workspace-deletion-rest.md, tenant-deletion-rest.md
# =============================================================================


class WorkspaceDeletionRequest(_Base):
    typed_confirmation: str = Field(min_length=1, max_length=512)
    reason: str | None = Field(default=None, max_length=2048)


class TenantDeletionRequest(_Base):
    typed_confirmation: str = Field(min_length=1, max_length=512)
    reason: str = Field(min_length=1, max_length=2048)
    include_final_export: bool = True
    grace_period_days: int = Field(default=30, ge=7, le=90)


class GraceExtensionRequest(_Base):
    additional_days: int = Field(ge=1, le=90)
    reason: str = Field(min_length=1, max_length=2048)


class AbortRequest(_Base):
    abort_reason: str = Field(min_length=1, max_length=2048)


class DeletionJobSummary(_Base):
    id: UUID
    scope_type: ScopeType
    scope_id: UUID
    phase: DeletionPhase
    grace_period_days: int
    grace_ends_at: datetime
    cascade_started_at: datetime | None = None
    cascade_completed_at: datetime | None = None


class StoreCascadeProgress(_Base):
    store: Literal[
        "postgresql", "qdrant", "neo4j", "clickhouse", "opensearch", "s3"
    ]
    status: Literal["pending", "in_progress", "completed", "failed"]
    rows_affected: int | None = None


class DeletionJobDetail(DeletionJobSummary):
    tombstone_id: UUID | None = None
    final_export_job_id: UUID | None = None
    two_pa_token_id: UUID | None = None
    abort_reason: str | None = None
    store_progress: list[StoreCascadeProgress] = Field(default_factory=list)


class CancelDeletionResponse(_Base):
    """Anti-enumeration response — identical for any token outcome (R10)."""

    message: str = (
        "If the link was valid, deletion has been cancelled. "
        "Check your email for confirmation."
    )


# =============================================================================
# DPA — dpa-upload-rest.md
# =============================================================================


class DPAUploadResponse(_Base):
    tenant_id: UUID
    version: str
    effective_date: date
    sha256: str
    vault_path: str


class DPAVersionEntry(_Base):
    version: str
    signed_at: datetime
    sha256: str


class DPAListResponse(_Base):
    active: DPAVersionEntry | None = None
    history: list[DPAVersionEntry] = Field(default_factory=list)


# =============================================================================
# Sub-processors — sub-processors-rest.md
# =============================================================================


class SubProcessorPublic(_Base):
    """Subset of fields exposed by the public endpoint.

    ``notes`` is intentionally absent — operator-only.
    """

    name: str
    category: str
    location: str
    data_categories: list[str]
    privacy_policy_url: str | None = None
    dpa_url: str | None = None
    started_using_at: date | None = None


class SubProcessorsPublicResponse(_Base):
    last_updated_at: datetime
    items: list[SubProcessorPublic]


class SubProcessorAdmin(SubProcessorPublic):
    id: UUID
    is_active: bool
    notes: str | None = None
    updated_at: datetime
    updated_by_user_id: UUID | None = None


class SubProcessorCreate(_Base):
    name: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    location: str = Field(min_length=1, max_length=64)
    data_categories: list[str] = Field(default_factory=list)
    privacy_policy_url: str | None = None
    dpa_url: str | None = None
    started_using_at: date | None = None
    notes: str | None = Field(default=None, max_length=4096)


class SubProcessorUpdate(_Base):
    """All fields optional — PATCH semantics."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    location: str | None = Field(default=None, min_length=1, max_length=64)
    data_categories: list[str] | None = None
    privacy_policy_url: str | None = None
    dpa_url: str | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=4096)


class SubProcessorSubscribeRequest(_Base):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def _basic_email_check(cls, v: str) -> str:
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("invalid email")
        return v.lower().strip()


class SubProcessorSubscribeResponse(_Base):
    """Anti-enumeration response — identical for any email."""

    message: str = (
        "If the email is valid, a verification link has been sent."
    )


# =============================================================================
# Article 28 evidence (Phase 8)
# =============================================================================


class Article28EvidenceRequest(_Base):
    """POST /api/v1/admin/tenants/{tenant_id}/article28-evidence — empty."""


class Article28EvidenceResponse(_Base):
    job_id: UUID
    estimated_completion: datetime | None = None
