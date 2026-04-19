from __future__ import annotations

from platform.common.exceptions import NotFoundError
from platform.evaluation.exceptions import (
    CalibrationRunImmutableError,
    RubricArchivedError,
    RubricNotFoundError,
)
from platform.evaluation.models import CalibrationRun, CalibrationRunStatus, Rubric, RubricStatus
from platform.evaluation.schemas import CalibrationRunCreate
from platform.evaluation.scorers.base import ScoreResult
from platform.evaluation.scorers.registry import ScorerRegistry
from platform.evaluation.service import CalibrationService
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tests.evaluation_testing_support import SessionStub, build_benchmark_case, now_utc


def build_rubric_model(**overrides: object) -> Rubric:
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "name": "custom-rubric",
        "description": "desc",
        "criteria": [{"name": "accuracy", "description": "desc", "scale_min": 1, "scale_max": 5}],
        "version": 2,
        "is_builtin": False,
        "status": RubricStatus.active,
        "created_by": uuid4(),
        "deleted_at": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return Rubric(**payload)


def build_calibration_model(**overrides: object) -> CalibrationRun:
    payload = {
        "id": uuid4(),
        "rubric_id": uuid4(),
        "rubric_version": 2,
        "judge_model": "judge-v1",
        "reference_set_id": str(uuid4()),
        "status": CalibrationRunStatus.pending,
        "distribution": None,
        "agreement_rate": None,
        "calibrated": None,
        "error_grade_finding": False,
        "started_at": now_utc(),
        "completed_at": None,
        "created_by": uuid4(),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return CalibrationRun(**payload)


def apply_updates(model: object, **fields: object) -> object:
    for key, value in fields.items():
        setattr(model, key, value)
    return model


class JudgeStub:
    def __init__(self, result: ScoreResult) -> None:
        self.result = result

    async def score(self, *_args: object, **_kwargs: object) -> ScoreResult:
        return self.result


@pytest.mark.asyncio
async def test_calibration_service_starts_and_fetches_runs() -> None:
    actor_id = uuid4()
    workspace_id = uuid4()
    rubric = build_rubric_model(workspace_id=workspace_id)
    run = build_calibration_model(rubric_id=rubric.id)
    repository = SimpleNamespace(
        session=SessionStub(),
        get_rubric=AsyncMock(return_value=rubric),
        create_calibration_run=AsyncMock(return_value=run),
        get_calibration_run=AsyncMock(return_value=run),
    )
    service = CalibrationService(
        repository=repository,
        settings=SimpleNamespace(evaluation=SimpleNamespace(calibration_variance_envelope=0.2)),
        scorer_registry=ScorerRegistry(),
    )

    started = await service.start_calibration(
        rubric.id,
        CalibrationRunCreate(judge_model="judge-v1", reference_set_id="reference-1"),
        actor_id,
        workspace_id,
    )
    fetched = await service.get_calibration_run(run.id)

    assert started.id == run.id
    assert fetched.id == run.id
    assert repository.session.commits == 1


@pytest.mark.asyncio
async def test_calibration_service_executes_and_flags_error_grade_findings() -> None:
    rubric = build_rubric_model()
    run = build_calibration_model(rubric_id=rubric.id)
    repository = SimpleNamespace(
        session=SessionStub(),
        get_calibration_run=AsyncMock(return_value=run),
        get_rubric=AsyncMock(return_value=rubric),
        update_calibration_run=AsyncMock(
            side_effect=lambda model, **fields: apply_updates(model, **fields)
        ),
        list_all_benchmark_cases=AsyncMock(
            return_value=[build_benchmark_case(), build_benchmark_case()]
        ),
    )
    registry = ScorerRegistry()
    registry.register(
        "llm_judge",
        JudgeStub(ScoreResult(score=4.0, extra={"criteria_scores": {"accuracy": 4.0}})),
    )
    service = CalibrationService(
        repository=repository,
        settings=SimpleNamespace(evaluation=SimpleNamespace(calibration_variance_envelope=0.2)),
        scorer_registry=registry,
    )

    result = await service.execute_calibration(run.id)

    assert result.status is CalibrationRunStatus.completed
    assert result.error_grade_finding is True
    assert result.calibrated is False
    assert result.agreement_rate == 0.0
    assert result.distribution is not None
    assert result.distribution["overall"]["histogram"] == {"4": 2}
    assert repository.session.commits == 2


@pytest.mark.asyncio
async def test_calibration_service_handles_failure_and_immutable_runs() -> None:
    rubric = build_rubric_model()
    failed_run = build_calibration_model(rubric_id=rubric.id)
    completed_run = build_calibration_model(completed_at=now_utc())
    repository = SimpleNamespace(
        session=SessionStub(),
        get_calibration_run=AsyncMock(side_effect=[failed_run, completed_run, None]),
        get_rubric=AsyncMock(return_value=rubric),
        update_calibration_run=AsyncMock(
            side_effect=lambda model, **fields: apply_updates(model, **fields)
        ),
        list_all_benchmark_cases=AsyncMock(return_value=[build_benchmark_case()]),
    )
    registry = ScorerRegistry()
    registry.register("llm_judge", JudgeStub(ScoreResult(error="judge_failure_permanent")))
    service = CalibrationService(
        repository=repository,
        settings=SimpleNamespace(evaluation=SimpleNamespace(calibration_variance_envelope=0.2)),
        scorer_registry=registry,
    )

    failed = await service.execute_calibration(failed_run.id)
    assert failed.status is CalibrationRunStatus.failed
    assert failed.distribution == {"error": "judge_failure_permanent"}

    with pytest.raises(CalibrationRunImmutableError):
        await service.execute_calibration(completed_run.id)

    with pytest.raises(NotFoundError):
        await service.get_calibration_run(uuid4())


@pytest.mark.asyncio
async def test_calibration_service_rejects_archived_rubrics() -> None:
    archived_rubric = build_rubric_model(status=RubricStatus.archived)
    repository = SimpleNamespace(
        session=SessionStub(),
        get_rubric=AsyncMock(return_value=archived_rubric),
    )
    service = CalibrationService(
        repository=repository,
        settings=SimpleNamespace(evaluation=SimpleNamespace(calibration_variance_envelope=0.2)),
        scorer_registry=ScorerRegistry(),
    )

    with pytest.raises(RubricArchivedError):
        await service.start_calibration(
            archived_rubric.id,
            CalibrationRunCreate(judge_model="judge-v1", reference_set_id="reference-1"),
            uuid4(),
        )


@pytest.mark.asyncio
async def test_calibration_service_handles_reference_set_edge_cases() -> None:
    repository = SimpleNamespace(session=SessionStub(), get_rubric=AsyncMock(return_value=None))
    service = CalibrationService(
        repository=repository,
        settings=SimpleNamespace(evaluation=SimpleNamespace(calibration_variance_envelope=0.2)),
        scorer_registry=ScorerRegistry(),
    )

    assert await service._load_reference_cases("not-a-uuid") == []
    with pytest.raises(RubricNotFoundError):
        await service._get_rubric(uuid4(), None)
