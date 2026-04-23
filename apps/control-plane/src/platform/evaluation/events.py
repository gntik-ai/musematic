from __future__ import annotations

from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class EvaluationEventType(StrEnum):
    run_started = "evaluation.run.started"
    run_completed = "evaluation.run.completed"
    run_failed = "evaluation.run.failed"
    verdict_scored = "evaluation.verdict.scored"
    ab_experiment_completed = "evaluation.ab_experiment.completed"
    ate_run_completed = "evaluation.ate.run.completed"
    ate_run_failed = "evaluation.ate.run.failed"
    robustness_completed = "evaluation.robustness.completed"
    drift_detected = "evaluation.drift.detected"
    human_grade_submitted = "evaluation.human.grade.submitted"
    rubric_created = "evaluation.rubric.created"
    rubric_updated = "evaluation.rubric.updated"
    rubric_archived = "evaluation.rubric.archived"
    calibration_started = "evaluation.calibration.started"
    calibration_completed = "evaluation.calibration.completed"
    judge_adhoc = "evaluation.judge.adhoc"


class RunStartedPayload(BaseModel):
    run_id: UUID
    eval_set_id: UUID
    workspace_id: UUID
    agent_fqn: str


class RunCompletedPayload(BaseModel):
    run_id: UUID
    eval_set_id: UUID
    workspace_id: UUID
    aggregate_score: float | None
    passed_cases: int
    total_cases: int


class RunFailedPayload(BaseModel):
    run_id: UUID
    eval_set_id: UUID
    workspace_id: UUID
    error_detail: str


class VerdictScoredPayload(BaseModel):
    verdict_id: UUID
    run_id: UUID
    case_id: UUID
    overall_score: float | None
    passed: bool | None


class AbExperimentCompletedPayload(BaseModel):
    experiment_id: UUID
    workspace_id: UUID
    winner: str | None
    p_value: float | None
    effect_size: float | None


class ATERunCompletedPayload(BaseModel):
    ate_run_id: UUID
    ate_config_id: UUID
    workspace_id: UUID
    agent_fqn: str
    report_summary: dict[str, object] | None = None


class ATERunFailedPayload(BaseModel):
    ate_run_id: UUID
    ate_config_id: UUID
    workspace_id: UUID
    pre_check_errors: list[object]


class RobustnessCompletedPayload(BaseModel):
    robustness_run_id: UUID
    workspace_id: UUID
    is_unreliable: bool
    distribution: dict[str, object] | None = None


class DriftDetectedPayload(BaseModel):
    alert_id: UUID
    workspace_id: UUID
    agent_fqn: str
    metric_name: str
    stddevs: float


class HumanGradeSubmittedPayload(BaseModel):
    grade_id: UUID
    verdict_id: UUID
    workspace_id: UUID
    decision: str


class RubricCreatedPayload(BaseModel):
    rubric_id: UUID
    workspace_id: UUID | None
    name: str
    version: int


class RubricUpdatedPayload(BaseModel):
    rubric_id: UUID
    old_version: int
    new_version: int


class RubricArchivedPayload(BaseModel):
    rubric_id: UUID
    workspace_id: UUID | None


class CalibrationStartedPayload(BaseModel):
    run_id: UUID
    rubric_id: UUID
    rubric_version: int


class CalibrationCompletedPayload(BaseModel):
    run_id: UUID
    rubric_id: UUID
    calibrated: bool | None
    error_grade_finding: bool


class AdHocJudgePayload(BaseModel):
    rubric_id: UUID | None
    judge_model: str
    principal_id: UUID
    duration_ms: int


EVALUATION_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    EvaluationEventType.run_started.value: RunStartedPayload,
    EvaluationEventType.run_completed.value: RunCompletedPayload,
    EvaluationEventType.run_failed.value: RunFailedPayload,
    EvaluationEventType.verdict_scored.value: VerdictScoredPayload,
    EvaluationEventType.ab_experiment_completed.value: AbExperimentCompletedPayload,
    EvaluationEventType.ate_run_completed.value: ATERunCompletedPayload,
    EvaluationEventType.ate_run_failed.value: ATERunFailedPayload,
    EvaluationEventType.robustness_completed.value: RobustnessCompletedPayload,
    EvaluationEventType.drift_detected.value: DriftDetectedPayload,
    EvaluationEventType.human_grade_submitted.value: HumanGradeSubmittedPayload,
    EvaluationEventType.rubric_created.value: RubricCreatedPayload,
    EvaluationEventType.rubric_updated.value: RubricUpdatedPayload,
    EvaluationEventType.rubric_archived.value: RubricArchivedPayload,
    EvaluationEventType.calibration_started.value: CalibrationStartedPayload,
    EvaluationEventType.calibration_completed.value: CalibrationCompletedPayload,
    EvaluationEventType.judge_adhoc.value: AdHocJudgePayload,
}


def register_evaluation_event_types() -> None:
    for event_type, schema in EVALUATION_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def _publish(
    *,
    producer: EventProducer | None,
    event_type: EvaluationEventType,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
    key: str,
) -> None:
    if producer is None:
        return
    await producer.publish(
        topic="evaluation.events",
        key=key,
        event_type=event_type.value,
        payload=payload.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.evaluation",
    )


async def publish_evaluation_event(
    producer: EventProducer | None,
    event_type: EvaluationEventType,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
) -> None:
    key = str(
        getattr(payload, "run_id", None)
        or getattr(payload, "experiment_id", None)
        or getattr(payload, "ate_run_id", None)
        or getattr(payload, "robustness_run_id", None)
        or getattr(payload, "alert_id", None)
        or getattr(payload, "grade_id", None)
        or getattr(payload, "rubric_id", None)
        or getattr(payload, "principal_id", None)
        or correlation_ctx.correlation_id
    )
    await _publish(
        producer=producer,
        event_type=event_type,
        payload=payload,
        correlation_ctx=correlation_ctx,
        key=key,
    )
