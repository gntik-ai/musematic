from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EnforcementPolicy = Literal["warn", "throttle", "escalate", "terminate"]
ReassessmentVerdict = Literal["pass", "fail", "action_required"]
ComplianceScope = Literal["agent", "fleet", "workspace"]
ComplianceBucket = Literal["hourly", "daily"]


class CertifierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    organization: str | None = Field(default=None, max_length=256)
    credentials: dict[str, Any] | None = None
    permitted_scopes: list[str] | None = None


class CertifierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    organization: str | None
    credentials: dict[str, Any] | None
    permitted_scopes: list[str] | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CertifierListResponse(BaseModel):
    items: list[CertifierResponse]
    total: int


class AgentContractCreate(BaseModel):
    agent_id: str = Field(min_length=1, max_length=512)
    task_scope: str = Field(min_length=1)
    expected_outputs: dict[str, Any] | None = None
    quality_thresholds: dict[str, Any] | None = None
    time_constraint_seconds: int | None = Field(default=None, ge=1)
    cost_limit_tokens: int | None = Field(default=None, ge=1)
    escalation_conditions: dict[str, Any] | None = None
    success_criteria: dict[str, Any] | None = None
    enforcement_policy: EnforcementPolicy = "warn"


class AgentContractUpdate(BaseModel):
    task_scope: str | None = Field(default=None, min_length=1)
    expected_outputs: dict[str, Any] | None = None
    quality_thresholds: dict[str, Any] | None = None
    time_constraint_seconds: int | None = Field(default=None, ge=1)
    cost_limit_tokens: int | None = Field(default=None, ge=1)
    escalation_conditions: dict[str, Any] | None = None
    success_criteria: dict[str, Any] | None = None
    enforcement_policy: EnforcementPolicy | None = None
    is_archived: bool | None = None


class AgentContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_id: str
    task_scope: str
    expected_outputs: dict[str, Any] | None
    quality_thresholds: dict[str, Any] | None
    time_constraint_seconds: int | None
    cost_limit_tokens: int | None
    escalation_conditions: dict[str, Any] | None
    success_criteria: dict[str, Any] | None
    enforcement_policy: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class AgentContractListResponse(BaseModel):
    items: list[AgentContractResponse]
    total: int


class ContractAttachmentRequest(BaseModel):
    interaction_id: UUID | None = None
    execution_id: UUID | None = None


class ContractBreachEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contract_id: UUID | None
    target_type: str
    target_id: UUID
    breached_term: str
    observed_value: dict[str, Any]
    threshold_value: dict[str, Any]
    enforcement_action: str
    enforcement_outcome: str
    contract_snapshot: dict[str, Any]
    created_at: datetime


class ContractBreachEventListResponse(BaseModel):
    items: list[ContractBreachEventResponse]
    total: int


class ReassessmentCreate(BaseModel):
    verdict: ReassessmentVerdict
    notes: str | None = None


class ReassessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    certification_id: UUID
    verdict: str
    reassessor_id: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ReassessmentListResponse(BaseModel):
    items: list[ReassessmentResponse]
    total: int


class TrustRecertificationRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    certification_id: UUID
    trigger_type: str
    trigger_reference: str
    deadline: datetime | None
    resolution_status: str
    dismissal_justification: str | None
    created_at: datetime
    updated_at: datetime


class TrustRecertificationRequestListResponse(BaseModel):
    items: list[TrustRecertificationRequestResponse]
    total: int


class ComplianceTrendPoint(BaseModel):
    bucket: str
    compliant: int
    total: int


class ComplianceRateQuery(BaseModel):
    scope: ComplianceScope
    scope_id: str
    start: datetime
    end: datetime
    bucket: ComplianceBucket = "daily"

    @model_validator(mode="after")
    def validate_range(self) -> ComplianceRateQuery:
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class ComplianceRateResponse(BaseModel):
    scope: ComplianceScope
    scope_id: str
    start: datetime
    end: datetime
    total_contract_attached: int
    compliant: int
    warned: int
    throttled: int
    escalated: int
    terminated: int
    compliance_rate: float | None
    breach_by_term: dict[str, int]
    trend: list[ComplianceTrendPoint]


class DismissSuspensionRequest(BaseModel):
    justification: str = Field(min_length=10)


class IssueWithCertifierRequest(BaseModel):
    certifier_id: UUID
    scope: str = Field(min_length=1, max_length=255)
