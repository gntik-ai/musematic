from __future__ import annotations

from datetime import datetime
from platform.evaluation.models import (
    ATERunStatus,
    EvalSetStatus,
    ExperimentStatus,
    ReviewDecision,
    RunStatus,
    VerdictStatus,
)
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    scale: int = Field(default=5, ge=1)
    examples: list[str] = Field(default_factory=list)


class RubricConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: str | None = None
    custom_criteria: list[RubricCriterion] | None = None


class LLMJudgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    judge_model: str = Field(min_length=1)
    rubric: RubricConfig
    calibration_runs: int = Field(default=3, ge=1, le=20)


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
