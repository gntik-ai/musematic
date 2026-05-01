from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RunStatus = Literal["provisioning", "running", "completed", "cancelled", "failed", "timeout"]
PredictionStatus = Literal["pending", "completed", "insufficient_data", "failed"]
ConfidenceLevel = Literal["high", "medium", "low", "insufficient_data"]
ComparisonType = Literal[
    "simulation_vs_simulation",
    "simulation_vs_production",
    "prediction_vs_actual",
]
ComparisonVerdict = Literal[
    "primary_better",
    "secondary_better",
    "equivalent",
    "inconclusive",
]


class SimulationRunCreateRequest(BaseModel):
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    digital_twin_ids: list[UUID] = Field(min_length=1)
    scenario_config: dict[str, Any] = Field(default_factory=dict)
    isolation_policy_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped

    @model_validator(mode="after")
    def _validate_duration(self) -> SimulationRunCreateRequest:
        duration = self.scenario_config.get("duration_seconds")
        if duration is not None and int(duration) <= 0:
            raise ValueError("scenario_config.duration_seconds must be positive")
        return self


class SimulationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    run_id: UUID = Field(validation_alias="id", serialization_alias="run_id")
    workspace_id: UUID
    name: str
    description: str | None = None
    status: RunStatus
    digital_twin_ids: list[UUID]
    scenario_config: dict[str, Any]
    isolation_policy_id: UUID | None = None
    scenario_id: UUID | None = None
    controller_run_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    results: dict[str, Any] | None = None
    initiated_by: UUID
    created_at: datetime

    @field_validator("digital_twin_ids", mode="before")
    @classmethod
    def _coerce_twin_ids(cls, value: Any) -> list[UUID]:
        return [item if isinstance(item, UUID) else UUID(str(item)) for item in value or []]


class SimulationRunListResponse(BaseModel):
    items: list[SimulationRunResponse]
    next_cursor: str | None = None


class ScenarioCreate(BaseModel):
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    agents_config: dict[str, Any] = Field(default_factory=dict)
    workflow_template_id: UUID | None = None
    mock_set_config: dict[str, Any] = Field(default_factory=dict)
    input_distribution: dict[str, Any] = Field(default_factory=dict)
    twin_fidelity: dict[str, Any] = Field(default_factory=dict)
    success_criteria: list[dict[str, Any]] = Field(min_length=1)
    run_schedule: dict[str, Any] | None = None


class ScenarioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    agents_config: dict[str, Any] | None = None
    workflow_template_id: UUID | None = None
    mock_set_config: dict[str, Any] | None = None
    input_distribution: dict[str, Any] | None = None
    twin_fidelity: dict[str, Any] | None = None
    success_criteria: list[dict[str, Any]] | None = None
    run_schedule: dict[str, Any] | None = None


class ScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    description: str | None = None
    agents_config: dict[str, Any]
    workflow_template_id: UUID | None = None
    mock_set_config: dict[str, Any]
    input_distribution: dict[str, Any]
    twin_fidelity: dict[str, Any]
    success_criteria: list[dict[str, Any]]
    run_schedule: dict[str, Any] | None = None
    archived_at: datetime | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class ScenarioListResponse(BaseModel):
    items: list[ScenarioRead]
    next_cursor: str | None = None


class ScenarioRunRequest(BaseModel):
    iterations: int = Field(default=1, ge=1, le=100)
    use_real_llm: bool = False
    confirmation_token: str | None = None


class ScenarioRunSummary(BaseModel):
    scenario_id: UUID
    queued_runs: list[UUID]
    iterations: int


class DigitalTwinDivergenceReportRead(BaseModel):
    run_id: UUID
    mock_components: list[str]
    real_components: list[str]
    divergence_points: list[dict[str, Any]]
    simulated_time_ms: int | None = None
    wall_clock_time_ms: int | None = None
    reference_execution_id: str | None = None
    reference_available: bool = False


class DigitalTwinCreateRequest(BaseModel):
    workspace_id: UUID
    agent_fqn: str = Field(min_length=1, max_length=255)
    revision_id: UUID | None = None
    description: str | None = None


class DigitalTwinModification(BaseModel):
    field: str = Field(min_length=1)
    value: Any
    description: str | None = None


class DigitalTwinModifyRequest(BaseModel):
    modifications: list[DigitalTwinModification] = Field(min_length=1)


class DigitalTwinResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    twin_id: UUID = Field(validation_alias="id", serialization_alias="twin_id")
    workspace_id: UUID
    source_agent_fqn: str
    source_revision_id: UUID | None = None
    version: int
    parent_twin_id: UUID | None = None
    config_snapshot: dict[str, Any]
    behavioral_history_summary: dict[str, Any]
    modifications: list[dict[str, Any]]
    is_active: bool
    created_at: datetime
    warning_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _populate_warning_flags(self) -> DigitalTwinResponse:
        if not self.warning_flags:
            flags = self.behavioral_history_summary.get("warning_flags", [])
            self.warning_flags = [str(flag) for flag in flags]
        return self


class DigitalTwinListResponse(BaseModel):
    items: list[DigitalTwinResponse]
    next_cursor: str | None = None


class DigitalTwinVersionListResponse(BaseModel):
    items: list[DigitalTwinResponse]
    total_versions: int


class SimulationIsolationPolicyCreateRequest(BaseModel):
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    blocked_actions: list[dict[str, Any]] = Field(default_factory=list)
    stubbed_actions: list[dict[str, Any]] = Field(default_factory=list)
    permitted_read_sources: list[dict[str, Any]] = Field(default_factory=list)
    is_default: bool = False
    halt_on_critical_breach: bool = True


class SimulationIsolationPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    policy_id: UUID = Field(validation_alias="id", serialization_alias="policy_id")
    workspace_id: UUID
    name: str
    description: str | None = None
    blocked_actions: list[dict[str, Any]]
    stubbed_actions: list[dict[str, Any]]
    permitted_read_sources: list[dict[str, Any]]
    is_default: bool
    halt_on_critical_breach: bool
    created_at: datetime
    updated_at: datetime


class SimulationIsolationPolicyListResponse(BaseModel):
    items: list[SimulationIsolationPolicyResponse]


class BehavioralPredictionCreateRequest(BaseModel):
    workspace_id: UUID
    condition_modifiers: dict[str, Any] = Field(default_factory=dict)

    @field_validator("condition_modifiers")
    @classmethod
    def _validate_load_factor(cls, value: dict[str, Any]) -> dict[str, Any]:
        load_factor = value.get("load_factor")
        if load_factor is not None and float(load_factor) <= 0:
            raise ValueError("condition_modifiers.load_factor must be positive")
        return value


class BehavioralPredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    prediction_id: UUID = Field(validation_alias="id", serialization_alias="prediction_id")
    digital_twin_id: UUID
    status: PredictionStatus
    condition_modifiers: dict[str, Any]
    predicted_metrics: dict[str, Any] | None = None
    confidence_level: ConfidenceLevel | None = None
    history_days_used: int
    accuracy_report: dict[str, Any] | None = None
    created_at: datetime


class SimulationComparisonCreateRequest(BaseModel):
    workspace_id: UUID
    comparison_type: ComparisonType
    secondary_run_id: UUID | None = None
    production_baseline_period: dict[str, Any] | None = None
    prediction_id: UUID | None = None

    @model_validator(mode="after")
    def _validate_configuration(self) -> SimulationComparisonCreateRequest:
        if self.comparison_type == "simulation_vs_simulation" and self.secondary_run_id is None:
            raise ValueError("secondary_run_id is required for simulation_vs_simulation")
        if self.comparison_type == "prediction_vs_actual" and self.prediction_id is None:
            raise ValueError("prediction_id is required for prediction_vs_actual")
        return self


class SimulationComparisonReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    report_id: UUID = Field(validation_alias="id", serialization_alias="report_id")
    comparison_type: ComparisonType
    primary_run_id: UUID
    secondary_run_id: UUID | None = None
    production_baseline_period: dict[str, Any] | None = None
    prediction_id: UUID | None = None
    status: Literal["pending", "completed", "failed"]
    compatible: bool
    incompatibility_reasons: list[str]
    metric_differences: list[dict[str, Any]]
    overall_verdict: ComparisonVerdict | None = None
    created_at: datetime


class SimulationSummary(BaseModel):
    run_id: UUID
    status: str
    name: str
    digital_twin_ids: list[UUID]
    completed_at: datetime | None = None
    results_summary: dict[str, Any] | None = None


class TwinConfigSnapshot(BaseModel):
    twin_id: UUID
    source_agent_fqn: str
    version: int
    config_snapshot: dict[str, Any]
