from __future__ import annotations

from platform.evaluation.models import CalibrationRun, CalibrationRunStatus, Rubric, RubricStatus
from platform.evaluation.repository import EvaluationRepository
from uuid import uuid4

import pytest
from tests.evaluation_testing_support import ResultStub, SessionStub, now_utc


def build_rubric(**overrides: object) -> Rubric:
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "name": "custom-rubric",
        "description": "desc",
        "criteria": [{"name": "accuracy", "description": "desc", "scale_min": 1, "scale_max": 5}],
        "version": 1,
        "is_builtin": False,
        "status": RubricStatus.active,
        "created_by": uuid4(),
        "deleted_at": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return Rubric(**payload)


def build_calibration_run(**overrides: object) -> CalibrationRun:
    payload = {
        "id": uuid4(),
        "rubric_id": uuid4(),
        "rubric_version": 1,
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


@pytest.mark.asyncio
async def test_repository_supports_rubric_and_calibration_crud() -> None:
    session = SessionStub()
    repository = EvaluationRepository(session)
    rubric = build_rubric()
    builtin = build_rubric(workspace_id=None, is_builtin=True, name="correctness")
    calibration_run = build_calibration_run(rubric_id=rubric.id)
    session.queue_execute(
        ResultStub(scalar_one_or_none=rubric),
        ResultStub(scalar_one_or_none=builtin),
        ResultStub(scalar_one_or_none=rubric),
        ResultStub(scalars=[builtin, rubric]),
        ResultStub(scalars=[builtin]),
        ResultStub(scalar_one_or_none=calibration_run),
    )
    session.queue_scalar(2, 1, 3)

    created_rubric = await repository.create_rubric(rubric)
    fetched_rubric = await repository.get_rubric(rubric.id, rubric.workspace_id)
    builtin_rubric = await repository.get_builtin_rubric_by_name("correctness")
    workspace_rubric = await repository.get_workspace_rubric_by_name(
        rubric.workspace_id, rubric.name
    )
    listed_rubrics, total = await repository.list_rubrics(
        rubric.workspace_id,
        status=None,
        include_builtins=True,
        page=1,
        page_size=10,
    )
    builtin_only, builtin_total = await repository.list_rubrics(
        None,
        status=RubricStatus.active,
        include_builtins=True,
        page=1,
        page_size=10,
    )
    updated_rubric = await repository.update_rubric(rubric, description="updated")
    archived_rubric = await repository.soft_delete_rubric(rubric)
    in_flight = await repository.count_in_flight_rubric_references(rubric.id)
    created_run = await repository.create_calibration_run(calibration_run)
    fetched_run = await repository.get_calibration_run(calibration_run.id)
    updated_run = await repository.update_calibration_run(
        calibration_run,
        status=CalibrationRunStatus.completed,
        calibrated=True,
    )

    assert created_rubric is rubric
    assert fetched_rubric is rubric
    assert builtin_rubric is builtin
    assert workspace_rubric is rubric
    assert listed_rubrics == [builtin, rubric]
    assert total == 2
    assert builtin_only == [builtin]
    assert builtin_total == 1
    assert updated_rubric.description == "updated"
    assert archived_rubric.deleted_at is not None
    assert in_flight == 3
    assert created_run is calibration_run
    assert fetched_run is calibration_run
    assert updated_run.status is CalibrationRunStatus.completed
    assert updated_run.calibrated is True
    assert session.flushed >= 5
