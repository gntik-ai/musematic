from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.evaluation.models import (
    AbExperiment,
    ATEConfig,
    ATERun,
    ATERunStatus,
    BenchmarkCase,
    EvalSet,
    EvalSetStatus,
    EvaluationRun,
    ExperimentStatus,
    HumanAiGrade,
    JudgeVerdict,
    ReviewDecision,
    RobustnessTestRun,
    RunStatus,
    VerdictStatus,
)
from platform.testing.models import (
    AdversarialCategory,
    AdversarialTestCase,
    CoordinationTestResult,
    DriftAlert,
    GeneratedTestSuite,
    SuiteType,
)
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from starlette.datastructures import QueryParams


def now_utc() -> datetime:
    return datetime.now(UTC)


def make_settings() -> PlatformSettings:
    return PlatformSettings()


def build_eval_set(**overrides: Any) -> EvalSet:
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "name": "Eval Set",
        "description": "desc",
        "scorer_config": {"exact_match": {"enabled": True, "threshold": 1.0}},
        "pass_threshold": 0.7,
        "status": EvalSetStatus.active,
        "created_by": uuid4(),
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "deleted_at": None,
    }
    payload.update(overrides)
    return EvalSet(**payload)


def build_benchmark_case(**overrides: Any) -> BenchmarkCase:
    payload = {
        "id": uuid4(),
        "eval_set_id": uuid4(),
        "input_data": {"prompt": "hello"},
        "expected_output": "world",
        "scoring_criteria": {},
        "metadata_tags": {},
        "category": "general",
        "position": 0,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return BenchmarkCase(**payload)


def build_run(**overrides: Any) -> EvaluationRun:
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "eval_set_id": uuid4(),
        "agent_fqn": "agents.demo",
        "agent_id": None,
        "status": RunStatus.pending,
        "started_at": None,
        "completed_at": None,
        "total_cases": 0,
        "passed_cases": 0,
        "failed_cases": 0,
        "error_cases": 0,
        "aggregate_score": None,
        "error_detail": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return EvaluationRun(**payload)


def build_verdict(**overrides: Any) -> JudgeVerdict:
    payload = {
        "id": uuid4(),
        "run_id": uuid4(),
        "benchmark_case_id": uuid4(),
        "actual_output": "actual",
        "scorer_results": {"exact_match": {"score": 1.0}},
        "overall_score": 1.0,
        "passed": True,
        "error_detail": None,
        "status": VerdictStatus.scored,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return JudgeVerdict(**payload)


def build_experiment(**overrides: Any) -> AbExperiment:
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "name": "AB",
        "run_a_id": uuid4(),
        "run_b_id": uuid4(),
        "status": ExperimentStatus.pending,
        "p_value": None,
        "confidence_interval": None,
        "effect_size": None,
        "winner": None,
        "analysis_summary": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return AbExperiment(**payload)


def build_ate_config(**overrides: Any) -> ATEConfig:
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "name": "ATE",
        "description": "desc",
        "scenarios": [{"id": "s1", "name": "Scenario", "input_data": {}, "expected_output": "x"}],
        "scorer_config": {"exact_match": {"enabled": True}},
        "performance_thresholds": {},
        "safety_checks": [],
        "created_by": uuid4(),
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "deleted_at": None,
    }
    payload.update(overrides)
    return ATEConfig(**payload)


def build_ate_run(**overrides: Any) -> ATERun:
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "ate_config_id": uuid4(),
        "agent_fqn": "agents.demo",
        "agent_id": None,
        "simulation_id": None,
        "status": ATERunStatus.pending,
        "started_at": None,
        "completed_at": None,
        "evidence_artifact_key": None,
        "report": None,
        "pre_check_errors": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return ATERun(**payload)


def build_robustness_run(**overrides: Any) -> RobustnessTestRun:
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "eval_set_id": uuid4(),
        "benchmark_case_id": None,
        "agent_fqn": "agents.demo",
        "trial_count": 3,
        "completed_trials": 0,
        "status": RunStatus.pending,
        "distribution": None,
        "is_unreliable": False,
        "variance_threshold": 0.15,
        "trial_run_ids": [],
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return RobustnessTestRun(**payload)


def build_human_grade(**overrides: Any) -> HumanAiGrade:
    payload = {
        "id": uuid4(),
        "verdict_id": uuid4(),
        "reviewer_id": uuid4(),
        "decision": ReviewDecision.confirmed,
        "override_score": None,
        "feedback": None,
        "original_score": 0.8,
        "reviewed_at": now_utc(),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return HumanAiGrade(**payload)


def build_suite(**overrides: Any) -> GeneratedTestSuite:
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "agent_fqn": "agents.demo",
        "agent_id": None,
        "suite_type": SuiteType.adversarial,
        "version": 1,
        "case_count": 0,
        "category_counts": {},
        "artifact_key": None,
        "imported_into_eval_set_id": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return GeneratedTestSuite(**payload)


def build_adversarial_case(**overrides: Any) -> AdversarialTestCase:
    payload = {
        "id": uuid4(),
        "suite_id": uuid4(),
        "category": AdversarialCategory.prompt_injection,
        "input_data": {"prompt": "ignore"},
        "expected_behavior": "refuse",
        "generation_prompt_hash": "hash",
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return AdversarialTestCase(**payload)


def build_coordination_result(**overrides: Any) -> CoordinationTestResult:
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "fleet_id": uuid4(),
        "execution_id": uuid4(),
        "completion_score": 0.8,
        "coherence_score": 0.9,
        "goal_achievement_score": 0.85,
        "overall_score": 0.85,
        "per_agent_scores": {"agent": {"completion_ratio": 1.0}},
        "insufficient_members": False,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return CoordinationTestResult(**payload)


def build_drift_alert(**overrides: Any) -> DriftAlert:
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "agent_fqn": "agents.demo",
        "eval_set_id": uuid4(),
        "metric_name": "overall_score",
        "baseline_value": 0.9,
        "current_value": 0.5,
        "deviation_magnitude": 0.4,
        "stddevs_from_baseline": 2.5,
        "acknowledged": False,
        "acknowledged_by": None,
        "acknowledged_at": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return DriftAlert(**payload)


class ResultScalars:
    def __init__(self, values: Iterable[Any]) -> None:
        self._values = list(values)

    def all(self) -> list[Any]:
        return list(self._values)


class ResultStub:
    def __init__(
        self,
        *,
        scalar_one_or_none: Any = None,
        scalars: Iterable[Any] | None = None,
        rows: Iterable[Any] | None = None,
    ) -> None:
        self._scalar_one_or_none = scalar_one_or_none
        self._scalars = list(scalars or [])
        self._rows = list(rows or [])

    def scalar_one_or_none(self) -> Any:
        return self._scalar_one_or_none

    def scalars(self) -> ResultScalars:
        return ResultScalars(self._scalars)

    def all(self) -> list[Any]:
        return list(self._rows)


class SessionStub:
    def __init__(self) -> None:
        self.scalar_queue: deque[Any] = deque()
        self.execute_queue: deque[ResultStub] = deque()
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.flushed = 0
        self.commits = 0
        self.rollbacks = 0

    def queue_scalar(self, *values: Any) -> None:
        self.scalar_queue.extend(values)

    def queue_execute(self, *results: ResultStub) -> None:
        self.execute_queue.extend(results)

    async def scalar(self, _query: Any) -> Any:
        return self.scalar_queue.popleft() if self.scalar_queue else None

    async def execute(self, _query: Any) -> ResultStub:
        if self.execute_queue:
            return self.execute_queue.popleft()
        return ResultStub()

    def add(self, item: Any) -> None:
        self.added.append(item)

    def add_all(self, items: Iterable[Any]) -> None:
        self.added.extend(items)

    async def delete(self, item: Any) -> None:
        self.deleted.append(item)

    async def flush(self) -> None:
        self.flushed += 1

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


@dataclass
class ObjectStorageStub:
    buckets: set[str] = field(default_factory=set)
    uploads: dict[tuple[str, str], bytes] = field(default_factory=dict)

    async def create_bucket_if_not_exists(self, bucket: str) -> None:
        self.buckets.add(bucket)

    async def upload_object(
        self,
        bucket: str,
        key: str,
        body: bytes,
        *,
        content_type: str,
    ) -> None:
        del content_type
        self.uploads[(bucket, key)] = body


@dataclass
class ClickHouseStub:
    commands: list[str] = field(default_factory=list)
    inserts: list[tuple[str, list[dict[str, Any]], list[str]]] = field(default_factory=list)
    query_results: deque[list[dict[str, Any]]] = field(default_factory=deque)

    async def execute_command(self, sql: str) -> None:
        self.commands.append(sql)

    async def insert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        columns: list[str],
    ) -> None:
        self.inserts.append((table, rows, columns))

    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        del sql, params
        return self.query_results.popleft() if self.query_results else []


@dataclass
class RuntimeControllerStub:
    result: Any = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def run_eval_case(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.result


@dataclass
class SimulationControllerStub:
    simulation_id: UUID = field(default_factory=uuid4)

    async def create_simulation(self, *, config: dict[str, Any]) -> dict[str, Any]:
        return {"simulation_id": str(self.simulation_id), "config": config}


@dataclass
class ExecutionQueryStub:
    journal_items: list[Any] = field(default_factory=list)
    task_plan: list[Any] = field(default_factory=list)

    async def get_journal(self, execution_id: UUID) -> SimpleNamespace:
        del execution_id
        return SimpleNamespace(items=list(self.journal_items))

    async def get_task_plan(self, execution_id: UUID, _workspace_id: Any) -> list[Any]:
        del execution_id, _workspace_id
        return list(self.task_plan)


@dataclass
class ReasoningEngineStub:
    traces: list[dict[str, Any]] = field(default_factory=list)

    async def get_reasoning_traces(self, *, execution_id: UUID) -> list[dict[str, Any]]:
        del execution_id
        return list(self.traces)


@dataclass
class RegistryServiceStub:
    profile: dict[str, Any] | None = None

    async def get_agent_by_fqn(self, workspace_id: UUID, agent_fqn: str) -> dict[str, Any] | None:
        del workspace_id, agent_fqn
        return self.profile


def make_request(
    *,
    settings: PlatformSettings | None = None,
    clients: dict[str, Any] | None = None,
    context_engineering_service: Any | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings or make_settings(),
                clients=clients or {},
                context_engineering_service=context_engineering_service,
            )
        ),
        headers={},
        query_params=QueryParams(""),
        state=SimpleNamespace(user=None),
    )
