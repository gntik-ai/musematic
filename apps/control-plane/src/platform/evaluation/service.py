from __future__ import annotations

import statistics
from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError
from platform.common.tracing import traced_async
from platform.evaluation.events import (
    EvaluationEventType,
    RunCompletedPayload,
    RunFailedPayload,
    RunStartedPayload,
    VerdictScoredPayload,
    publish_evaluation_event,
)
from platform.evaluation.models import (
    BenchmarkCase,
    EvalSet,
    EvaluationRun,
    JudgeVerdict,
    RunStatus,
    VerdictStatus,
)
from platform.evaluation.repository import EvaluationRepository
from platform.evaluation.schemas import (
    BenchmarkCaseCreate,
    BenchmarkCaseListResponse,
    BenchmarkCaseResponse,
    EvalRunSummaryDTO,
    EvalSetCreate,
    EvalSetListResponse,
    EvalSetResponse,
    EvalSetUpdate,
    EvaluationRunCreate,
    EvaluationRunListResponse,
    EvaluationRunResponse,
    JudgeVerdictListResponse,
    JudgeVerdictResponse,
)
from platform.evaluation.scorers.base import ScoreResult
from platform.evaluation.scorers.registry import ScorerRegistry
from typing import Any
from uuid import UUID, uuid4


class EvalSuiteService:
    def __init__(
        self,
        *,
        repository: EvaluationRepository,
        settings: Any,
        producer: EventProducer | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer

    @traced_async("evaluation.eval_suite.create_eval_set")
    async def create_eval_set(self, payload: EvalSetCreate, actor_id: UUID) -> EvalSetResponse:
        eval_set = await self.repository.create_eval_set(
            EvalSet(
                workspace_id=payload.workspace_id,
                name=payload.name,
                description=payload.description,
                scorer_config=payload.scorer_config,
                pass_threshold=payload.pass_threshold,
                created_by=actor_id,
            )
        )
        await self._commit()
        return EvalSetResponse.model_validate(eval_set)

    @traced_async("evaluation.eval_suite.list_eval_sets")
    async def list_eval_sets(
        self,
        *,
        workspace_id: UUID,
        status: Any | None,
        page: int,
        page_size: int,
    ) -> EvalSetListResponse:
        items, total = await self.repository.list_eval_sets(
            workspace_id,
            status=status,
            page=page,
            page_size=page_size,
        )
        return EvalSetListResponse(
            items=[EvalSetResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @traced_async("evaluation.eval_suite.get_eval_set")
    async def get_eval_set(
        self,
        eval_set_id: UUID,
        workspace_id: UUID | None = None,
    ) -> EvalSetResponse:
        eval_set = await self.repository.get_eval_set(eval_set_id, workspace_id)
        if eval_set is None:
            raise NotFoundError("EVAL_SET_NOT_FOUND", "Evaluation set not found")
        return EvalSetResponse.model_validate(eval_set)

    @traced_async("evaluation.eval_suite.update_eval_set")
    async def update_eval_set(self, eval_set_id: UUID, payload: EvalSetUpdate) -> EvalSetResponse:
        eval_set = await self.repository.get_eval_set(eval_set_id)
        if eval_set is None:
            raise NotFoundError("EVAL_SET_NOT_FOUND", "Evaluation set not found")
        updated = await self.repository.update_eval_set(
            eval_set,
            **payload.model_dump(exclude_unset=True),
        )
        await self._commit()
        return EvalSetResponse.model_validate(updated)

    @traced_async("evaluation.eval_suite.archive_eval_set")
    async def archive_eval_set(self, eval_set_id: UUID) -> None:
        eval_set = await self.repository.get_eval_set(eval_set_id)
        if eval_set is None:
            raise NotFoundError("EVAL_SET_NOT_FOUND", "Evaluation set not found")
        await self.repository.soft_delete_eval_set(eval_set)
        await self._commit()

    @traced_async("evaluation.eval_suite.create_benchmark_case")
    async def create_benchmark_case(
        self,
        eval_set_id: UUID,
        payload: BenchmarkCaseCreate,
    ) -> BenchmarkCaseResponse:
        eval_set = await self.repository.get_eval_set(eval_set_id)
        if eval_set is None:
            raise NotFoundError("EVAL_SET_NOT_FOUND", "Evaluation set not found")
        position = (
            payload.position
            if payload.position is not None
            else await self.repository.get_next_case_position(eval_set_id)
        )
        case = await self.repository.create_benchmark_case(
            BenchmarkCase(
                eval_set_id=eval_set_id,
                input_data=payload.input_data,
                expected_output=payload.expected_output,
                scoring_criteria=payload.scoring_criteria,
                metadata_tags=payload.metadata_tags,
                category=payload.category,
                position=position,
            )
        )
        await self._commit()
        return BenchmarkCaseResponse.model_validate(case)

    @traced_async("evaluation.eval_suite.list_benchmark_cases")
    async def list_benchmark_cases(
        self,
        *,
        eval_set_id: UUID,
        category: str | None,
        page: int,
        page_size: int,
    ) -> BenchmarkCaseListResponse:
        items, total = await self.repository.list_benchmark_cases(
            eval_set_id,
            category=category,
            page=page,
            page_size=page_size,
        )
        return BenchmarkCaseListResponse(
            items=[BenchmarkCaseResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @traced_async("evaluation.eval_suite.get_benchmark_case")
    async def get_benchmark_case(self, eval_set_id: UUID, case_id: UUID) -> BenchmarkCaseResponse:
        case = await self.repository.get_benchmark_case(case_id, eval_set_id=eval_set_id)
        if case is None:
            raise NotFoundError("BENCHMARK_CASE_NOT_FOUND", "Benchmark case not found")
        return BenchmarkCaseResponse.model_validate(case)

    @traced_async("evaluation.eval_suite.delete_benchmark_case")
    async def delete_benchmark_case(self, eval_set_id: UUID, case_id: UUID) -> None:
        case = await self.repository.get_benchmark_case(case_id, eval_set_id=eval_set_id)
        if case is None:
            raise NotFoundError("BENCHMARK_CASE_NOT_FOUND", "Benchmark case not found")
        await self.repository.delete_benchmark_case(case)
        await self._commit()

    @traced_async("evaluation.eval_suite.get_run_summary")
    async def get_run_summary(self, run_id: UUID) -> EvalRunSummaryDTO:
        run = await self.repository.get_run(run_id)
        if run is None:
            raise NotFoundError("EVALUATION_RUN_NOT_FOUND", "Evaluation run not found")
        return EvalRunSummaryDTO(
            run_id=run.id,
            eval_set_id=run.eval_set_id,
            workspace_id=run.workspace_id,
            agent_fqn=run.agent_fqn,
            aggregate_score=run.aggregate_score,
            passed_cases=run.passed_cases,
            failed_cases=run.failed_cases,
            error_cases=run.error_cases,
            total_cases=run.total_cases,
            status=run.status,
        )

    @traced_async("evaluation.eval_suite.get_latest_agent_score")
    async def get_latest_agent_score(
        self,
        agent_fqn: str,
        eval_set_id: UUID,
        workspace_id: UUID,
    ) -> float | None:
        return await self.repository.get_latest_completed_run_score(
            workspace_id=workspace_id,
            agent_fqn=agent_fqn,
            eval_set_id=eval_set_id,
        )

    @traced_async("evaluation.eval_suite.commit")
    async def _commit(self) -> None:
        await self.repository.session.commit()


class EvalRunnerService:
    def __init__(
        self,
        *,
        repository: EvaluationRepository,
        settings: Any,
        scorer_registry: ScorerRegistry,
        producer: EventProducer | None = None,
        runtime_controller: Any | None = None,
        execution_query: Any | None = None,
        drift_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.scorer_registry = scorer_registry
        self.producer = producer
        self.runtime_controller = runtime_controller
        self.execution_query = execution_query
        self.drift_service = drift_service

    @traced_async("evaluation.eval_runner.start_run")
    async def start_run(
        self,
        eval_set_id: UUID,
        payload: EvaluationRunCreate,
        workspace_id: UUID,
    ) -> EvaluationRunResponse:
        eval_set = await self.repository.get_eval_set(eval_set_id, workspace_id)
        if eval_set is None:
            raise NotFoundError("EVAL_SET_NOT_FOUND", "Evaluation set not found")
        run = await self.repository.create_run(
            EvaluationRun(
                workspace_id=workspace_id,
                eval_set_id=eval_set_id,
                agent_fqn=payload.agent_fqn,
                agent_id=payload.agent_id,
                status=RunStatus.pending,
            )
        )
        await self._commit()
        return EvaluationRunResponse.model_validate(run)

    @traced_async("evaluation.eval_runner.run_eval_set")
    async def run_eval_set(
        self,
        *,
        eval_set_id: UUID,
        workspace_id: UUID,
        agent_fqn: str,
        agent_id: UUID | None = None,
        benchmark_case_id: UUID | None = None,
    ) -> EvaluationRunResponse:
        response = await self.start_run(
            eval_set_id,
            EvaluationRunCreate(agent_fqn=agent_fqn, agent_id=agent_id),
            workspace_id,
        )
        return await self.run_existing(response.id, benchmark_case_id=benchmark_case_id)

    @traced_async("evaluation.eval_runner.run_existing")
    async def run_existing(
        self,
        run_id: UUID,
        *,
        benchmark_case_id: UUID | None = None,
    ) -> EvaluationRunResponse:
        run = await self.repository.get_run(run_id)
        if run is None:
            raise NotFoundError("EVALUATION_RUN_NOT_FOUND", "Evaluation run not found")
        eval_set = await self.repository.get_eval_set(run.eval_set_id, run.workspace_id)
        if eval_set is None:
            raise NotFoundError("EVAL_SET_NOT_FOUND", "Evaluation set not found")
        cases = await self.repository.list_all_benchmark_cases(eval_set.id)
        if benchmark_case_id is not None:
            cases = [case for case in cases if case.id == benchmark_case_id]
        correlation = self._correlation(run.workspace_id)
        await self.repository.update_run(
            run,
            status=RunStatus.running,
            started_at=datetime.now(UTC),
            total_cases=len(cases),
            passed_cases=0,
            failed_cases=0,
            error_cases=0,
            aggregate_score=None,
            error_detail=None,
        )
        await self._commit()
        await publish_evaluation_event(
            self.producer,
            EvaluationEventType.run_started,
            RunStartedPayload(
                run_id=run.id,
                eval_set_id=run.eval_set_id,
                workspace_id=run.workspace_id,
                agent_fqn=run.agent_fqn,
            ),
            correlation,
        )
        try:
            verdict_scores: list[float] = []
            passed_cases = 0
            failed_cases = 0
            error_cases = 0
            for case in cases:
                verdict = await self._score_case(run, eval_set, case)
                if verdict.overall_score is not None:
                    verdict_scores.append(verdict.overall_score)
                if verdict.status is VerdictStatus.error:
                    error_cases += 1
                elif verdict.passed:
                    passed_cases += 1
                else:
                    failed_cases += 1
                await publish_evaluation_event(
                    self.producer,
                    EvaluationEventType.verdict_scored,
                    VerdictScoredPayload(
                        verdict_id=verdict.id,
                        run_id=run.id,
                        case_id=case.id,
                        overall_score=verdict.overall_score,
                        passed=verdict.passed,
                    ),
                    correlation,
                )
            aggregate_score = statistics.mean(verdict_scores) if verdict_scores else None
            await self.repository.update_run(
                run,
                status=RunStatus.completed,
                completed_at=datetime.now(UTC),
                total_cases=len(cases),
                passed_cases=passed_cases,
                failed_cases=failed_cases,
                error_cases=error_cases,
                aggregate_score=aggregate_score,
            )
            await self._commit()
            await publish_evaluation_event(
                self.producer,
                EvaluationEventType.run_completed,
                RunCompletedPayload(
                    run_id=run.id,
                    eval_set_id=run.eval_set_id,
                    workspace_id=run.workspace_id,
                    aggregate_score=aggregate_score,
                    passed_cases=passed_cases,
                    total_cases=len(cases),
                ),
                correlation,
            )
            if self.drift_service is not None and aggregate_score is not None:
                record_metric = getattr(self.drift_service, "record_eval_metric", None)
                if callable(record_metric):
                    await record_metric(
                        run_id=run.id,
                        agent_fqn=run.agent_fqn,
                        eval_set_id=run.eval_set_id,
                        score=aggregate_score,
                        workspace_id=run.workspace_id,
                    )
            return EvaluationRunResponse.model_validate(run)
        except Exception as exc:
            await self.repository.update_run(
                run,
                status=RunStatus.failed,
                completed_at=datetime.now(UTC),
                error_detail=str(exc),
            )
            await self._commit()
            await publish_evaluation_event(
                self.producer,
                EvaluationEventType.run_failed,
                RunFailedPayload(
                    run_id=run.id,
                    eval_set_id=run.eval_set_id,
                    workspace_id=run.workspace_id,
                    error_detail=str(exc),
                ),
                correlation,
            )
            raise

    @traced_async("evaluation.eval_runner.list_runs")
    async def list_runs(
        self,
        *,
        workspace_id: UUID,
        eval_set_id: UUID | None,
        agent_fqn: str | None,
        status: Any | None,
        page: int,
        page_size: int,
    ) -> EvaluationRunListResponse:
        items, total = await self.repository.list_runs(
            workspace_id,
            eval_set_id=eval_set_id,
            agent_fqn=agent_fqn,
            status=status,
            page=page,
            page_size=page_size,
        )
        return EvaluationRunListResponse(
            items=[EvaluationRunResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @traced_async("evaluation.eval_runner.get_run")
    async def get_run(self, run_id: UUID) -> EvaluationRunResponse:
        run = await self.repository.get_run(run_id)
        if run is None:
            raise NotFoundError("EVALUATION_RUN_NOT_FOUND", "Evaluation run not found")
        return EvaluationRunResponse.model_validate(run)

    @traced_async("evaluation.eval_runner.list_run_verdicts")
    async def list_run_verdicts(
        self,
        *,
        run_id: UUID,
        passed: bool | None,
        status: Any | None,
        page: int,
        page_size: int,
    ) -> JudgeVerdictListResponse:
        items, total = await self.repository.list_run_verdicts(
            run_id,
            passed=passed,
            status=status,
            page=page,
            page_size=page_size,
        )
        return JudgeVerdictListResponse(
            items=[JudgeVerdictResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @traced_async("evaluation.eval_runner.get_verdict")
    async def get_verdict(self, verdict_id: UUID) -> JudgeVerdictResponse:
        verdict = await self.repository.get_verdict(verdict_id)
        if verdict is None:
            raise NotFoundError("EVALUATION_VERDICT_NOT_FOUND", "Evaluation verdict not found")
        return JudgeVerdictResponse.model_validate(verdict)

    @traced_async("evaluation.eval_runner.score_outputs")
    async def score_outputs(
        self,
        *,
        expected_output: str,
        actual_output: str,
        scorer_config: dict[str, dict[str, Any]],
        input_data: dict[str, Any] | None = None,
        pass_threshold: float = 0.7,
    ) -> tuple[dict[str, Any], float | None, bool | None, VerdictStatus, str | None]:
        scorer_results: dict[str, Any] = {}
        normalized_scores: list[float] = []
        errors: list[str] = []
        for scorer_name, raw_config in scorer_config.items():
            if not raw_config.get("enabled", True):
                continue
            scorer_kwargs = dict(raw_config)
            scorer_kwargs.setdefault("threshold", raw_config.get("threshold"))
            if (
                scorer_name == "trajectory"
                and input_data is not None
                and "execution_id" in input_data
            ):
                scorer_kwargs["execution_id"] = input_data["execution_id"]
            try:
                scorer = self.scorer_registry.get(scorer_name)
                result = await scorer.score(actual_output, expected_output, scorer_kwargs)
            except Exception as exc:
                result = ScoreResult(
                    score=None,
                    passed=None,
                    error=f"{scorer_name}_error",
                    rationale=str(exc),
                )
            flattened = self._flatten_score_result(result)
            scorer_results[scorer_name] = flattened
            if result.error:
                errors.append(result.error)
            if result.score is not None:
                normalized_scores.append(self._normalize_score(scorer_name, result))
        overall_score = statistics.mean(normalized_scores) if normalized_scores else None
        verdict_status = (
            VerdictStatus.error
            if errors and overall_score is None
            else VerdictStatus.scored
        )
        passed = overall_score >= pass_threshold if overall_score is not None else None
        error_detail = "; ".join(errors) if errors else None
        return scorer_results, overall_score, passed, verdict_status, error_detail

    @traced_async("evaluation.eval_runner.score_case")
    async def _score_case(
        self,
        run: EvaluationRun,
        eval_set: EvalSet,
        case: BenchmarkCase,
    ) -> JudgeVerdict:
        actual_output = await self._invoke_agent(run, case)
        merged_config = self._merge_scorer_config(eval_set.scorer_config, case.scoring_criteria)
        scorer_results, overall_score, passed, status, error_detail = await self.score_outputs(
            expected_output=case.expected_output,
            actual_output=actual_output,
            scorer_config=merged_config,
            input_data=case.input_data,
            pass_threshold=eval_set.pass_threshold,
        )
        verdict = await self.repository.create_verdict(
            JudgeVerdict(
                run_id=run.id,
                benchmark_case_id=case.id,
                actual_output=actual_output,
                scorer_results=scorer_results,
                overall_score=overall_score,
                passed=passed,
                error_detail=error_detail,
                status=status,
            )
        )
        await self._commit()
        return verdict

    @traced_async("evaluation.eval_runner.invoke_agent")
    async def _invoke_agent(self, run: EvaluationRun, case: BenchmarkCase) -> str:
        for key in ("actual_output", "mock_response", "response", "output"):
            value = case.input_data.get(key)
            if isinstance(value, str) and value:
                return value
        if self.runtime_controller is not None:
            for method_name in ("run_eval_case", "invoke_agent", "execute_agent", "run_agent"):
                method = getattr(self.runtime_controller, method_name, None)
                if callable(method):
                    result = await method(
                        agent_fqn=run.agent_fqn,
                        agent_id=run.agent_id,
                        input_data=case.input_data,
                        workspace_id=run.workspace_id,
                    )
                    extracted = self._extract_output(result)
                    if extracted is not None:
                        return extracted
        return case.expected_output

    @staticmethod
    def _extract_output(result: Any) -> str | None:
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            for key in ("output", "actual_output", "response", "result", "content"):
                value = result.get(key)
                if isinstance(value, str):
                    return value
        for key in ("output", "actual_output", "response", "result", "content"):
            value = getattr(result, key, None)
            if isinstance(value, str):
                return value
        return None

    @staticmethod
    def _merge_scorer_config(
        base: dict[str, Any],
        overrides: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        scorer_names = set(base) | set(overrides)
        for scorer_name in scorer_names:
            merged[scorer_name] = {}
            if isinstance(base.get(scorer_name), dict):
                merged[scorer_name].update(base[scorer_name])
            if isinstance(overrides.get(scorer_name), dict):
                merged[scorer_name].update(overrides[scorer_name])
        return merged

    @staticmethod
    def _flatten_score_result(result: ScoreResult) -> dict[str, Any]:
        data = result.model_dump(exclude_none=True)
        extra = dict(data.pop("extra", {}))
        data.update(extra)
        return data

    @staticmethod
    def _normalize_score(scorer_name: str, result: ScoreResult) -> float:
        if result.score is None:
            return 0.0
        if scorer_name == "llm_judge":
            max_scale = float(result.extra.get("max_scale", 5.0) or 5.0)
            return max(0.0, min(1.0, float(result.score) / max(max_scale, 1.0)))
        return max(0.0, min(1.0, float(result.score)))

    @staticmethod
    def _correlation(workspace_id: UUID) -> CorrelationContext:
        return CorrelationContext(correlation_id=uuid4(), workspace_id=workspace_id)

    @traced_async("evaluation.eval_runner.commit")
    async def _commit(self) -> None:
        await self.repository.session.commit()
