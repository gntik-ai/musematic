from __future__ import annotations

import sys
import types

if "jsonschema" not in sys.modules:
    jsonschema_stub = types.ModuleType("jsonschema")

    class _ValidationError(Exception):
        pass

    def _validate(*, instance: object, schema: dict[str, object]) -> None:
        del instance, schema
        return None

    jsonschema_stub.ValidationError = _ValidationError
    jsonschema_stub.validate = _validate
    sys.modules["jsonschema"] = jsonschema_stub

from platform.common.exceptions import AuthorizationError, NotFoundError, ValidationError
from platform.evaluation.ab_experiment_service import AbExperimentService
from platform.evaluation.ate_service import ATEService
from platform.evaluation.dependencies import (
    build_ab_experiment_service,
    build_ate_service,
    build_eval_runner_service,
    build_eval_suite_service,
    build_human_grading_service,
    build_robustness_service,
    build_scorer_registry,
    get_ab_experiment_service,
    get_ate_service,
    get_eval_runner_service,
    get_eval_suite_service,
    get_human_grading_service,
    get_robustness_service,
)
from platform.evaluation.human_grading_service import HumanGradingService
from platform.evaluation.models import ATERunStatus, RunStatus, VerdictStatus
from platform.evaluation.robustness_service import RobustnessTestService
from platform.evaluation.router import (
    _actor_id,
    _build_eval_runner,
    _build_execution_query,
    _require_roles,
    _run_ate_background,
    _run_eval_background,
    _run_experiment_background,
    _run_robustness_background,
    _workspace_id,
    archive_eval_set,
    create_ate_config,
    create_benchmark_case,
    create_eval_set,
    create_experiment,
    create_robustness_run,
    delete_benchmark_case,
    get_ate_config,
    get_ate_run,
    get_benchmark_case,
    get_eval_set,
    get_experiment,
    get_review_progress,
    get_robustness_run,
    get_verdict,
    get_verdict_grade,
    list_ate_configs,
    list_ate_results,
    list_benchmark_cases,
    list_eval_sets,
    list_run_verdicts,
    list_runs,
    run_ate,
    run_eval_set,
    submit_verdict_grade,
    update_ate_config,
    update_eval_set,
    update_grade,
)
from platform.evaluation.router import (
    get_run as get_run_route,
)
from platform.evaluation.schemas import (
    AbExperimentCreate,
    AbExperimentResponse,
    ATEConfigCreate,
    ATEConfigListResponse,
    ATEConfigResponse,
    ATEConfigUpdate,
    ATERunListResponse,
    ATERunRequest,
    ATERunResponse,
    BenchmarkCaseCreate,
    BenchmarkCaseListResponse,
    BenchmarkCaseResponse,
    EvalSetCreate,
    EvalSetListResponse,
    EvalSetResponse,
    EvalSetUpdate,
    EvaluationRunCreate,
    EvaluationRunListResponse,
    EvaluationRunResponse,
    HumanAiGradeResponse,
    HumanGradeSubmit,
    HumanGradeUpdate,
    JudgeVerdictListResponse,
    JudgeVerdictResponse,
    ReviewProgressResponse,
    RobustnessRunCreate,
    RobustnessTestRunResponse,
)
from platform.evaluation.scorers.base import ScoreResult
from platform.evaluation.scorers.registry import ScorerRegistry
from platform.evaluation.service import EvalRunnerService, EvalSuiteService
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import BackgroundTasks, FastAPI

from tests.evaluation_testing_support import (
    ObjectStorageStub,
    RuntimeControllerStub,
    SessionStub,
    SimulationControllerStub,
    build_ate_config,
    build_ate_run,
    build_benchmark_case,
    build_eval_set,
    build_experiment,
    build_human_grade,
    build_robustness_run,
    build_run,
    build_verdict,
    make_request,
    make_settings,
)


def _apply_updates(model: object, **fields: object) -> object:
    for key, value in fields.items():
        setattr(model, key, value)
    return model


def _persist_verdict(verdict: object) -> object:
    if getattr(verdict, "id", None) is None:
        verdict.id = uuid4()
    return verdict


def _admin_user(workspace_id: UUID) -> dict[str, object]:
    return {
        "sub": str(uuid4()),
        "workspace_id": str(workspace_id),
        "roles": [{"role": "workspace_admin"}],
    }


@pytest.mark.asyncio
async def test_eval_suite_service_crud_and_lookup_methods() -> None:
    workspace_id = uuid4()
    eval_set = build_eval_set(workspace_id=workspace_id)
    case = build_benchmark_case(eval_set_id=eval_set.id)
    run = build_run(workspace_id=workspace_id, eval_set_id=eval_set.id)
    repo = SimpleNamespace(
        session=SessionStub(),
        create_eval_set=AsyncMock(return_value=eval_set),
        list_eval_sets=AsyncMock(return_value=([eval_set], 1)),
        get_eval_set=AsyncMock(side_effect=[eval_set, eval_set, eval_set, eval_set, eval_set]),
        update_eval_set=AsyncMock(
            side_effect=lambda model, **fields: _apply_updates(model, **fields)
        ),
        soft_delete_eval_set=AsyncMock(return_value=eval_set),
        get_next_case_position=AsyncMock(return_value=4),
        create_benchmark_case=AsyncMock(return_value=case),
        list_benchmark_cases=AsyncMock(return_value=([case], 1)),
        get_benchmark_case=AsyncMock(side_effect=[case, case]),
        delete_benchmark_case=AsyncMock(return_value=None),
        get_run=AsyncMock(return_value=run),
        get_latest_completed_run_score=AsyncMock(return_value=0.91),
    )
    service = EvalSuiteService(repository=repo, settings=make_settings())
    original_name = eval_set.name

    created = await service.create_eval_set(
        EvalSetCreate(
            workspace_id=workspace_id,
            name="suite",
            description="desc",
            scorer_config={"exact_match": {"enabled": True}},
            pass_threshold=0.8,
        ),
        uuid4(),
    )
    listed = await service.list_eval_sets(
        workspace_id=workspace_id, status=None, page=1, page_size=10
    )
    fetched = await service.get_eval_set(eval_set.id, workspace_id)
    updated = await service.update_eval_set(eval_set.id, EvalSetUpdate(name="updated"))
    await service.archive_eval_set(eval_set.id)
    created_case = await service.create_benchmark_case(
        eval_set.id,
        BenchmarkCaseCreate(
            input_data={"prompt": "hi"},
            expected_output="hello",
            scoring_criteria={},
            metadata_tags={},
            category="general",
        ),
    )
    listed_cases = await service.list_benchmark_cases(
        eval_set_id=eval_set.id,
        category=None,
        page=1,
        page_size=10,
    )
    fetched_case = await service.get_benchmark_case(eval_set.id, case.id)
    await service.delete_benchmark_case(eval_set.id, case.id)
    summary = await service.get_run_summary(run.id)
    latest = await service.get_latest_agent_score(run.agent_fqn, run.eval_set_id, workspace_id)

    assert created.name == original_name
    assert listed.total == 1
    assert fetched.id == eval_set.id
    assert updated.name == "updated"
    assert created_case.id == case.id
    assert listed_cases.total == 1
    assert fetched_case.id == case.id
    assert summary.run_id == run.id
    assert latest == 0.91
    assert repo.session.commits >= 4


@pytest.mark.asyncio
async def test_eval_runner_service_success_failure_and_scoring_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    eval_set = build_eval_set(
        workspace_id=workspace_id,
        scorer_config={
            "exact_match": {"enabled": True},
            "llm_judge": {"enabled": True, "threshold": 4.0},
        },
    )
    run = build_run(workspace_id=workspace_id, eval_set_id=eval_set.id)
    case = build_benchmark_case(eval_set_id=eval_set.id, input_data={"prompt": "hello"})
    registry = ScorerRegistry()

    class _ExactScorer:
        async def score(self, actual: str, expected: str, config: dict[str, object]) -> ScoreResult:
            del config
            return ScoreResult(score=1.0 if actual == expected else 0.0, passed=actual == expected)

    class _JudgeScorer:
        async def score(self, actual: str, expected: str, config: dict[str, object]) -> ScoreResult:
            del actual, expected, config
            return ScoreResult(score=4.0, passed=True, extra={"max_scale": 5.0})

    class _BrokenScorer:
        async def score(self, actual: str, expected: str, config: dict[str, object]) -> ScoreResult:
            del actual, expected, config
            raise RuntimeError("boom")

    registry.register("exact_match", _ExactScorer())
    registry.register("llm_judge", _JudgeScorer())
    registry.register("broken", _BrokenScorer())
    repo = SimpleNamespace(
        session=SessionStub(),
        get_eval_set=AsyncMock(return_value=eval_set),
        create_run=AsyncMock(return_value=run),
        get_run=AsyncMock(return_value=run),
        list_all_benchmark_cases=AsyncMock(return_value=[case]),
        update_run=AsyncMock(side_effect=lambda model, **fields: _apply_updates(model, **fields)),
        create_verdict=AsyncMock(side_effect=_persist_verdict),
        list_runs=AsyncMock(return_value=([run], 1)),
        list_run_verdicts=AsyncMock(return_value=([build_verdict(run_id=run.id)], 1)),
        get_verdict=AsyncMock(return_value=build_verdict(run_id=run.id)),
    )
    drift_service = SimpleNamespace(record_eval_metric=AsyncMock())
    service = EvalRunnerService(
        repository=repo,
        settings=make_settings(),
        scorer_registry=registry,
        runtime_controller=RuntimeControllerStub(result={"output": case.expected_output}),
        drift_service=drift_service,
    )

    started = await service.start_run(
        eval_set.id,
        EvaluationRunCreate(agent_fqn=run.agent_fqn, agent_id=run.agent_id),
        workspace_id,
    )
    finished = await service.run_existing(run.id)
    listed = await service.list_runs(
        workspace_id=workspace_id,
        eval_set_id=eval_set.id,
        agent_fqn=run.agent_fqn,
        status=None,
        page=1,
        page_size=10,
    )
    got_run = await service.get_run(run.id)
    verdicts = await service.list_run_verdicts(
        run_id=run.id,
        passed=None,
        status=None,
        page=1,
        page_size=10,
    )
    got_verdict = await service.get_verdict(repo.get_verdict.return_value.id)
    score_outputs = await service.score_outputs(
        expected_output="expected",
        actual_output="expected",
        scorer_config={
            "exact_match": {"enabled": True},
            "llm_judge": {"enabled": True, "threshold": 4.0},
            "broken": {"enabled": True},
        },
        input_data={"execution_id": str(uuid4())},
        pass_threshold=0.7,
    )

    assert started.id == run.id
    assert finished.status is RunStatus.completed
    assert listed.total == 1
    assert got_run.id == run.id
    assert verdicts.total == 1
    assert got_verdict.id is not None
    assert score_outputs[1] is not None
    assert score_outputs[2] is True
    assert "broken" in score_outputs[0]
    assert repo.session.commits >= 2
    drift_service.record_eval_metric.assert_awaited_once()
    assert service._extract_output({"response": "ok"}) == "ok"
    assert service._extract_output(SimpleNamespace(result="ok")) == "ok"
    assert service._extract_output(1) is None
    assert service._merge_scorer_config({"a": {"enabled": True}}, {"a": {"threshold": 0.5}}) == {
        "a": {"enabled": True, "threshold": 0.5}
    }
    assert service._flatten_score_result(ScoreResult(score=1.0, extra={"k": "v"})) == {
        "score": 1.0,
        "k": "v",
    }
    assert (
        service._normalize_score("llm_judge", ScoreResult(score=4.0, extra={"max_scale": 5.0}))
        == 0.8
    )

    failing_repo = SimpleNamespace(
        session=SessionStub(),
        get_run=AsyncMock(return_value=run),
        get_eval_set=AsyncMock(return_value=eval_set),
        list_all_benchmark_cases=AsyncMock(return_value=[case]),
        update_run=AsyncMock(side_effect=lambda model, **fields: _apply_updates(model, **fields)),
    )
    failing_service = EvalRunnerService(
        repository=failing_repo,
        settings=make_settings(),
        scorer_registry=registry,
    )
    monkeypatch.setattr(
        failing_service,
        "_score_case",
        AsyncMock(side_effect=RuntimeError("scoring failed")),
    )
    with pytest.raises(RuntimeError, match="scoring failed"):
        await failing_service.run_existing(run.id)
    assert run.status is RunStatus.failed


@pytest.mark.asyncio
async def test_ab_experiment_human_grading_ate_and_robustness_services() -> None:
    workspace_id = uuid4()
    run_a = build_run(workspace_id=workspace_id, status=RunStatus.completed)
    run_b = build_run(
        workspace_id=workspace_id, status=RunStatus.completed, eval_set_id=run_a.eval_set_id
    )
    experiment = build_experiment(workspace_id=workspace_id, run_a_id=run_a.id, run_b_id=run_b.id)
    verdict = build_verdict(run_id=run_a.id)
    verdict.run = run_a
    grade = build_human_grade(verdict_id=verdict.id)
    ate_config = build_ate_config(workspace_id=workspace_id)
    ate_run = build_ate_run(workspace_id=workspace_id, ate_config_id=ate_config.id)
    robustness_run = build_robustness_run(
        workspace_id=workspace_id,
        eval_set_id=run_a.eval_set_id,
        trial_count=2,
    )
    repo = SimpleNamespace(
        session=SessionStub(),
        get_run=AsyncMock(side_effect=[run_a, run_b]),
        create_ab_experiment=AsyncMock(return_value=experiment),
        get_ab_experiment=AsyncMock(return_value=experiment),
        get_run_score_array=AsyncMock(side_effect=[[0.9, 0.95], [0.2, 0.25]]),
        update_ab_experiment=AsyncMock(
            side_effect=lambda model, **fields: _apply_updates(model, **fields)
        ),
        get_verdict=AsyncMock(return_value=verdict),
        get_human_grade_by_verdict=AsyncMock(side_effect=[None, grade]),
        create_human_grade=AsyncMock(return_value=grade),
        get_human_grade=AsyncMock(return_value=grade),
        update_human_grade=AsyncMock(
            side_effect=lambda model, **fields: _apply_updates(model, **fields)
        ),
        get_review_progress=AsyncMock(
            return_value={"total_verdicts": 2, "pending_review": 1, "reviewed": 1, "overridden": 0}
        ),
        create_ate_config=AsyncMock(return_value=ate_config),
        list_ate_configs=AsyncMock(return_value=([ate_config], 1)),
        get_ate_config=AsyncMock(side_effect=[ate_config, ate_config, ate_config, ate_config]),
        update_ate_config=AsyncMock(
            side_effect=lambda model, **fields: _apply_updates(model, **fields)
        ),
        create_ate_run=AsyncMock(return_value=ate_run),
        get_ate_run=AsyncMock(side_effect=[ate_run, ate_run, ate_run]),
        update_ate_run=AsyncMock(
            side_effect=lambda model, **fields: _apply_updates(model, **fields)
        ),
        list_ate_runs=AsyncMock(return_value=([ate_run], 1)),
        create_robustness_run=AsyncMock(return_value=robustness_run),
        get_robustness_run=AsyncMock(side_effect=[robustness_run, robustness_run]),
        update_robustness_run=AsyncMock(
            side_effect=lambda model, **fields: _apply_updates(model, **fields)
        ),
    )

    ab_service = AbExperimentService(repository=repo)
    started_experiment = await ab_service.start_experiment(
        AbExperimentCreate(
            workspace_id=workspace_id,
            name="AB",
            run_a_id=run_a.id,
            run_b_id=run_b.id,
        )
    )
    completed_experiment = await ab_service.run_experiment(experiment.id)
    fetched_experiment = await ab_service.get_experiment(experiment.id)

    grading_service = HumanGradingService(repository=repo)
    submitted = await grading_service.submit_grade(
        verdict.id,
        uuid4(),
        HumanGradeSubmit(decision="confirmed"),
    )
    updated = await grading_service.update_grade(grade.id, HumanGradeUpdate(feedback="updated"))
    fetched_grade = await grading_service.get_grade_for_verdict(verdict.id)
    progress = await grading_service.get_review_progress(run_a.id)

    eval_runner = SimpleNamespace(
        score_outputs=AsyncMock(
            return_value=({"exact_match": {"score": 1.0}}, 1.0, True, VerdictStatus.scored, None)
        ),
        run_eval_set=AsyncMock(
            return_value=EvaluationRunResponse.model_validate(build_run(aggregate_score=0.9))
        ),
    )
    object_storage = ObjectStorageStub()
    ate_service = ATEService(
        repository=repo,
        settings=make_settings(),
        producer=None,
        object_storage=object_storage,
        simulation_controller=SimulationControllerStub(),
        eval_runner_service=eval_runner,
    )
    created_config = await ate_service.create_config(
        ATEConfigCreate(
            workspace_id=workspace_id,
            name="ATE",
            description="desc",
            scenarios=ate_config.scenarios,
            scorer_config=ate_config.scorer_config,
            performance_thresholds={},
            safety_checks=[],
        ),
        uuid4(),
    )
    listed_configs = await ate_service.list_configs(workspace_id=workspace_id, page=1, page_size=10)
    fetched_config = await ate_service.get_config(ate_config.id, workspace_id)
    updated_config = await ate_service.update_config(ate_config.id, ATEConfigUpdate(name="renamed"))
    started_run = await ate_service.start_run(
        ate_config_id=ate_config.id,
        workspace_id=workspace_id,
        agent_fqn="agents.demo",
        payload=ATERunRequest(agent_id=None),
    )
    executed = await ate_service.execute_run(ate_run.id)
    listed_runs = await ate_service.list_results(ate_config_id=ate_config.id, page=1, page_size=10)
    fetched_run = await ate_service.get_run(ate_run.id, workspace_id)
    precheck_errors = ate_service.pre_check(build_ate_config(scenarios=[]))

    robustness_service = RobustnessTestService(
        repository=repo,
        eval_runner_service=eval_runner,
    )
    created_robustness = await robustness_service.start_run(
        RobustnessRunCreate(
            workspace_id=workspace_id,
            eval_set_id=run_a.eval_set_id,
            benchmark_case_id=None,
            agent_fqn="agents.demo",
            trial_count=2,
            variance_threshold=0.2,
        )
    )
    executed_robustness = await robustness_service.execute_run(robustness_run.id)
    fetched_robustness = await robustness_service.get_run(robustness_run.id)

    assert started_experiment.id == experiment.id
    assert completed_experiment.status.name == "completed"
    assert fetched_experiment.id == experiment.id
    assert submitted.id == grade.id
    assert updated.feedback == "updated"
    assert fetched_grade.id == grade.id
    assert progress.reviewed == 1
    assert created_config.id == ate_config.id
    assert listed_configs.total == 1
    assert fetched_config.id == ate_config.id
    assert updated_config.name == "renamed"
    assert started_run.id == ate_run.id
    assert executed.status is ATERunStatus.completed
    assert listed_runs.total == 1
    assert fetched_run.id == ate_run.id
    assert precheck_errors[0]["code"] == "ATE_SCENARIOS_REQUIRED"
    assert created_robustness.id == robustness_run.id
    assert executed_robustness.completed_trials == 2
    assert fetched_robustness.id == robustness_run.id
    assert ("evaluation-ate-evidence", f"{ate_run.id}/evidence.json") in object_storage.uploads
    assert AbExperimentService._compare([1.0], [1.0]) == (None, None, None, "inconclusive")
    assert ATEService._percentile([], 0.5) is None
    assert RobustnessTestService._distribution([0.4])["p95"] == 0.4


@pytest.mark.asyncio
async def test_evaluation_dependency_builders_and_getters(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SessionStub()
    request = make_request(
        clients={
            "kafka": None,
            "qdrant": SimpleNamespace(),
            "redis": SimpleNamespace(),
            "object_storage": ObjectStorageStub(),
            "runtime_controller": None,
            "reasoning_engine": None,
            "simulation_controller": None,
        }
    )
    app = FastAPI()
    app.state.settings = make_settings()
    app.state.clients = request.app.state.clients
    request.app = app
    execution_service = SimpleNamespace(name="execution")
    monkeypatch.setattr(
        "platform.evaluation.dependencies.build_execution_service",
        lambda **_kwargs: execution_service,
    )

    registry = build_scorer_registry(
        settings=make_settings(),
        qdrant=SimpleNamespace(),
        execution_service=execution_service,
        reasoning_engine=SimpleNamespace(),
    )
    suite_service = build_eval_suite_service(
        session=session, settings=make_settings(), producer=None
    )
    runner_service = build_eval_runner_service(
        session=session,
        settings=make_settings(),
        producer=None,
        qdrant=SimpleNamespace(),
        runtime_controller=None,
        reasoning_engine=None,
        execution_service=execution_service,
    )
    ate_service = build_ate_service(
        session=session,
        settings=make_settings(),
        producer=None,
        object_storage=ObjectStorageStub(),
        simulation_controller=None,
        eval_runner_service=runner_service,
    )
    ab_service = build_ab_experiment_service(session=session, producer=None)
    robustness_service = build_robustness_service(
        session=session,
        eval_runner_service=runner_service,
        producer=None,
    )
    grading_service = build_human_grading_service(session=session, producer=None)

    assert registry.has("trajectory") is True
    assert isinstance(suite_service, EvalSuiteService)
    assert isinstance(runner_service, EvalRunnerService)
    assert isinstance(ate_service, ATEService)
    assert isinstance(ab_service, AbExperimentService)
    assert isinstance(robustness_service, RobustnessTestService)
    assert isinstance(grading_service, HumanGradingService)
    assert isinstance(await get_eval_suite_service(request, session), EvalSuiteService)
    assert isinstance(await get_eval_runner_service(request, session), EvalRunnerService)
    assert isinstance(await get_ate_service(request, session, runner_service), ATEService)
    assert isinstance(await get_ab_experiment_service(request, session), AbExperimentService)
    assert isinstance(
        await get_robustness_service(request, session, runner_service), RobustnessTestService
    )
    assert isinstance(await get_human_grading_service(request, session), HumanGradingService)


@pytest.mark.asyncio
async def test_evaluation_router_helpers_and_background_jobs_cover_remaining_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    request = make_request()
    current_user = {"sub": str(uuid4()), "workspace_id": str(workspace_id), "roles": []}

    assert _workspace_id(request, current_user) == workspace_id
    assert _workspace_id(request, {"sub": str(uuid4())}, workspace_id) == workspace_id
    with pytest.raises(ValidationError, match="Workspace context is required"):
        _workspace_id(make_request(), {"sub": str(uuid4())})
    with pytest.raises(ValidationError, match="does not match"):
        _workspace_id(make_request(), current_user, uuid4())

    class _SessionContext:
        def __init__(self, session: SessionStub) -> None:
            self.session = session

        async def __aenter__(self) -> SessionStub:
            return self.session

        async def __aexit__(self, *_args: object) -> None:
            return None

    app = FastAPI()
    app.state.settings = make_settings()
    app.state.clients = {
        "kafka": None,
        "redis": SimpleNamespace(),
        "object_storage": ObjectStorageStub(),
        "runtime_controller": RuntimeControllerStub(),
        "reasoning_engine": SimpleNamespace(),
        "simulation_controller": SimulationControllerStub(),
        "qdrant": SimpleNamespace(),
    }
    app.state.context_engineering_service = "ce"
    session = SessionStub()
    monkeypatch.setattr(
        "platform.evaluation.router.build_execution_service",
        lambda **kwargs: kwargs | {"kind": "execution"},
    )
    monkeypatch.setattr(
        "platform.evaluation.router.build_eval_runner_service",
        lambda **kwargs: kwargs | {"kind": "runner"},
    )
    execution_service = _build_execution_query(app, session)
    eval_runner = _build_eval_runner(app, session)

    assert execution_service["kind"] == "execution"
    assert execution_service["context_engineering_service"] == "ce"
    assert eval_runner["kind"] == "runner"
    assert eval_runner["execution_service"]["kind"] == "execution"

    success_session = SessionStub()
    monkeypatch.setattr(
        "platform.evaluation.router.database.AsyncSessionLocal",
        lambda: _SessionContext(success_session),
    )
    monkeypatch.setattr(
        "platform.evaluation.router._build_eval_runner",
        lambda _app, _session: SimpleNamespace(run_existing=AsyncMock()),
    )
    await _run_eval_background(app, uuid4())
    assert success_session.commits == 1

    failed_eval_session = SessionStub()
    monkeypatch.setattr(
        "platform.evaluation.router.database.AsyncSessionLocal",
        lambda: _SessionContext(failed_eval_session),
    )
    monkeypatch.setattr(
        "platform.evaluation.router._build_eval_runner",
        lambda _app, _session: SimpleNamespace(
            run_existing=AsyncMock(side_effect=RuntimeError("eval background failed"))
        ),
    )
    with pytest.raises(RuntimeError, match="eval background failed"):
        await _run_eval_background(app, uuid4())
    assert failed_eval_session.rollbacks == 1

    experiment_session = SessionStub()
    monkeypatch.setattr(
        "platform.evaluation.router.database.AsyncSessionLocal",
        lambda: _SessionContext(experiment_session),
    )
    monkeypatch.setattr(
        "platform.evaluation.router.build_ab_experiment_service",
        lambda **_kwargs: SimpleNamespace(run_experiment=AsyncMock()),
    )
    await _run_experiment_background(app, uuid4())
    assert experiment_session.commits == 1

    failed_experiment_session = SessionStub()
    monkeypatch.setattr(
        "platform.evaluation.router.database.AsyncSessionLocal",
        lambda: _SessionContext(failed_experiment_session),
    )
    monkeypatch.setattr(
        "platform.evaluation.router.build_ab_experiment_service",
        lambda **_kwargs: SimpleNamespace(
            run_experiment=AsyncMock(side_effect=RuntimeError("experiment failed"))
        ),
    )
    with pytest.raises(RuntimeError, match="experiment failed"):
        await _run_experiment_background(app, uuid4())
    assert failed_experiment_session.rollbacks == 1

    ate_session = SessionStub()
    monkeypatch.setattr(
        "platform.evaluation.router.database.AsyncSessionLocal",
        lambda: _SessionContext(ate_session),
    )
    monkeypatch.setattr(
        "platform.evaluation.router.build_ate_service",
        lambda **_kwargs: SimpleNamespace(execute_run=AsyncMock()),
    )
    await _run_ate_background(app, uuid4())
    assert ate_session.commits == 1

    failed_ate_session = SessionStub()
    monkeypatch.setattr(
        "platform.evaluation.router.database.AsyncSessionLocal",
        lambda: _SessionContext(failed_ate_session),
    )
    monkeypatch.setattr(
        "platform.evaluation.router.build_ate_service",
        lambda **_kwargs: SimpleNamespace(
            execute_run=AsyncMock(side_effect=RuntimeError("ate failed"))
        ),
    )
    with pytest.raises(RuntimeError, match="ate failed"):
        await _run_ate_background(app, uuid4())
    assert failed_ate_session.rollbacks == 1

    robustness_session = SessionStub()
    monkeypatch.setattr(
        "platform.evaluation.router.database.AsyncSessionLocal",
        lambda: _SessionContext(robustness_session),
    )
    monkeypatch.setattr(
        "platform.evaluation.router.build_robustness_service",
        lambda **_kwargs: SimpleNamespace(execute_run=AsyncMock()),
    )
    monkeypatch.setattr(
        "platform.evaluation.router._build_eval_runner",
        lambda _app, _session: SimpleNamespace(name="runner"),
    )
    await _run_robustness_background(app, uuid4())
    assert robustness_session.commits == 1

    failed_robustness_session = SessionStub()
    monkeypatch.setattr(
        "platform.evaluation.router.database.AsyncSessionLocal",
        lambda: _SessionContext(failed_robustness_session),
    )
    monkeypatch.setattr(
        "platform.evaluation.router.build_robustness_service",
        lambda **_kwargs: SimpleNamespace(
            execute_run=AsyncMock(side_effect=RuntimeError("robustness failed"))
        ),
    )
    with pytest.raises(RuntimeError, match="robustness failed"):
        await _run_robustness_background(app, uuid4())
    assert failed_robustness_session.rollbacks == 1


@pytest.mark.asyncio
async def test_evaluation_router_wrappers_cover_endpoint_logic() -> None:
    workspace_id = uuid4()
    eval_set_response = EvalSetResponse.model_validate(build_eval_set(workspace_id=workspace_id))
    case_response = BenchmarkCaseResponse.model_validate(
        build_benchmark_case(eval_set_id=eval_set_response.id)
    )
    run_response = EvaluationRunResponse.model_validate(
        build_run(workspace_id=workspace_id, eval_set_id=eval_set_response.id)
    )
    verdict_response = JudgeVerdictResponse.model_validate(
        build_verdict(run_id=run_response.id, benchmark_case_id=case_response.id)
    )
    experiment_response = AbExperimentResponse.model_validate(
        build_experiment(
            workspace_id=workspace_id, run_a_id=run_response.id, run_b_id=run_response.id
        )
    )
    ate_config_response = ATEConfigResponse.model_validate(
        build_ate_config(workspace_id=workspace_id)
    )
    ate_run_response = ATERunResponse.model_validate(
        build_ate_run(workspace_id=workspace_id, ate_config_id=ate_config_response.id)
    )
    robustness_response = RobustnessTestRunResponse.model_validate(
        build_robustness_run(workspace_id=workspace_id, eval_set_id=eval_set_response.id)
    )
    grade_response = HumanAiGradeResponse.model_validate(
        build_human_grade(verdict_id=verdict_response.id)
    )
    request = make_request()
    request.headers["X-Workspace-ID"] = str(workspace_id)
    current_user = _admin_user(workspace_id)
    background = BackgroundTasks()
    eval_suite_service = SimpleNamespace(
        create_eval_set=AsyncMock(return_value=eval_set_response),
        list_eval_sets=AsyncMock(
            return_value=EvalSetListResponse(
                items=[eval_set_response], total=1, page=1, page_size=10
            )
        ),
        get_eval_set=AsyncMock(return_value=eval_set_response),
        update_eval_set=AsyncMock(return_value=eval_set_response),
        archive_eval_set=AsyncMock(return_value=None),
        create_benchmark_case=AsyncMock(return_value=case_response),
        list_benchmark_cases=AsyncMock(
            return_value=BenchmarkCaseListResponse(
                items=[case_response], total=1, page=1, page_size=10
            )
        ),
        get_benchmark_case=AsyncMock(return_value=case_response),
        delete_benchmark_case=AsyncMock(return_value=None),
    )
    eval_runner_service = SimpleNamespace(
        start_run=AsyncMock(return_value=run_response),
        list_runs=AsyncMock(
            return_value=EvaluationRunListResponse(
                items=[run_response], total=1, page=1, page_size=10
            )
        ),
        get_run=AsyncMock(return_value=run_response),
        list_run_verdicts=AsyncMock(
            return_value=JudgeVerdictListResponse(
                items=[verdict_response], total=1, page=1, page_size=10
            )
        ),
        get_verdict=AsyncMock(return_value=verdict_response),
    )
    ab_service = SimpleNamespace(
        start_experiment=AsyncMock(return_value=experiment_response),
        get_experiment=AsyncMock(return_value=experiment_response),
    )
    ate_service = SimpleNamespace(
        create_config=AsyncMock(return_value=ate_config_response),
        list_configs=AsyncMock(
            return_value=ATEConfigListResponse(
                items=[ate_config_response], total=1, page=1, page_size=10
            )
        ),
        get_config=AsyncMock(return_value=ate_config_response),
        update_config=AsyncMock(return_value=ate_config_response),
        start_run=AsyncMock(return_value=ate_run_response),
        list_results=AsyncMock(
            return_value=ATERunListResponse(items=[ate_run_response], total=1, page=1, page_size=10)
        ),
        get_run=AsyncMock(return_value=ate_run_response),
    )
    robustness_service = SimpleNamespace(
        start_run=AsyncMock(return_value=robustness_response),
        get_run=AsyncMock(return_value=robustness_response),
    )
    grading_service = SimpleNamespace(
        get_review_progress=AsyncMock(
            return_value=ReviewProgressResponse(
                total_verdicts=1, pending_review=0, reviewed=1, overridden=0
            )
        ),
        get_grade_for_verdict=AsyncMock(return_value=grade_response),
        submit_grade=AsyncMock(return_value=grade_response),
        update_grade=AsyncMock(return_value=grade_response),
    )

    assert _actor_id(current_user) == UUID(str(current_user["sub"]))
    assert _workspace_id(request, current_user, workspace_id) == workspace_id
    with pytest.raises(AuthorizationError):
        _require_roles({"roles": [{"role": "viewer"}]}, {"workspace_admin"})
    bad_request = make_request()
    bad_request.headers["X-Workspace-ID"] = str(uuid4())
    with pytest.raises(ValidationError):
        await create_eval_set(  # type: ignore[misc]
            EvalSetCreate(
                workspace_id=workspace_id,
                name="suite",
                description="desc",
                scorer_config={"exact_match": {"enabled": True}},
                pass_threshold=0.7,
            ),
            bad_request,
            {"sub": str(uuid4()), "roles": []},
            eval_suite_service,
        )

    assert (
        await create_eval_set(
            EvalSetCreate(
                workspace_id=workspace_id,
                name="suite",
                description="desc",
                scorer_config={"exact_match": {"enabled": True}},
                pass_threshold=0.7,
            ),
            request,
            current_user,
            eval_suite_service,
        )
    ).id == eval_set_response.id
    assert (await list_eval_sets(request, current_user, None, 1, 10, eval_suite_service)).total == 1
    assert (
        await get_eval_set(eval_set_response.id, request, current_user, eval_suite_service)
    ).id == eval_set_response.id
    assert (
        await update_eval_set(
            eval_set_response.id, EvalSetUpdate(name="x"), current_user, eval_suite_service
        )
    ).id == eval_set_response.id
    assert (
        await archive_eval_set(eval_set_response.id, current_user, eval_suite_service)
    ).status_code == 204
    assert (
        await create_benchmark_case(
            eval_set_response.id,
            BenchmarkCaseCreate(
                input_data={"prompt": "hi"},
                expected_output="hello",
                scoring_criteria={},
                metadata_tags={},
                category="general",
            ),
            eval_suite_service,
        )
    ).id == case_response.id
    assert (
        await list_benchmark_cases(eval_set_response.id, None, 1, 10, eval_suite_service)
    ).total == 1
    assert (
        await get_benchmark_case(eval_set_response.id, case_response.id, eval_suite_service)
    ).id == case_response.id
    assert (
        await delete_benchmark_case(
            eval_set_response.id, case_response.id, current_user, eval_suite_service
        )
    ).status_code == 204
    assert (
        await run_eval_set(
            eval_set_response.id,
            EvaluationRunCreate(agent_fqn=run_response.agent_fqn, agent_id=run_response.agent_id),
            background,
            request,
            current_user,
            eval_runner_service,
        )
    ).id == run_response.id
    assert len(background.tasks) == 1
    assert (
        await list_runs(request, current_user, None, None, None, 1, 10, eval_runner_service)
    ).total == 1
    assert (await get_run_route(run_response.id, eval_runner_service)).id == run_response.id
    assert (
        await list_run_verdicts(run_response.id, None, None, 1, 10, eval_runner_service)
    ).total == 1
    assert (await get_verdict(verdict_response.id, eval_runner_service)).id == verdict_response.id
    assert (
        await create_experiment(
            AbExperimentCreate(
                workspace_id=workspace_id,
                name="exp",
                run_a_id=run_response.id,
                run_b_id=run_response.id,
            ),
            BackgroundTasks(),
            request,
            current_user,
            ab_service,
        )
    ).id == experiment_response.id
    assert (await get_experiment(experiment_response.id, ab_service)).id == experiment_response.id
    assert (
        await create_ate_config(
            ATEConfigCreate(
                workspace_id=workspace_id,
                name="ATE",
                description="desc",
                scenarios=[{"id": "s1", "name": "S1", "input_data": {}, "expected_output": "ok"}],
                scorer_config={"exact_match": {"enabled": True}},
                performance_thresholds={},
                safety_checks=[],
            ),
            request,
            current_user,
            ate_service,
        )
    ).id == ate_config_response.id
    assert (await list_ate_configs(request, current_user, 1, 10, ate_service)).total == 1
    assert (
        await get_ate_config(ate_config_response.id, request, current_user, ate_service)
    ).id == ate_config_response.id
    assert (
        await update_ate_config(
            ate_config_response.id, ATEConfigUpdate(name="updated"), current_user, ate_service
        )
    ).id == ate_config_response.id
    assert (
        await run_ate(
            ate_config_response.id,
            "agents.demo",
            ATERunRequest(agent_id=None),
            BackgroundTasks(),
            request,
            current_user,
            ate_service,
        )
    ).id == ate_run_response.id
    assert (await list_ate_results(ate_config_response.id, 1, 10, ate_service)).total == 1
    assert (
        await get_ate_run(ate_run_response.id, request, current_user, ate_service)
    ).id == ate_run_response.id
    assert (
        await create_robustness_run(
            RobustnessRunCreate(
                workspace_id=workspace_id,
                eval_set_id=eval_set_response.id,
                benchmark_case_id=None,
                agent_fqn="agents.demo",
                trial_count=2,
                variance_threshold=0.2,
            ),
            BackgroundTasks(),
            request,
            current_user,
            robustness_service,
        )
    ).id == robustness_response.id
    assert (
        await get_robustness_run(robustness_response.id, robustness_service)
    ).id == robustness_response.id
    assert (await get_review_progress(run_response.id, grading_service)).reviewed == 1
    assert (await get_verdict_grade(verdict_response.id, grading_service)).id == grade_response.id
    assert (
        await submit_verdict_grade(
            verdict_response.id,
            HumanGradeSubmit(decision="confirmed"),
            {**current_user, "roles": [{"role": "evaluator"}]},
            grading_service,
        )
    ).id == grade_response.id
    assert (
        await update_grade(
            grade_response.id,
            HumanGradeUpdate(feedback="updated"),
            {**current_user, "roles": [{"role": "evaluator"}]},
            grading_service,
        )
    ).id == grade_response.id


@pytest.mark.asyncio
async def test_run_ate_skips_background_for_precheck_failed_runs() -> None:
    workspace_id = uuid4()
    request = make_request()
    request.headers["X-Workspace-ID"] = str(workspace_id)
    current_user = _admin_user(workspace_id)
    background = BackgroundTasks()
    precheck_run = ATERunResponse.model_validate(
        build_ate_run(
            workspace_id=workspace_id,
            status=ATERunStatus.pre_check_failed,
            pre_check_errors=[{"code": "ATE_SCENARIOS_REQUIRED"}],
        )
    )
    ate_service = SimpleNamespace(start_run=AsyncMock(return_value=precheck_run))

    response = await run_ate(
        uuid4(),
        "agents.demo",
        ATERunRequest(agent_id=None),
        background,
        request,
        current_user,
        ate_service,
    )

    assert response.status is ATERunStatus.pre_check_failed
    assert background.tasks == []


@pytest.mark.asyncio
async def test_eval_suite_and_runner_raise_not_found_when_entities_are_missing() -> None:
    workspace_id = uuid4()
    repo = SimpleNamespace(
        session=SessionStub(),
        get_eval_set=AsyncMock(return_value=None),
        get_run=AsyncMock(return_value=None),
        get_benchmark_case=AsyncMock(return_value=None),
        get_verdict=AsyncMock(return_value=None),
        get_human_grade_by_verdict=AsyncMock(return_value=None),
        get_human_grade=AsyncMock(return_value=None),
        get_ab_experiment=AsyncMock(return_value=None),
        get_ate_config=AsyncMock(return_value=None),
        get_ate_run=AsyncMock(return_value=None),
        get_robustness_run=AsyncMock(return_value=None),
    )
    suite_service = EvalSuiteService(repository=repo, settings=make_settings())
    runner_service = EvalRunnerService(
        repository=repo,
        settings=make_settings(),
        scorer_registry=ScorerRegistry(),
        runtime_controller=SimpleNamespace(
            run_agent=AsyncMock(return_value={"content": "from-controller"})
        ),
    )
    grading_service = HumanGradingService(repository=repo)
    ab_service = AbExperimentService(repository=repo)
    ate_service = ATEService(
        repository=repo,
        settings=make_settings(),
        producer=None,
        object_storage=ObjectStorageStub(),
        simulation_controller=None,
        eval_runner_service=SimpleNamespace(score_outputs=AsyncMock(), run_eval_set=AsyncMock()),
    )
    robustness_service = RobustnessTestService(
        repository=repo,
        eval_runner_service=SimpleNamespace(run_eval_set=AsyncMock()),
    )

    with pytest.raises(NotFoundError):
        await suite_service.get_eval_set(uuid4())
    with pytest.raises(NotFoundError):
        await suite_service.get_benchmark_case(uuid4(), uuid4())
    with pytest.raises(NotFoundError):
        await runner_service.get_run(uuid4())
    with pytest.raises(NotFoundError):
        await runner_service.get_verdict(uuid4())
    with pytest.raises(NotFoundError):
        await grading_service.submit_grade(uuid4(), uuid4(), HumanGradeSubmit(decision="confirmed"))
    with pytest.raises(NotFoundError):
        await grading_service.get_grade_for_verdict(uuid4())
    with pytest.raises(NotFoundError):
        await grading_service.update_grade(uuid4(), HumanGradeUpdate(feedback="updated"))
    with pytest.raises(NotFoundError):
        await ab_service.get_experiment(uuid4())
    with pytest.raises(NotFoundError):
        await ate_service.start_run(
            ate_config_id=uuid4(),
            workspace_id=workspace_id,
            agent_fqn="agents.demo",
            payload=ATERunRequest(agent_id=None),
        )
    with pytest.raises(NotFoundError):
        await ate_service.execute_run(uuid4())
    with pytest.raises(NotFoundError):
        await ate_service.get_run(uuid4(), workspace_id)
    with pytest.raises(NotFoundError):
        await robustness_service.execute_run(uuid4())
    with pytest.raises(NotFoundError):
        await robustness_service.get_run(uuid4())

    output = await runner_service._invoke_agent(
        build_run(workspace_id=workspace_id),
        build_benchmark_case(input_data={"prompt": "x"}, expected_output="fallback"),
    )
    assert output == "from-controller"

    fallback_output = await EvalRunnerService(
        repository=repo,
        settings=make_settings(),
        scorer_registry=ScorerRegistry(),
        runtime_controller=SimpleNamespace(run_agent=AsyncMock(return_value={"ignored": True})),
    )._invoke_agent(
        build_run(workspace_id=workspace_id),
        build_benchmark_case(input_data={"prompt": "x"}, expected_output="fallback"),
    )
    assert fallback_output == "fallback"

    broken_registry = ScorerRegistry()

    class _BrokenScorer:
        async def score(self, *_args: object, **_kwargs: object) -> ScoreResult:
            raise RuntimeError("only broken")

    broken_registry.register("broken", _BrokenScorer())
    broken_result = await EvalRunnerService(
        repository=repo,
        settings=make_settings(),
        scorer_registry=broken_registry,
    ).score_outputs(
        expected_output="expected",
        actual_output="actual",
        scorer_config={"broken": {"enabled": True}},
    )

    assert broken_result[2] is None
    assert broken_result[3] is VerdictStatus.error
    assert "broken_error" in (broken_result[4] or "")
