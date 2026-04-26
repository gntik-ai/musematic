from __future__ import annotations

from datetime import datetime
from platform.evaluation.models import (
    ATERunStatus,
    CalibrationRunStatus,
    EvalSetStatus,
    ExperimentStatus,
    ReviewDecision,
    RubricStatus,
    RunStatus,
    VerdictStatus,
)
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FairnessCase(BaseModel):
    id: str | None = None
    input_data: dict[str, Any] = Field(default_factory=dict)
    expected: str | int | float | bool | None = None
    actual: str | int | float | bool | None = None
    label: str | int | float | bool | None = None
    prediction: str | int | float | bool | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    group_attributes: dict[str, str] = Field(default_factory=dict)


class FairnessScorerConfig(BaseModel):
    metrics: list[str] = Field(
        default_factory=lambda: ["demographic_parity", "equal_opportunity", "calibration"]
    )
    group_attributes: list[str] = Field(default_factory=list)
    fairness_band: float = Field(default=0.10, ge=0.0, le=1.0)
    min_group_size: int = Field(default=5, ge=1)
    positive_class: str = "positive"
    preview: bool = False


class FairnessMetricRow(BaseModel):
    evaluation_run_id: UUID
    agent_id: UUID
    agent_revision_id: str
    suite_id: UUID
    metric_name: str
    group_attribute: str
    per_group_scores: dict[str, float]
    spread: float
    fairness_band: float
    passed: bool
    coverage: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    evaluated_by: UUID | None = None
    computed_at: datetime | None = None


class FairnessScorerResult(BaseModel):
    evaluation_run_id: UUID
    status: str = "completed"
    rows: list[FairnessMetricRow] = Field(default_factory=list)
    overall_passed: bool
    coverage: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class FairnessRunRequest(BaseModel):
    workspace_id: UUID | None = None
    evaluation_run_id: UUID | None = None
    agent_id: UUID
    agent_revision_id: str = Field(min_length=1, max_length=255)
    suite_id: UUID
    cases: list[FairnessCase] = Field(min_length=1)
    config: FairnessScorerConfig = Field(default_factory=FairnessScorerConfig)


class FairnessEvaluationSummary(BaseModel):
    evaluation_run_id: UUID
    agent_id: UUID
    agent_revision_id: str
    suite_id: UUID
    overall_passed: bool
    metric_count: int
    computed_at: datetime | None = None


class FairnessRunResponse(BaseModel):
    evaluation_run_id: UUID
    status: str
    rows: list[FairnessMetricRow] = Field(default_factory=list)
    overall_passed: bool | None = None
    notes: list[str] = Field(default_factory=list)


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class EvalSetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    scorer_config: dict[str, dict[str, Any]] = Field(default_factory=dict)
    pass_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class EvalSetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    scorer_config: dict[str, dict[str, Any]] | None = None
    pass_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    status: EvalSetStatus | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class EvalSetResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    scorer_config: dict[str, Any]
    pass_threshold: float
    status: EvalSetStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvalSetListResponse(BaseModel):
    items: list[EvalSetResponse]
    total: int
    page: int = 1
    page_size: int = 20


class BenchmarkCaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_data: dict[str, Any] = Field(default_factory=dict)
    expected_output: str = Field(min_length=1)
    scoring_criteria: dict[str, Any] = Field(default_factory=dict)
    metadata_tags: dict[str, Any] = Field(default_factory=dict)
    category: str | None = Field(default=None, max_length=64)
    position: int | None = Field(default=None, ge=0)

    @field_validator("expected_output")
    @classmethod
    def normalize_expected_output(cls, value: str) -> str:
        return value.strip()

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class BenchmarkCaseResponse(BaseModel):
    id: UUID
    eval_set_id: UUID
    input_data: dict[str, Any]
    expected_output: str
    scoring_criteria: dict[str, Any]
    metadata_tags: dict[str, Any]
    category: str | None
    position: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BenchmarkCaseListResponse(BaseModel):
    items: list[BenchmarkCaseResponse]
    total: int
    page: int = 1
    page_size: int = 50


class EvaluationRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_fqn: str = Field(min_length=1, max_length=512)
    agent_id: UUID | None = None

    @field_validator("agent_fqn")
    @classmethod
    def normalize_agent_fqn(cls, value: str) -> str:
        return value.strip()


class EvaluationRunResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    eval_set_id: UUID
    agent_fqn: str
    agent_id: UUID | None
    status: RunStatus
    started_at: datetime | None
    completed_at: datetime | None
    total_cases: int
    passed_cases: int
    failed_cases: int
    error_cases: int
    aggregate_score: float | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationRunListResponse(BaseModel):
    items: list[EvaluationRunResponse]
    total: int
    page: int = 1
    page_size: int = 20


class HumanAiGradeResponse(BaseModel):
    id: UUID
    verdict_id: UUID
    reviewer_id: UUID
    decision: ReviewDecision
    override_score: float | None
    feedback: str | None
    original_score: float
    reviewed_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JudgeVerdictResponse(BaseModel):
    id: UUID
    run_id: UUID
    benchmark_case_id: UUID
    actual_output: str
    scorer_results: dict[str, Any]
    overall_score: float | None
    passed: bool | None
    error_detail: str | None
    status: VerdictStatus
    human_grade: HumanAiGradeResponse | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JudgeVerdictListResponse(BaseModel):
    items: list[JudgeVerdictResponse]
    total: int
    page: int = 1
    page_size: int = 50


class AbExperimentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    name: str = Field(min_length=1, max_length=255)
    run_a_id: UUID
    run_b_id: UUID

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class AbExperimentResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    run_a_id: UUID
    run_b_id: UUID
    status: ExperimentStatus
    p_value: float | None
    confidence_interval: dict[str, Any] | None
    effect_size: float | None
    winner: str | None
    analysis_summary: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RubricCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    scale: int | None = Field(default=None, ge=1)
    scale_min: int = Field(default=1, ge=1)
    scale_max: int | None = Field(default=None, ge=1)
    examples: dict[str, str] = Field(default_factory=dict)

    @field_validator("name", "description")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_scale(self) -> RubricCriterion:
        if self.scale is not None and self.scale_max is None:
            self.scale_max = self.scale
        if self.scale_max is None:
            self.scale_max = 5
        if self.scale_min >= self.scale_max:
            raise ValueError("Rubric criterion scale_min must be lower than scale_max")
        for raw_key in self.examples:
            try:
                numeric = int(raw_key)
            except ValueError as exc:  # pragma: no cover - defensive
                raise ValueError("Rubric example keys must be numeric") from exc
            if numeric < self.scale_min or numeric > self.scale_max:
                raise ValueError("Rubric example keys must fall within the criterion scale")
        return self


class RubricConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: str | None = None
    custom_criteria: list[RubricCriterion] | None = None


class LLMJudgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    judge_model: str = Field(min_length=1)
    rubric: RubricConfig | None = None
    rubric_id: UUID | None = None
    calibration_runs: int = Field(default=3, ge=1, le=20)

    @model_validator(mode="after")
    def validate_rubric_source(self) -> LLMJudgeConfig:
        if self.rubric is None and self.rubric_id is None:
            raise ValueError("Either rubric or rubric_id must be provided")
        return self


class CalibrationDistribution(BaseModel):
    mean: float
    stddev: float
    confidence_interval: dict[str, float]
    runs: list[float]
    low_confidence: bool = False


class TrajectoryScore(BaseModel):
    efficiency_score: float = Field(ge=0.0, le=1.0)
    tool_appropriateness_score: float = Field(ge=0.0, le=1.0)
    reasoning_coherence_score: float = Field(ge=0.0, le=1.0)
    cost_effectiveness_score: float = Field(ge=0.0, le=1.0)
    overall_trajectory_score: float = Field(ge=0.0, le=1.0)
    llm_judge_holistic: dict[str, Any] | None = None


class CooperationScoreResult(BaseModel):
    per_agent_scores: dict[str, dict[str, Any]]
    coordination_overhead: float = Field(ge=0.0, le=1.0)
    handoff_timeliness: float = Field(ge=0.0, le=1.0)
    redundancy: float = Field(ge=0.0, le=1.0)
    joint_path_efficiency: float = Field(ge=0.0, le=1.0)
    cycle_flags: list[dict[str, Any]] = Field(default_factory=list)


class RubricCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    criteria: list[RubricCriterion] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def normalize_rubric_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_rubric_description(cls, value: str) -> str:
        return value.strip()


class RubricUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    criteria: list[RubricCriterion] | None = None
    status: RubricStatus | None = None

    @field_validator("name")
    @classmethod
    def normalize_optional_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("description")
    @classmethod
    def normalize_optional_description(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class RubricResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None
    name: str
    description: str
    criteria: list[dict[str, Any]]
    version: int
    is_builtin: bool
    status: RubricStatus
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RubricListResponse(BaseModel):
    items: list[RubricResponse]
    total: int
    page: int = 1
    page_size: int = 20


class CalibrationRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    judge_model: str = Field(min_length=1)
    reference_set_id: str = Field(min_length=1)

    @field_validator("judge_model", "reference_set_id")
    @classmethod
    def normalize_calibration_text(cls, value: str) -> str:
        return value.strip()


class CalibrationRunResponse(BaseModel):
    id: UUID
    rubric_id: UUID
    rubric_version: int
    judge_model: str
    reference_set_id: str
    status: CalibrationRunStatus
    distribution: dict[str, Any] | None
    agreement_rate: float | None
    calibrated: bool | None
    error_grade_finding: bool
    started_at: datetime
    completed_at: datetime | None
    created_by: UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdHocJudgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric_id: UUID | None = None
    rubric: RubricCreate | None = None
    output: str = Field(min_length=1)
    judge_model: str | None = None

    @field_validator("output")
    @classmethod
    def normalize_output(cls, value: str) -> str:
        return value.strip()

    @field_validator("judge_model")
    @classmethod
    def normalize_judge_model(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_rubric_selector(self) -> AdHocJudgeRequest:
        if self.rubric_id is None and self.rubric is None:
            raise ValueError("Either rubric_id or rubric must be provided")
        return self


class AdHocJudgeResponse(BaseModel):
    rubric_id: UUID | None
    rubric_version: int | None
    judge_model: str
    per_criterion_scores: dict[str, dict[str, Any]]
    overall_score: float | None
    aggregation_method: str = "arithmetic_mean"
    rationale: str | None
    principal_id: UUID
    timestamp: datetime
    duration_ms: int


class ScorerTypeListResponse(BaseModel):
    items: list[str]


class RubricTemplateSummary(BaseModel):
    name: str
    description: str
    criteria_count: int
    rubric_id: UUID


class RubricTemplateListResponse(BaseModel):
    items: list[RubricTemplateSummary]
    total: int


class ATEConfigCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    scenarios: list[dict[str, Any]] = Field(default_factory=list)
    scorer_config: dict[str, Any] = Field(default_factory=dict)
    performance_thresholds: dict[str, Any] = Field(default_factory=dict)
    safety_checks: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class ATEConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    scenarios: list[dict[str, Any]] | None = None
    scorer_config: dict[str, Any] | None = None
    performance_thresholds: dict[str, Any] | None = None
    safety_checks: list[dict[str, Any]] | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class ATEConfigResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    scenarios: list[dict[str, Any]]
    scorer_config: dict[str, Any]
    performance_thresholds: dict[str, Any]
    safety_checks: list[dict[str, Any]]
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ATEConfigListResponse(BaseModel):
    items: list[ATEConfigResponse]
    total: int
    page: int = 1
    page_size: int = 20


class ATERunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: UUID | None = None


class ATERunResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    ate_config_id: UUID
    agent_fqn: str
    agent_id: UUID | None
    simulation_id: UUID | None
    status: ATERunStatus
    started_at: datetime | None
    completed_at: datetime | None
    evidence_artifact_key: str | None
    report: dict[str, Any] | None
    pre_check_errors: list[Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ATERunListResponse(BaseModel):
    items: list[ATERunResponse]
    total: int
    page: int = 1
    page_size: int = 20


class RobustnessRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    eval_set_id: UUID
    agent_fqn: str = Field(min_length=1, max_length=512)
    trial_count: int = Field(ge=1, le=100)
    benchmark_case_id: UUID | None = None
    variance_threshold: float = Field(default=0.15, ge=0.0)


class RobustnessTestRunResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    eval_set_id: UUID
    benchmark_case_id: UUID | None
    agent_fqn: str
    trial_count: int
    completed_trials: int
    status: RunStatus
    distribution: dict[str, Any] | None
    is_unreliable: bool
    variance_threshold: float
    trial_run_ids: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HumanGradeSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    override_score: float | None = Field(default=None, ge=0.0)
    feedback: str | None = None

    @field_validator("feedback")
    @classmethod
    def normalize_feedback(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class HumanGradeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    override_score: float | None = Field(default=None, ge=0.0)
    feedback: str | None = None

    @field_validator("feedback")
    @classmethod
    def normalize_feedback(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class ReviewProgressResponse(BaseModel):
    total_verdicts: int
    pending_review: int
    reviewed: int
    overridden: int


class EvalRunSummaryDTO(BaseModel):
    run_id: UUID
    eval_set_id: UUID
    workspace_id: UUID
    agent_fqn: str
    aggregate_score: float | None
    passed_cases: int
    failed_cases: int
    error_cases: int
    total_cases: int
    status: RunStatus
