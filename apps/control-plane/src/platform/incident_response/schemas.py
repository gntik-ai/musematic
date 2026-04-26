from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IncidentSeverity(StrEnum):
    critical = "critical"
    high = "high"
    warning = "warning"
    info = "info"


class IncidentStatus(StrEnum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"
    auto_resolved = "auto_resolved"


class PagingProvider(StrEnum):
    pagerduty = "pagerduty"
    opsgenie = "opsgenie"
    victorops = "victorops"


class RunbookStatus(StrEnum):
    active = "active"
    retired = "retired"


class PostMortemStatus(StrEnum):
    draft = "draft"
    published = "published"
    distributed = "distributed"


class TimelineSource(StrEnum):
    audit_chain = "audit_chain"
    execution_journal = "execution_journal"
    kafka = "kafka"


class TimelineCoverageState(StrEnum):
    complete = "complete"
    partial = "partial"
    unavailable = "unavailable"


class DeliveryStatus(StrEnum):
    pending = "pending"
    delivered = "delivered"
    failed = "failed"
    resolved = "resolved"


class DiagnosticCommand(BaseModel):
    command: str = Field(min_length=1)
    description: str = Field(min_length=1)


class IncidentSignal(BaseModel):
    alert_rule_class: str = Field(min_length=1, max_length=128)
    severity: IncidentSeverity
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1)
    related_execution_ids: list[UUID] = Field(default_factory=list)
    related_event_ids: list[UUID] = Field(default_factory=list)
    condition_fingerprint: str = Field(min_length=1, max_length=512)
    runbook_scenario: str | None = Field(default=None, max_length=256)
    correlation_context: CorrelationContext | None = None


class IncidentRef(BaseModel):
    incident_id: UUID
    deduplicated: bool = False
    external_pages_attempted: int = 0
    no_external_page_attempted: bool = False


class ExternalAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    integration_id: UUID
    provider_reference: str | None
    delivery_status: DeliveryStatus
    attempt_count: int
    last_attempt_at: datetime | None
    last_error: str | None
    next_retry_at: datetime | None


class RunbookBase(BaseModel):
    scenario: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=256)
    symptoms: str = Field(min_length=1)
    diagnostic_commands: list[DiagnosticCommand] = Field(min_length=1)
    remediation_steps: str = Field(min_length=1)
    escalation_path: str = Field(min_length=1)


class RunbookCreateRequest(RunbookBase):
    status: RunbookStatus = RunbookStatus.active


class RunbookUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    symptoms: str | None = Field(default=None, min_length=1)
    diagnostic_commands: list[DiagnosticCommand] | None = Field(default=None, min_length=1)
    remediation_steps: str | None = Field(default=None, min_length=1)
    escalation_path: str | None = Field(default=None, min_length=1)
    status: RunbookStatus | None = None


class RunbookResponse(RunbookBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: RunbookStatus
    version: int
    created_at: datetime
    updated_at: datetime
    updated_by: UUID | None
    is_stale: bool = False


class RunbookListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scenario: str
    title: str
    status: RunbookStatus
    version: int
    updated_at: datetime
    is_stale: bool = False


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condition_fingerprint: str
    severity: IncidentSeverity
    status: IncidentStatus
    title: str
    description: str
    triggered_at: datetime
    resolved_at: datetime | None
    related_executions: list[UUID]
    related_event_ids: list[UUID]
    runbook_scenario: str | None
    alert_rule_class: str
    post_mortem_id: UUID | None


class IncidentListItem(IncidentResponse):
    pass


class IncidentDetailResponse(IncidentResponse):
    external_alerts: list[ExternalAlertResponse] = Field(default_factory=list)
    runbook: RunbookResponse | None = None
    runbook_authoring_link: str | None = None
    runbook_scenario_unmapped: bool = False


class IncidentResolveRequest(BaseModel):
    resolved_at: datetime | None = None
    auto_resolved: bool = False


class IntegrationCreateRequest(BaseModel):
    provider: PagingProvider
    integration_key_ref: str = Field(min_length=1, max_length=512)
    alert_severity_mapping: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("integration_key_ref")
    @classmethod
    def _validate_key_ref(cls, value: str) -> str:
        if not value.startswith("incident-response/integrations/"):
            raise ValueError("integration_key_ref must be an incident-response Vault path")
        return value


class IntegrationUpdateRequest(BaseModel):
    enabled: bool | None = None
    alert_severity_mapping: dict[str, str] | None = None


class IntegrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: PagingProvider
    integration_key_ref: str
    enabled: bool
    alert_severity_mapping: dict[str, str]
    created_at: datetime
    updated_at: datetime


class TimelineEntry(BaseModel):
    id: str
    timestamp: datetime
    source: TimelineSource
    event_type: str | None = None
    summary: str
    topic: str | None = None
    payload_summary: dict[str, Any] = Field(default_factory=dict)


class TimelineSourceCoverage(BaseModel):
    audit_chain: TimelineCoverageState = TimelineCoverageState.complete
    execution_journal: TimelineCoverageState = TimelineCoverageState.complete
    kafka: TimelineCoverageState = TimelineCoverageState.complete
    reasons: dict[str, str] = Field(default_factory=dict)


class TimelineResponse(BaseModel):
    entries: list[TimelineEntry]
    coverage: TimelineSourceCoverage


class PostMortemDraftRequest(BaseModel):
    created_by: UUID | None = None


class PostMortemSectionUpdateRequest(BaseModel):
    impact_assessment: str | None = None
    root_cause: str | None = None
    action_items: list[dict[str, Any]] | None = None


class PostMortemDistributeRequest(BaseModel):
    recipients: list[str] = Field(min_length=1)


class PostMortemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    status: PostMortemStatus
    timeline: list[TimelineEntry] | None = None
    timeline_blob_ref: str | None
    timeline_source_coverage: TimelineSourceCoverage
    impact_assessment: str | None
    root_cause: str | None
    action_items: list[dict[str, Any]] | None
    distribution_list: list[dict[str, Any]] | None
    linked_certification_ids: list[UUID]
    blameless: bool
    created_at: datetime
    created_by: UUID | None
    published_at: datetime | None
    distributed_at: datetime | None


class LinkExecutionRequest(BaseModel):
    execution_id: UUID


class LinkCertificationRequest(BaseModel):
    certification_id: UUID
