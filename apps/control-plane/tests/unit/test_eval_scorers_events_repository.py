from __future__ import annotations

import sys
import types

if "jsonschema" not in sys.modules:
    jsonschema_stub = types.ModuleType("jsonschema")

    class _ValidationError(Exception):
        def __init__(
            self,
            message: str,
            *,
            validator: str = "type",
            path: list[object] | None = None,
        ) -> None:
            super().__init__(message)
            self.message = message
            self.validator = validator
            self.path = path or []

    def _validate(*, instance: object, schema: dict[str, object]) -> None:
        properties = schema.get("properties", {})
        if (
            isinstance(instance, dict)
            and isinstance(properties, dict)
            and isinstance(properties.get("value"), dict)
            and properties["value"].get("type") == "number"
            and not isinstance(instance.get("value"), (int, float))
        ):
            raise _ValidationError("'x' is not of type 'number'")

    jsonschema_stub.ValidationError = _ValidationError
    jsonschema_stub.validate = _validate
    sys.modules["jsonschema"] = jsonschema_stub

from platform.common.events.envelope import CorrelationContext
from platform.common.events.registry import event_registry
from platform.evaluation.events import (
    EvaluationEventType,
    HumanGradeSubmittedPayload,
    RunStartedPayload,
    publish_evaluation_event,
    register_evaluation_event_types,
)
from platform.evaluation.repository import EvaluationRepository
from platform.evaluation.schemas import (
    AbExperimentResponse,
    ATEConfigResponse,
    ATERunResponse,
    BenchmarkCaseResponse,
    EvalSetResponse,
    EvaluationRunResponse,
    HumanAiGradeResponse,
    JudgeVerdictResponse,
    RobustnessTestRunResponse,
)
from platform.evaluation.scorers.base import ScoreResult
from platform.evaluation.scorers.exact_match import ExactMatchScorer
from platform.evaluation.scorers.json_schema import JsonSchemaScorer
from platform.evaluation.scorers.llm_judge import RUBRIC_TEMPLATES, LLMJudgeScorer
from platform.evaluation.scorers.regex import RegexScorer
from platform.evaluation.scorers.registry import ScorerRegistry
from platform.evaluation.scorers.semantic import SemanticSimilarityScorer
from platform.evaluation.scorers.trajectory import TrajectoryScorer
from platform.evaluation.service_interfaces import EvalSuiteServiceInterface
from platform.testing.events import (
    SuiteGeneratedPayload,
    TestingDriftDetectedPayload,
    TestingEventType,
    publish_testing_event,
    register_testing_event_types,
)
from platform.testing.models import AdversarialCategory, SuiteType
from platform.testing.repository import TestingRepository
from platform.testing.schemas import (
    AdversarialCaseResponse,
    CoordinationTestResultResponse,
    DriftAlertResponse,
    GeneratedTestSuiteResponse,
)
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from tests.context_engineering_support import EventProducerStub
from tests.evaluation_testing_support import (
    ClickHouseStub,
    ExecutionQueryStub,
    ReasoningEngineStub,
    ResultStub,
    SessionStub,
    build_adversarial_case,
    build_ate_config,
    build_ate_run,
    build_benchmark_case,
    build_coordination_result,
    build_drift_alert,
    build_eval_set,
    build_experiment,
    build_human_grade,
    build_robustness_run,
    build_run,
    build_suite,
    build_verdict,
    make_settings,
)


@pytest.mark.asyncio
async def test_basic_scorers_cover_success_and_error_paths() -> None:
    exact_match = ExactMatchScorer()
    regex = RegexScorer()
    json_schema = JsonSchemaScorer()

    matched = await exact_match.score("same", "same", {})
    mismatched = await exact_match.score("left", "right", {"threshold": 0.5})
    regex_missing = await regex.score("value", "", {})
    regex_invalid = await regex.score("value", "", {"pattern": "("})
    regex_matched = await regex.score("hello 42", "", {"pattern": r"\d+"})
    regex_unmatched = await regex.score("hello", "", {"pattern": r"\d+", "threshold": 0.5})
    schema_missing = await json_schema.score("{}", "", {})
    schema_invalid_json = await json_schema.score("{", "", {"schema": {"type": "object"}})
    schema_invalid = await json_schema.score(
        '{"value":"x"}',
        "",
        {"schema": {"type": "object", "properties": {"value": {"type": "number"}}}},
    )
    schema_valid = await json_schema.score(
        '{"value":1}',
        "",
        {"schema": {"type": "object", "properties": {"value": {"type": "number"}}}},
    )

    assert matched.score == 1.0
    assert matched.passed is True
    assert mismatched.score == 0.0
    assert mismatched.passed is False
    assert regex_missing.error == "missing_regex_pattern"
    assert regex_invalid.error == "invalid_regex"
    assert regex_matched.passed is True
    assert regex_unmatched.passed is False
    assert schema_missing.error == "missing_json_schema"
    assert schema_invalid_json.error == "invalid_json"
    assert schema_invalid.passed is False
    assert schema_valid.score == 1.0


@pytest.mark.asyncio
async def test_llm_judge_scorer_parses_provider_and_heuristic_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scorer = LLMJudgeScorer(settings=make_settings(), api_url="http://judge.example")

    async def _judge_with_retries(**_kwargs: object) -> dict[str, object]:
        return {
            "score": 4.0,
            "criteria_scores": {"factual_accuracy": 4.0, "completeness": 4.0},
            "rationale": "good",
        }

    monkeypatch.setattr(scorer, "_judge_with_retries", _judge_with_retries)
    result = await scorer.score(
        "actual",
        "expected",
        {"judge_model": "demo", "rubric": {"template": "correctness"}, "calibration_runs": 2},
    )
    parsed = scorer._parse_provider_result(
        {
            "output": (
                '{"score": 5, "criteria_scores": {"clarity": 5, "usefulness": 4},'
                ' "rationale": "parsed"}'
            )
        },
        RUBRIC_TEMPLATES["helpfulness"]["criteria"],
    )
    heuristic = scorer._heuristic_result(
        actual="hello",
        expected="hello there",
        criteria=RUBRIC_TEMPLATES["style"]["criteria"],
    )

    assert result.score == 4.0
    assert result.passed is True
    assert result.extra["calibration_distribution"]["low_confidence"] is False
    assert parsed["score"] == 5.0
    assert parsed["criteria_scores"]["clarity"] == 5.0
    assert heuristic["score"] is not None
    assert (
        scorer._resolve_criteria(
            scorer._validate_config(
                {
                    "judge_model": "demo",
                    "rubric": {"custom_criteria": [{"name": "c1", "description": "d", "scale": 3}]},
                    "calibration_runs": 1,
                }
            ).rubric
        )[0]["name"]
        == "c1"
    )


@pytest.mark.asyncio
async def test_semantic_and_trajectory_scorers_cover_success_and_fallback_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic = SemanticSimilarityScorer(settings=make_settings(), qdrant=SimpleNamespace())

    async def _ensure_collection() -> None:
        return None

    async def _embed_text(text: str) -> list[float]:
        del text
        return [1.0, 0.0]

    async def _store_embeddings(_left: list[float], _right: list[float]) -> None:
        return None

    monkeypatch.setattr(semantic, "ensure_collection", _ensure_collection)
    monkeypatch.setattr(semantic, "_embed_text", _embed_text)
    monkeypatch.setattr(semantic, "_store_embeddings", _store_embeddings)
    semantic_result = await semantic.score("actual", "expected", {"threshold": 0.5})

    async def _boom() -> None:
        raise RuntimeError("unavailable")

    monkeypatch.setattr(semantic, "ensure_collection", _boom)
    fallback = await semantic.score("same", "same", {"threshold": 0.9})

    llm_judge = SimpleNamespace(
        score=lambda *_args, **_kwargs: None,
    )

    async def _judge_score(*_args: object, **_kwargs: object) -> ScoreResult:
        return ScoreResult(score=4.0, rationale="coherent", extra={"max_scale": 5.0})

    llm_judge.score = _judge_score
    trajectory = TrajectoryScorer(
        execution_query=ExecutionQueryStub(
            journal_items=[
                SimpleNamespace(
                    event_type="completed",
                    step_id="s1",
                    agent_fqn="tool.alpha",
                    payload={"output": "done"},
                )
            ],
            task_plan=[{"selected_tool": "tool.alpha"}],
        ),
        reasoning_engine=ReasoningEngineStub(traces=[{"summary": "done"}]),
        llm_judge=llm_judge,
    )
    trajectory_result = await trajectory.score(
        "done",
        "done",
        {
            "execution_id": str(uuid4()),
            "include_llm_holistic": True,
            "judge_model": "demo",
            "token_cost_ratio": 1.0,
        },
    )
    missing_execution = await trajectory.score("x", "y", {})

    assert semantic_result.score == 1.0
    assert semantic_result.passed is True
    assert fallback.error == "semantic_similarity_fallback"
    assert trajectory_result.passed is True
    assert trajectory_result.extra["llm_judge_holistic"]["score"] == 4.0
    assert missing_execution.error == "missing_execution_id"
    assert SemanticSimilarityScorer._extract_embedding({"embedding": [1, 2]}) == [1.0, 2.0]
    assert SemanticSimilarityScorer._extract_embedding({"data": [{"embedding": [3, 4]}]}) == [
        3.0,
        4.0,
    ]
    assert SemanticSimilarityScorer._cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


@pytest.mark.asyncio
async def test_evaluation_and_testing_events_publish_and_register() -> None:
    producer = EventProducerStub()
    correlation = CorrelationContext(correlation_id=uuid4(), workspace_id=uuid4())
    run_payload = RunStartedPayload(
        run_id=uuid4(),
        eval_set_id=uuid4(),
        workspace_id=correlation.workspace_id,
        agent_fqn="agents.demo",
    )
    testing_payload = SuiteGeneratedPayload(
        suite_id=uuid4(),
        workspace_id=correlation.workspace_id,
        agent_fqn="agents.demo",
        suite_type=SuiteType.adversarial.value,
        case_count=10,
    )

    register_evaluation_event_types()
    register_testing_event_types()
    await publish_evaluation_event(
        producer,
        EvaluationEventType.run_started,
        run_payload,
        correlation,
    )
    await publish_evaluation_event(
        producer,
        EvaluationEventType.human_grade_submitted,
        HumanGradeSubmittedPayload(
            grade_id=uuid4(),
            verdict_id=uuid4(),
            workspace_id=correlation.workspace_id,
            decision="confirmed",
        ),
        correlation,
    )
    await publish_testing_event(
        producer,
        TestingEventType.suite_generated,
        testing_payload,
        correlation,
    )
    await publish_testing_event(
        producer,
        TestingEventType.drift_detected,
        TestingDriftDetectedPayload(
            alert_id=uuid4(),
            workspace_id=correlation.workspace_id,
            agent_fqn="agents.demo",
            eval_set_id=uuid4(),
            metric_name="overall_score",
            stddevs_from_baseline=2.5,
        ),
        correlation,
    )

    assert event_registry.is_registered(EvaluationEventType.run_started.value) is True
    assert event_registry.is_registered(TestingEventType.suite_generated.value) is True
    assert [item["event_type"] for item in producer.published] == [
        "evaluation.run.started",
        "evaluation.human.grade.submitted",
        "evaluation.suite.generated",
        "evaluation.drift.detected",
    ]


@pytest.mark.asyncio
async def test_evaluation_repository_methods_cover_crud_and_queries() -> None:
    session = SessionStub()
    repo = EvaluationRepository(session)  # type: ignore[arg-type]
    eval_set = build_eval_set()
    case = build_benchmark_case(eval_set_id=eval_set.id)
    run = build_run(workspace_id=eval_set.workspace_id, eval_set_id=eval_set.id)
    verdict = build_verdict(run_id=run.id, benchmark_case_id=case.id)
    experiment = build_experiment(
        workspace_id=eval_set.workspace_id, run_a_id=run.id, run_b_id=run.id
    )
    ate_config = build_ate_config(workspace_id=eval_set.workspace_id)
    ate_run = build_ate_run(workspace_id=eval_set.workspace_id, ate_config_id=ate_config.id)
    robustness = build_robustness_run(workspace_id=eval_set.workspace_id, eval_set_id=eval_set.id)
    grade = build_human_grade(verdict_id=verdict.id)

    assert await repo.create_eval_set(eval_set) is eval_set
    session.queue_execute(ResultStub(scalar_one_or_none=eval_set))
    assert await repo.get_eval_set(eval_set.id, eval_set.workspace_id) is eval_set
    session.queue_scalar(1)
    session.queue_execute(ResultStub(scalars=[eval_set]))
    items, total = await repo.list_eval_sets(
        eval_set.workspace_id, status=None, page=1, page_size=10
    )
    assert items == [eval_set]
    assert total == 1
    updated_eval_set = await repo.update_eval_set(eval_set, name="Updated")
    deleted_eval_set = await repo.soft_delete_eval_set(eval_set)
    session.queue_scalar(3, 4)
    assert await repo.count_benchmark_cases(eval_set.id) == 3
    assert await repo.get_next_case_position(eval_set.id) == 5
    assert await repo.create_benchmark_case(case) is case
    session.queue_execute(ResultStub(scalar_one_or_none=case))
    assert await repo.get_benchmark_case(case.id, eval_set_id=eval_set.id) is case
    session.queue_scalar(1)
    session.queue_execute(ResultStub(scalars=[case]))
    listed_cases, case_total = await repo.list_benchmark_cases(
        eval_set.id,
        category=None,
        page=1,
        page_size=10,
    )
    assert listed_cases == [case]
    assert case_total == 1
    session.queue_execute(ResultStub(scalars=[case]))
    assert await repo.list_all_benchmark_cases(eval_set.id) == [case]
    await repo.delete_benchmark_case(case)

    assert await repo.create_run(run) is run
    session.queue_execute(ResultStub(scalar_one_or_none=run))
    assert await repo.get_run(run.id, run.workspace_id) is run
    session.queue_scalar(1)
    session.queue_execute(ResultStub(scalars=[run]))
    listed_runs, run_total = await repo.list_runs(
        run.workspace_id,
        eval_set_id=run.eval_set_id,
        agent_fqn=run.agent_fqn,
        status=None,
        page=1,
        page_size=10,
    )
    assert listed_runs == [run]
    assert run_total == 1
    updated_run = await repo.update_run(run, aggregate_score=0.9)
    assert await repo.create_verdict(verdict) is verdict
    session.queue_execute(ResultStub(scalar_one_or_none=verdict))
    assert await repo.get_verdict(verdict.id) is verdict
    session.queue_scalar(1)
    session.queue_execute(ResultStub(scalars=[verdict]))
    verdicts, verdict_total = await repo.list_run_verdicts(
        run.id,
        passed=None,
        status=None,
        page=1,
        page_size=10,
    )
    assert verdicts == [verdict]
    assert verdict_total == 1
    session.queue_execute(ResultStub(scalars=[verdict]))
    assert await repo.list_verdicts_by_run(run.id) == [verdict]
    session.queue_execute(ResultStub(scalars=[1.0, None, 0.5]))
    assert await repo.get_run_score_array(run.id) == [1.0, 0.5]

    assert await repo.create_ab_experiment(experiment) is experiment
    session.queue_execute(ResultStub(scalar_one_or_none=experiment))
    assert await repo.get_ab_experiment(experiment.id, experiment.workspace_id) is experiment
    updated_experiment = await repo.update_ab_experiment(experiment, winner="a")

    assert await repo.create_ate_config(ate_config) is ate_config
    session.queue_execute(ResultStub(scalar_one_or_none=ate_config))
    assert await repo.get_ate_config(ate_config.id, ate_config.workspace_id) is ate_config
    session.queue_scalar(1)
    session.queue_execute(ResultStub(scalars=[ate_config]))
    ate_configs, ate_total = await repo.list_ate_configs(
        ate_config.workspace_id, page=1, page_size=10
    )
    assert ate_configs == [ate_config]
    assert ate_total == 1
    updated_ate_config = await repo.update_ate_config(ate_config, name="ATE updated")
    deleted_ate_config = await repo.soft_delete_ate_config(ate_config)
    assert await repo.create_ate_run(ate_run) is ate_run
    session.queue_execute(ResultStub(scalar_one_or_none=ate_run))
    assert await repo.get_ate_run(ate_run.id, ate_run.workspace_id) is ate_run
    session.queue_scalar(1)
    session.queue_execute(ResultStub(scalars=[ate_run]))
    ate_runs, ate_run_total = await repo.list_ate_runs(ate_config.id, page=1, page_size=10)
    assert ate_runs == [ate_run]
    assert ate_run_total == 1
    updated_ate_run = await repo.update_ate_run(ate_run, simulation_id=uuid4())

    assert await repo.create_robustness_run(robustness) is robustness
    session.queue_execute(ResultStub(scalar_one_or_none=robustness))
    assert await repo.get_robustness_run(robustness.id, robustness.workspace_id) is robustness
    session.queue_execute(ResultStub(scalars=[robustness]))
    assert await repo.list_active_robustness_runs_by_agent(robustness.agent_fqn) == [robustness]
    session.queue_execute(ResultStub(scalars=[robustness]))
    assert await repo.list_pending_robustness_runs(limit=5) == [robustness]
    updated_robustness = await repo.update_robustness_run(robustness, completed_trials=1)

    assert await repo.create_human_grade(grade) is grade
    session.queue_execute(ResultStub(scalar_one_or_none=grade))
    assert await repo.get_human_grade(grade.id) is grade
    session.queue_execute(ResultStub(scalar_one_or_none=grade))
    assert await repo.get_human_grade_by_verdict(verdict.id) is grade
    updated_grade = await repo.update_human_grade(grade, feedback="updated")
    session.queue_scalar(3, 2, 1)
    progress = await repo.get_review_progress(run.id)
    session.queue_execute(ResultStub(scalar_one_or_none=0.88))
    latest = await repo.get_latest_completed_run_score(
        workspace_id=run.workspace_id,
        agent_fqn=run.agent_fqn,
        eval_set_id=run.eval_set_id,
    )

    assert updated_eval_set.name == "Updated"
    assert deleted_eval_set.deleted_at is not None
    assert updated_run.aggregate_score == 0.9
    assert updated_experiment.winner == "a"
    assert updated_ate_config.name == "ATE updated"
    assert deleted_ate_config.deleted_at is not None
    assert updated_ate_run.simulation_id is not None
    assert updated_robustness.completed_trials == 1
    assert updated_grade.feedback == "updated"
    assert progress == {
        "total_verdicts": 3,
        "pending_review": 1,
        "reviewed": 2,
        "overridden": 1,
    }
    assert latest == 0.88
    assert session.deleted == [case]


@pytest.mark.asyncio
async def test_scorer_registry_and_internal_scorer_helpers_cover_remaining_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ScorerRegistry()
    registry.register("exact_match", ExactMatchScorer())

    assert registry.has("exact_match") is True
    assert registry.registered_types() == ["exact_match"]
    assert hasattr(EvalSuiteServiceInterface, "get_run_summary")
    with pytest.raises(KeyError, match="Unknown scorer type"):
        registry.get("missing")

    llm_judge = LLMJudgeScorer(settings=make_settings(), api_url="http://judge.example")
    criteria = RUBRIC_TEMPLATES["helpfulness"]["criteria"]

    class _JudgeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class _JudgeClient:
        async def __aenter__(self) -> _JudgeClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, *_args: object, **_kwargs: object) -> _JudgeResponse:
            return _JudgeResponse(
                {
                    "text": (
                        '{"score": 4, "criteria_scores": {"usefulness": 4, "clarity": 3},'
                        ' "rationale": "provider"}'
                    )
                }
            )

    monkeypatch.setattr(
        "platform.evaluation.scorers.llm_judge.httpx.AsyncClient",
        lambda timeout: _JudgeClient(),
    )
    provider_result = await llm_judge._judge_once_provider(
        actual="actual",
        expected="expected",
        judge_model="demo",
        criteria=criteria,
        endpoint="http://judge.example",
    )

    assert provider_result["score"] == 4.0
    assert "Criteria:" in llm_judge._build_prompt(
        actual="a",
        expected="b",
        criteria=criteria,
    )
    with pytest.raises(ValueError, match="requires rubric"):
        llm_judge._validate_config({"judge_model": "demo"})
    with pytest.raises(ValueError, match="unsupported"):
        llm_judge._resolve_criteria(
            llm_judge._validate_config(
                {
                    "judge_model": "demo",
                    "rubric": {"template": "unknown-template"},
                    "calibration_runs": 1,
                }
            ).rubric
        )
    with pytest.raises(ValueError, match="Expecting value"):
        llm_judge._parse_provider_result({"output": "not-json"}, criteria)

    qdrant_calls: list[tuple[str, object | None, bool]] = []
    stored_vectors: list[object] = []

    class _QdrantStub:
        async def create_collection_if_not_exists(
            self,
            *,
            collection: str,
            vectors_config: object,
            on_disk_payload: bool,
        ) -> None:
            qdrant_calls.append((collection, vectors_config, on_disk_payload))

        async def upsert_vectors(self, collection: str, points: list[object]) -> None:
            qdrant_calls.append((collection, None, True))
            stored_vectors.extend(points)

    semantic = SemanticSimilarityScorer(settings=make_settings(), qdrant=_QdrantStub())
    monkeypatch.setattr(
        "platform.evaluation.scorers.semantic.import_module",
        lambda _name: SimpleNamespace(
            VectorParams=lambda **kwargs: kwargs,
            Distance=SimpleNamespace(COSINE="cosine"),
        ),
    )

    class _EmbeddingResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": [{"embedding": [0.5, 0.25]}]}

    class _EmbeddingClient:
        async def __aenter__(self) -> _EmbeddingClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, *_args: object, **_kwargs: object) -> _EmbeddingResponse:
            return _EmbeddingResponse()

    monkeypatch.setattr(
        "platform.evaluation.scorers.semantic.httpx.AsyncClient",
        lambda timeout: _EmbeddingClient(),
    )
    await semantic.ensure_collection()
    await semantic.ensure_collection()
    embedded = await semantic._embed_text("hello")
    await semantic._store_embeddings([1.0, 0.0], [0.0, 1.0])

    assert len(qdrant_calls) == 2
    assert embedded == [0.5, 0.25]
    assert len(stored_vectors) == 2
    with pytest.raises(ValueError, match="missing vector payload"):
        SemanticSimilarityScorer._extract_embedding({})
    with pytest.raises(ValueError, match="matching sizes"):
        SemanticSimilarityScorer._cosine_similarity([1.0], [1.0, 2.0])
    assert SemanticSimilarityScorer._cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    empty_trajectory = TrajectoryScorer()
    no_getter_trajectory = TrajectoryScorer(execution_query=SimpleNamespace())
    no_reasoning_getter = TrajectoryScorer(reasoning_engine=SimpleNamespace())
    alternate_trajectory = TrajectoryScorer(
        execution_query=SimpleNamespace(
            get_journal_events=AsyncMock(return_value=[{"agent_fqn": "tool.alpha"}]),
            get_task_plan_record=AsyncMock(return_value={"selected_tool": "tool.alpha"}),
        ),
        reasoning_engine=SimpleNamespace(
            fetch_reasoning_traces=AsyncMock(
                return_value=SimpleNamespace(items=[{"summary": "expected"}, "ignored"])
            )
        ),
    )

    assert await empty_trajectory._get_journal_events(uuid4()) == []
    assert await empty_trajectory._get_task_plan(uuid4()) == []
    assert await empty_trajectory._get_reasoning_traces(uuid4()) == []
    assert await no_getter_trajectory._get_journal_events(uuid4()) == []
    assert await no_getter_trajectory._get_task_plan(uuid4()) == []
    assert await no_reasoning_getter._get_reasoning_traces(uuid4()) == []
    assert await alternate_trajectory._get_journal_events(uuid4()) == [{"agent_fqn": "tool.alpha"}]
    assert await alternate_trajectory._get_task_plan(uuid4()) == [{"selected_tool": "tool.alpha"}]
    assert await alternate_trajectory._get_reasoning_traces(uuid4()) == [
        {"summary": "expected"},
        "ignored",
    ]
    assert TrajectoryScorer._score_tool_alignment([], []) == 1.0
    assert TrajectoryScorer._score_tool_alignment([{"selected_tool": ""}], []) == 1.0
    assert TrajectoryScorer._score_tool_alignment([{"selected_tool": "tool.alpha"}], []) == 0.5
    assert (
        TrajectoryScorer._score_cost_effectiveness(
            "expected",
            "expected",
            {"token_cost_ratio": 2},
            [],
        )
        == 0.5
    )
    assert await alternate_trajectory._score_reasoning_coherence([], "close enough", "close") > 0


@pytest.mark.asyncio
async def test_testing_repository_methods_cover_crud_and_queries() -> None:
    session = SessionStub()
    repo = TestingRepository(session)  # type: ignore[arg-type]
    suite = build_suite()
    adversarial_case = build_adversarial_case(suite_id=suite.id)
    coordination = build_coordination_result(workspace_id=suite.workspace_id)
    alert = build_drift_alert(workspace_id=suite.workspace_id)

    session.queue_scalar(2)
    assert (
        await repo.get_next_suite_version(
            workspace_id=suite.workspace_id,
            agent_fqn=suite.agent_fqn,
            suite_type=suite.suite_type,
        )
        == 3
    )
    assert await repo.create_suite(suite) is suite
    session.queue_execute(ResultStub(scalar_one_or_none=suite))
    assert await repo.get_suite(suite.id, suite.workspace_id) is suite
    session.queue_scalar(1)
    session.queue_execute(ResultStub(scalars=[suite]))
    suites, total = await repo.list_suites(
        suite.workspace_id,
        agent_fqn=suite.agent_fqn,
        suite_type=suite.suite_type,
        page=1,
        page_size=10,
    )
    assert suites == [suite]
    assert total == 1
    updated_suite = await repo.update_suite(suite, case_count=7)
    assert await repo.create_adversarial_case(adversarial_case) is adversarial_case
    created_many = await repo.create_adversarial_cases([adversarial_case])
    session.queue_scalar(1)
    session.queue_execute(ResultStub(scalars=[adversarial_case]))
    cases, case_total = await repo.list_adversarial_cases(
        suite.id,
        category=AdversarialCategory.prompt_injection,
        page=1,
        page_size=10,
    )
    session.queue_execute(ResultStub(rows=[(AdversarialCategory.prompt_injection, 2)]))
    counts = await repo.count_cases_by_category(suite.id)
    assert created_many == [adversarial_case]
    assert cases == [adversarial_case]
    assert case_total == 1
    assert counts == {"prompt_injection": 2}

    assert await repo.create_coordination_result(coordination) is coordination
    session.queue_execute(ResultStub(scalar_one_or_none=coordination))
    assert (
        await repo.get_coordination_result(coordination.id, coordination.workspace_id)
        is coordination
    )

    assert await repo.create_drift_alert(alert) is alert
    session.queue_execute(ResultStub(scalar_one_or_none=alert))
    assert await repo.get_drift_alert(alert.id, alert.workspace_id) is alert
    session.queue_scalar(1)
    session.queue_execute(ResultStub(scalars=[alert]))
    alerts, alert_total = await repo.list_drift_alerts(
        alert.workspace_id,
        agent_fqn=alert.agent_fqn,
        eval_set_id=alert.eval_set_id,
        acknowledged=False,
        page=1,
        page_size=10,
    )
    acknowledged = await repo.acknowledge_drift_alert(
        alert,
        acknowledged_by=uuid4(),
        acknowledged_at=alert.created_at,
    )

    assert updated_suite.case_count == 7
    assert alerts == [alert]
    assert alert_total == 1
    assert acknowledged.acknowledged is True


def test_models_and_response_schemas_validate_feature_objects() -> None:
    assert EvalSetResponse.model_validate(build_eval_set()).name == "Eval Set"
    assert BenchmarkCaseResponse.model_validate(build_benchmark_case()).category == "general"
    assert EvaluationRunResponse.model_validate(build_run()).agent_fqn == "agents.demo"
    assert JudgeVerdictResponse.model_validate(build_verdict()).passed is True
    assert AbExperimentResponse.model_validate(build_experiment()).name == "AB"
    assert ATEConfigResponse.model_validate(build_ate_config()).name == "ATE"
    assert ATERunResponse.model_validate(build_ate_run()).agent_fqn == "agents.demo"
    assert RobustnessTestRunResponse.model_validate(build_robustness_run()).trial_count == 3
    assert HumanAiGradeResponse.model_validate(build_human_grade()).original_score == 0.8
    assert (
        GeneratedTestSuiteResponse.model_validate(build_suite()).suite_type == SuiteType.adversarial
    )
    assert (
        AdversarialCaseResponse.model_validate(build_adversarial_case()).category
        is AdversarialCategory.prompt_injection
    )
    assert (
        CoordinationTestResultResponse.model_validate(build_coordination_result()).overall_score
        == 0.85
    )
    assert DriftAlertResponse.model_validate(build_drift_alert()).metric_name == "overall_score"
    assert ClickHouseStub().commands == []
