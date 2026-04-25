from __future__ import annotations

from datetime import datetime
from platform.privacy_compliance.models import (
    ConsentType,
    DLPAction,
    DLPClassification,
    DSRRequestType,
    DSRStatus,
    PIAStatus,
    PIASubjectType,
)
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DSRCreateRequest(BaseModel):
    subject_user_id: UUID
    request_type: DSRRequestType
    legal_basis: str | None = Field(default=None, max_length=256)
    hold_hours: int = Field(default=0, ge=0, le=72)


class DSRSelfServiceCreateRequest(BaseModel):
    request_type: DSRRequestType
    legal_basis: str | None = Field(default=None, max_length=256)


class DSRCancelRequest(BaseModel):
    approver_ids: list[UUID] = Field(min_length=2)
    reason: str = Field(min_length=1, max_length=512)


class DSRRetryRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=512)


class DSRResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_user_id: UUID
    request_type: DSRRequestType
    requested_by: UUID
    status: DSRStatus
    legal_basis: str | None = None
    scheduled_release_at: datetime | None = None
    requested_at: datetime
    completed_at: datetime | None = None
    completion_proof_hash: str | None = None
    failure_reason: str | None = None
    tombstone_id: UUID | None = None


class CascadePlanResponse(BaseModel):
    dsr_id: UUID | None = None
    estimated_count: int
    per_store_estimates: dict[str, int]
    per_target_estimates: dict[str, dict[str, int]]


class TombstoneResponse(BaseModel):
    id: UUID
    subject_user_id_hash: str
    salt_version: int
    entities_deleted: dict[str, int]
    cascade_log: list[dict[str, Any]]
    proof_hash: str
    created_at: datetime


class SignedTombstoneResponse(BaseModel):
    tombstone: str
    key_version: str
    signature: str
    proof_hash: str


class ConsentRecordRequest(BaseModel):
    choices: dict[ConsentType, bool]
    workspace_id: UUID | None = None


class ConsentStateResponse(BaseModel):
    state: dict[ConsentType, Literal["granted", "denied", "never_asked"]]


class ConsentRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    consent_type: ConsentType
    granted: bool
    granted_at: datetime
    revoked_at: datetime | None = None
    workspace_id: UUID | None = None


class DisclosureResponse(BaseModel):
    version: str = "2026-04-25"
    text: str
    required_consents: list[ConsentType]


class PIACreateRequest(BaseModel):
    subject_type: PIASubjectType
    subject_id: UUID
    data_categories: list[str] = Field(min_length=1)
    legal_basis: str = Field(min_length=10)
    retention_policy: str | None = None
    risks: list[dict[str, Any]] = Field(default_factory=list)
    mitigations: list[dict[str, Any]] = Field(default_factory=list)


class PIARejectRequest(BaseModel):
    feedback: str = Field(min_length=1)


class PIAResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_type: PIASubjectType
    subject_id: UUID
    data_categories: list[str]
    legal_basis: str
    retention_policy: str | None = None
    risks: list[dict[str, Any]] | None = None
    mitigations: list[dict[str, Any]] | None = None
    status: PIAStatus
    submitted_by: UUID
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    rejection_feedback: str | None = None
    superseded_by_pia_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ResidencyConfigRequest(BaseModel):
    region_code: str = Field(min_length=1, max_length=32)
    allowed_transfer_regions: list[str] = Field(default_factory=list)


class ResidencyConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    region_code: str
    allowed_transfer_regions: list[str]
    created_at: datetime
    updated_at: datetime


class ResidencyCheckRequest(BaseModel):
    origin_region: str | None = Field(default=None, max_length=32)


class ResidencyCheckResponse(BaseModel):
    allowed: bool
    workspace_id: UUID
    origin_region: str


class DLPRuleCreateRequest(BaseModel):
    workspace_id: UUID | None = None
    name: str = Field(min_length=1, max_length=256)
    classification: DLPClassification
    pattern: str = Field(min_length=1)
    action: DLPAction
    enabled: bool = True


class DLPRuleUpdateRequest(BaseModel):
    enabled: bool | None = None
    action: DLPAction | None = None


class DLPRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID | None = None
    name: str
    classification: DLPClassification
    pattern: str
    action: DLPAction
    enabled: bool
    seeded: bool


class DLPEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_id: UUID
    workspace_id: UUID | None = None
    execution_id: UUID | None = None
    match_summary: str
    action_taken: DLPAction
    created_at: datetime
