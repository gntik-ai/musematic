from __future__ import annotations

from platform.evaluation.exceptions import JudgeUnavailableError, RubricArchivedError
from platform.evaluation.models import Rubric, RubricStatus
from platform.evaluation.schemas import AdHocJudgeRequest, RubricCreate, RubricCriterion
from platform.evaluation.scorers.base import ScoreResult
from platform.evaluation.scorers.registry import ScorerRegistry
from platform.evaluation.service import EvalRunnerService
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.evaluation_testing_support import SessionStub, build_run, now_utc


class TrajectoryScorerStub:
    def __init__(self) -> None:
        self.used_cooperation = False

    async def score(self, *_args: object, **_kwargs: object) -> ScoreResult:
        return ScoreResult(score=0.1, passed=False)

    async def score_cooperation(self, *_args: object, **_kwargs: object) -> ScoreResult:
        self.used_cooperation = True
        return ScoreResult(score=0.8, passed=True, extra={"joint_path_efficiency": 0.8})


class JudgeScorerStub:
    def __init__(self, result: ScoreResult) -> None:
        self.result = result

    async def score(self, *_args: object, **_kwargs: object) -> ScoreResult:
        return self.result


class RubricServiceStub:
    def __init__(self, rubric: Rubric) -> None:
        self.rubric = rubric

    async def get_rubric_model(self, *_args: object, **_kwargs: object) -> Rubric:
        return self.rubric


class EvalRunRepositoryStub:
    def __init__(self, run: object | None) -> None:
        self.run = run
        self.session = SessionStub()
        self.deleted: list[object] = []

    async def get_run(self, *_args: object, **_kwargs: object) -> object | None:
        return self.run

    async def delete_run(self, run: object) -> None:
        self.deleted.append(run)


class TagCascadeStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def cascade_on_entity_deletion(self, entity_type: str, entity_id: object) -> None:
        self.calls.append((entity_type, entity_id))


def build_rubric(**overrides: object) -> Rubric:
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "name": "custom-rubric",
        "description": "desc",
        "criteria": [{"name": "accuracy", "description": "desc", "scale_min": 1, "scale_max": 5}],
        "version": 4,
        "is_builtin": False,
        "status": RubricStatus.active,
        "created_by": uuid4(),
        "deleted_at": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return Rubric(**payload)


@pytest.mark.asyncio
async def test_eval_runner_score_outputs_uses_cooperation_mode() -> None:
    registry = ScorerRegistry()
    trajectory = TrajectoryScorerStub()
    registry.register("trajectory", trajectory)
    service = EvalRunnerService(
        repository=SimpleNamespace(session=SessionStub()),
        settings=SimpleNamespace(),
        scorer_registry=registry,
    )

    (
        scorer_results,
        overall_score,
        passed,
        verdict_status,
        error_detail,
    ) = await service.score_outputs(
        expected_output="expected",
        actual_output="actual",
        scorer_config={
            "trajectory": {
                "enabled": True,
                "cooperation_mode": True,
                "agent_execution_ids": [str(uuid4()), str(uuid4())],
                "threshold": 0.5,
            }
        },
        input_data={"execution_id": str(uuid4())},
        pass_threshold=0.5,
    )

    assert trajectory.used_cooperation is True
    assert scorer_results["trajectory"]["score"] == 0.8
    assert overall_score == 0.8
    assert passed is True
    assert verdict_status.value == "scored"
    assert error_detail is None


@pytest.mark.asyncio
async def test_eval_runner_judge_adhoc_uses_rubric_id_and_lists_scorers() -> None:
    rubric = build_rubric()
    registry = ScorerRegistry()
    registry.register(
        "llm_judge",
        JudgeScorerStub(
            ScoreResult(
                score=4.5,
                rationale="good",
                extra={"criteria_scores": {"accuracy": 4.5}, "out_of_range_clamped": {}},
            )
        ),
    )
    registry.register("trajectory", TrajectoryScorerStub())
    service = EvalRunnerService(
        repository=SimpleNamespace(session=SessionStub()),
        settings=SimpleNamespace(evaluation=SimpleNamespace(llm_judge_model="judge-default")),
        scorer_registry=registry,
        rubric_service=RubricServiceStub(rubric),
    )

    response = await service.judge_adhoc(
        AdHocJudgeRequest(rubric_id=rubric.id, output="answer", judge_model="judge-v1"),
        uuid4(),
    )

    assert response.rubric_id == rubric.id
    assert response.rubric_version == 4
    assert response.per_criterion_scores["accuracy"]["score"] == 4.5
    assert service.list_scorer_types() == ["llm_judge", "trajectory"]


@pytest.mark.asyncio
async def test_eval_runner_judge_adhoc_handles_inline_and_failure_paths() -> None:
    registry = ScorerRegistry()
    registry.register("llm_judge", JudgeScorerStub(ScoreResult(error="judge_failure_permanent")))
    service = EvalRunnerService(
        repository=SimpleNamespace(session=SessionStub()),
        settings=SimpleNamespace(evaluation=SimpleNamespace(llm_judge_model="judge-default")),
        scorer_registry=registry,
    )

    with pytest.raises(JudgeUnavailableError):
        await service.judge_adhoc(
            AdHocJudgeRequest(
                output="answer",
                rubric=RubricCreate(
                    name="inline",
                    description="desc",
                    criteria=[RubricCriterion(name="accuracy", description="desc", scale=5)],
                ),
            ),
            uuid4(),
        )


@pytest.mark.asyncio
async def test_eval_runner_judge_adhoc_rejects_archived_rubrics() -> None:
    archived = build_rubric(status=RubricStatus.archived)
    registry = ScorerRegistry()
    registry.register("llm_judge", JudgeScorerStub(ScoreResult(score=4.0)))
    service = EvalRunnerService(
        repository=SimpleNamespace(session=SessionStub()),
        settings=SimpleNamespace(evaluation=SimpleNamespace(llm_judge_model="judge-default")),
        scorer_registry=registry,
        rubric_service=RubricServiceStub(archived),
    )

    with pytest.raises(RubricArchivedError):
        await service.judge_adhoc(
            AdHocJudgeRequest(rubric_id=archived.id, output="answer", judge_model="judge-v1"),
            uuid4(),
        )


@pytest.mark.asyncio
async def test_eval_runner_inline_judge_success_and_normalization() -> None:
    registry = ScorerRegistry()
    registry.register(
        "llm_judge",
        JudgeScorerStub(
            ScoreResult(
                score=4.0,
                rationale="inline-ok",
                extra={
                    "criteria_scores": {"accuracy": 4.0},
                    "out_of_range_clamped": {"accuracy": {"original": 6.0, "clamped": 4.0}},
                    "rubric_version": 5,
                    "max_scale": 5.0,
                },
            )
        ),
    )
    service = EvalRunnerService(
        repository=SimpleNamespace(session=SessionStub()),
        settings=SimpleNamespace(evaluation=SimpleNamespace(llm_judge_model="judge-default")),
        scorer_registry=registry,
    )

    response = await service.judge_adhoc(
        AdHocJudgeRequest(
            output="answer",
            rubric=RubricCreate(
                name="inline",
                description="desc",
                criteria=[RubricCriterion(name="accuracy", description="desc", scale=5)],
            ),
        ),
        uuid4(),
    )

    assert response.rubric_id is None
    assert response.rubric_version == 5
    assert response.per_criterion_scores["accuracy"]["out_of_range"] is True
    assert (
        service._normalize_score(
            "llm_judge",
            ScoreResult(score=4.0, extra={"max_scale": 5.0}),
        )
        == 0.8
    )
    assert service._normalize_score("trajectory", ScoreResult(score=1.5)) == 1.0


@pytest.mark.asyncio
async def test_eval_runner_delete_run_cascades_tagging_state() -> None:
    run = build_run()
    repository = EvalRunRepositoryStub(run)
    tag_service = TagCascadeStub()
    service = EvalRunnerService(
        repository=repository,
        settings=SimpleNamespace(),
        scorer_registry=ScorerRegistry(),
        tag_service=tag_service,
    )

    await service.delete_run(run.id, run.workspace_id)

    assert repository.deleted == [run]
    assert tag_service.calls == [("evaluation_run", run.id)]
    assert repository.session.commits == 1
