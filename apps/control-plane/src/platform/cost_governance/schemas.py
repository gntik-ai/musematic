from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CostType(StrEnum):
    model = "model"
    compute = "compute"
    storage = "storage"
    overhead = "overhead"


class BudgetPeriodType(StrEnum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class AnomalyType(StrEnum):
    sudden_spike = "sudden_spike"
    sustained_deviation = "sustained_deviation"


class AnomalySeverity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class AnomalyState(StrEnum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"


class CostAttributionRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    execution_id: UUID
    step_id: str | None = None
    workspace_id: UUID
    agent_id: UUID | None = None
    user_id: UUID | None = None
    origin: str = "user_trigger"
    model_id: str | None = None
    currency: str = "USD"
    model_cost_cents: Decimal = Decimal("0")
    compute_cost_cents: Decimal = Decimal("0")
    storage_cost_cents: Decimal = Decimal("0")
    overhead_cost_cents: Decimal = Decimal("0")
    total_cost_cents: Decimal = Decimal("0")
    token_counts: dict[str, Any] = Field(default_factory=dict)
    attribution_metadata: dict[str, Any] = Field(default_factory=dict)
    correction_of: UUID | None = None
    created_at: datetime


class CostAttributionCorrectionRequest(BaseModel):
    model_cost_cents: Decimal = Decimal("0")
    compute_cost_cents: Decimal = Decimal("0")
    storage_cost_cents: Decimal = Decimal("0")
    overhead_cost_cents: Decimal = Decimal("0")
    reason: str | None = Field(default=None, max_length=500)


class WorkspaceBudgetCreateRequest(BaseModel):
    period_type: BudgetPeriodType
    budget_cents: int = Field(gt=0)
    soft_alert_thresholds: list[int] = Field(default_factory=lambda: [50, 80, 100])
    hard_cap_enabled: bool = False
    admin_override_enabled: bool = True
    currency: str = "USD"

    @field_validator("soft_alert_thresholds")
    @classmethod
    def validate_thresholds(cls, value: list[int]) -> list[int]:
        if sorted(value) != value:
            raise ValueError("thresholds must be sorted ascending")
        if any(item <= 0 or item > 100 for item in value):
            raise ValueError("thresholds must be between 1 and 100")
        return value


class WorkspaceBudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    period_type: BudgetPeriodType
    budget_cents: int
    soft_alert_thresholds: list[int]
    hard_cap_enabled: bool
    admin_override_enabled: bool
    currency: str
    created_at: datetime
    updated_at: datetime


class BudgetAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    budget_id: UUID
    workspace_id: UUID
    threshold_percentage: int
    period_start: datetime
    period_end: datetime
    spend_cents: Decimal
    triggered_at: datetime


class ChargebackReportRequest(BaseModel):
    dimensions: list[str] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=lambda: ["workspace"])
    since: datetime
    until: datetime
    workspace_filter: list[UUID] | None = None

    @model_validator(mode="after")
    def validate_window(self) -> ChargebackReportRequest:
        if self.since > self.until:
            raise ValueError("since must be less than or equal to until")
        return self


class ChargebackReportRow(BaseModel):
    dimensions: dict[str, Any]
    model_cost_cents: Decimal = Decimal("0")
    compute_cost_cents: Decimal = Decimal("0")
    storage_cost_cents: Decimal = Decimal("0")
    overhead_cost_cents: Decimal = Decimal("0")
    total_cost_cents: Decimal = Decimal("0")
    currency: str = "USD"


class ChargebackReportResponse(BaseModel):
    dimensions: list[str]
    time_range: dict[str, datetime]
    group_by: list[str]
    rows: list[ChargebackReportRow]
    totals: dict[str, Decimal]
    currency: str
    generated_at: datetime


class ChargebackExportRequest(ChargebackReportRequest):
    format: Literal["csv", "ndjson"] = "csv"


class ChargebackExportResponse(BaseModel):
    filename: str
    content_type: str
    content: str


class CostForecastResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    period_start: datetime
    period_end: datetime
    forecast_cents: Decimal | None = None
    confidence_interval: dict[str, Any] = Field(default_factory=dict)
    currency: str = "USD"
    computed_at: datetime
    freshness_seconds: int | None = None


class CostAnomalyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    state: AnomalyState
    baseline_cents: Decimal
    observed_cents: Decimal
    period_start: datetime
    period_end: datetime
    summary: str
    correlation_fingerprint: str
    detected_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: UUID | None = None
    resolved_at: datetime | None = None


class AnomalyAcknowledgeRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class OverrideIssueRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class OverrideIssueResponse(BaseModel):
    token: str
    expires_at: datetime


class BudgetCheckResult(BaseModel):
    allowed: bool
    block_reason: str | None = None
    override_endpoint: str | None = None
    budget_cents: int | None = None
    projected_spend_cents: Decimal | None = None
    period_type: BudgetPeriodType | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None

