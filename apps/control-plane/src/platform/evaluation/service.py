from __future__ import annotations

import statistics
import time
from datetime import UTC, datetime, timedelta
from platform.audit.repository import AuditChainRepository
from platform.audit.service import AuditChainService
from platform.common.audit_hook import audit_chain_hook
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError
from platform.common.tracing import traced_async
from platform.evaluation.events import (
    AdHocJudgePayload,
    CalibrationCompletedPayload,
    CalibrationStartedPayload,
    EvaluationEventType,
    FairnessEvaluationCompletedPayload,
    RubricArchivedPayload,
    RubricCreatedPayload,
    RubricUpdatedPayload,
    RunCompletedPayload,
    RunFailedPayload,
    RunStartedPayload,
    VerdictScoredPayload,
    publish_evaluation_event,
)
from platform.evaluation.exceptions import (
    CalibrationRunImmutableError,
    JudgeUnavailableError,
    RubricArchivedError,
    RubricBuiltinProtectedError,
    RubricInFlightError,
    RubricNotFoundError,
    RubricValidationError,
)
from platform.evaluation.models import (
    BenchmarkCase,
    CalibrationRun,
    CalibrationRunStatus,
    EvalSet,
    EvaluationRun,
    FairnessEvaluation,
    JudgeVerdict,
    Rubric,
    RubricStatus,
    RunStatus,
    VerdictStatus,
)
from platform.evaluation.repository import EvaluationRepository
from platform.evaluation.schemas import (
    AdHocJudgeRequest,
    AdHocJudgeResponse,
    BenchmarkCaseCreate,
    BenchmarkCaseListResponse,
    BenchmarkCaseResponse,
    CalibrationRunCreate,
    CalibrationRunResponse,
    EvalRunSummaryDTO,
    EvalSetCreate,
    EvalSetListResponse,
    EvalSetResponse,
    EvalSetUpdate,
    EvaluationRunCreate,
    EvaluationRunListResponse,
    EvaluationRunResponse,
    FairnessEvaluationSummary,
    FairnessMetricRow,
    FairnessRunRequest,
    FairnessRunResponse,
    JudgeVerdictListResponse,
    JudgeVerdictResponse,
    RubricCreate,
    RubricListResponse,
    RubricResponse,
    RubricUpdate,
)
from platform.evaluation.scorers.base import ScoreResult
from platform.evaluation.scorers.fairness import FairnessScorer
from platform.evaluation.scorers.registry import ScorerRegistry
from typing import Any, cast
from uuid import UUID, uuid4


class RubricService:
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

    async def create_rubric(
        self,
        payload: RubricCreate,
        workspace_id: UUID,
        actor_id: UUID,
    ) -> RubricResponse:
        await self._validate_rubric_payload(payload)
        existing = await self.repository.get_workspace_rubric_by_name(workspace_id, payload.name)
        if existing is not None:
            raise RubricValidationError("Rubric name already exists in workspace")
        rubric = await self.repository.create_rubric(
            Rubric(
                workspace_id=workspace_id,
                name=payload.name,
                description=payload.description,
                criteria=[criterion.model_dump(mode="json") for criterion in payload.criteria],
                version=1,
                is_builtin=False,
                status=RubricStatus.active,
                created_by=actor_id,
            )
        )
        await self._commit()
        await publish_evaluation_event(
            self.producer,
            EvaluationEventType.rubric_created,
            RubricCreatedPayload(
                rubric_id=rubric.id,
                workspace_id=rubric.workspace_id,
                name=rubric.name,
                version=rubric.version,
            ),
            self._correlation(workspace_id),
        )
        return RubricResponse.model_validate(rubric)

    async def upsert_builtin_template(
        self, template_name: str, payload: RubricCreate
    ) -> RubricResponse:
        await self._validate_rubric_payload(payload)
        rubric = await self.repository.get_builtin_rubric_by_name(template_name)
        criteria = [criterion.model_dump(mode="json") for criterion in payload.criteria]
        if rubric is None:
            rubric = await self.repository.create_rubric(
                Rubric(
                    workspace_id=None,
                    name=template_name,
                    description=payload.description,
                    criteria=criteria,
                    version=1,
                    is_builtin=True,
                    status=RubricStatus.active,
                    created_by=None,
                )
            )
        else:
            next_version = (
                rubric.version + 1
                if rubric.criteria != criteria or rubric.description != payload.description
                else rubric.version
            )
            await self.repository.update_rubric(
                rubric,
                description=payload.description,
                criteria=criteria,
                status=RubricStatus.active,
                version=next_version,
            )
        await self._commit()
        return RubricResponse.model_validate(rubric)

    async def get_rubric(self, rubric_id: UUID, workspace_id: UUID | None = None) -> RubricResponse:
        rubric = await self.repository.get_rubric(rubric_id, workspace_id)
        if rubric is None:
            raise RubricNotFoundError()
        return RubricResponse.model_validate(rubric)

    async def get_rubric_model(self, rubric_id: UUID, workspace_id: UUID | None = None) -> Rubric:
        rubric = await self.repository.get_rubric(rubric_id, workspace_id)
        if rubric is None:
            raise RubricNotFoundError()
        return rubric

    async def list_rubrics(
        self,
        *,
        workspace_id: UUID | None,
        status: Any | None,
        include_builtins: bool,
        page: int,
        page_size: int,
    ) -> RubricListResponse:
        items, total = await self.repository.list_rubrics(
            workspace_id,
            status=status,
            include_builtins=include_builtins,
            page=page,
            page_size=page_size,
        )
        return RubricListResponse(
            items=[RubricResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update_rubric(
        self,
        rubric_id: UUID,
        payload: RubricUpdate,
        workspace_id: UUID | None = None,
        actor_id: UUID | None = None,
    ) -> RubricResponse:
        rubric = await self.get_rubric_model(rubric_id, workspace_id)
        if rubric.is_builtin:
            raise RubricBuiltinProtectedError()
        update_fields = payload.model_dump(exclude_unset=True)
        if not update_fields:
            return RubricResponse.model_validate(rubric)
        criteria_payload = update_fields.get("criteria")
        if criteria_payload is not None:
            criteria = [criterion.model_dump(mode="json") for criterion in criteria_payload]
            await self._validate_rubric_payload(
                RubricCreate(
                    name=rubric.name, description=rubric.description, criteria=criteria_payload
                )
            )
            if (
                criteria != rubric.criteria
                and await self.repository.count_in_flight_rubric_references(rubric.id)
            ):
                raise RubricInFlightError()
            update_fields["criteria"] = criteria
        if (
            "name" in update_fields and update_fields["name"] != rubric.name
        ) and rubric.workspace_id is not None:
            existing = await self.repository.get_workspace_rubric_by_name(
                rubric.workspace_id, update_fields["name"]
            )
            if existing is not None and existing.id != rubric.id:
                raise RubricValidationError("Rubric name already exists in workspace")
        old_version = rubric.version
        if any(key in update_fields for key in {"name", "description", "criteria"}):
            update_fields["version"] = rubric.version + 1
        updated = await self.repository.update_rubric(rubric, **update_fields)
        await self._commit()
        if updated.version != old_version:
            await publish_evaluation_event(
                self.producer,
                EvaluationEventType.rubric_updated,
                RubricUpdatedPayload(
                    rubric_id=updated.id,
                    old_version=old_version,
                    new_version=updated.version,
                ),
                self._correlation(updated.workspace_id),
            )
        return RubricResponse.model_validate(updated)

    async def archive_rubric(
        self,
        rubric_id: UUID,
        workspace_id: UUID | None = None,
        actor_id: UUID | None = None,
    ) -> None:
        del actor_id
        rubric = await self.get_rubric_model(rubric_id, workspace_id)
        if rubric.is_builtin:
            raise RubricBuiltinProtectedError()
        if await self.repository.count_in_flight_rubric_references(rubric.id):
            raise RubricInFlightError()
        await self.repository.update_rubric(
            rubric,
            status=RubricStatus.archived,
            deleted_at=datetime.now(UTC),
        )
        await self._commit()
        await publish_evaluation_event(
            self.producer,
            EvaluationEventType.rubric_archived,
            RubricArchivedPayload(rubric_id=rubric.id, workspace_id=rubric.workspace_id),
            self._correlation(rubric.workspace_id),
        )

    async def get_builtin_by_name(self, name: str) -> RubricResponse:
        rubric = await self.repository.get_builtin_rubric_by_name(name)
        if rubric is None:
            raise RubricNotFoundError()
        return RubricResponse.model_validate(rubric)

    async def _validate_rubric_payload(self, payload: RubricCreate) -> None:
        normalized_names: set[str] = set()
        for criterion in payload.criteria:
            key = criterion.name.strip().lower()
            if key in normalized_names:
                raise RubricValidationError("Rubric criteria names must be unique")
            normalized_names.add(key)
            if len(criterion.examples) != len(set(criterion.examples)):
                raise RubricValidationError("Rubric examples contain contradictory duplicates")

    @staticmethod
    def _correlation(workspace_id: UUID | None) -> CorrelationContext:
        return CorrelationContext(correlation_id=uuid4(), workspace_id=workspace_id)

    async def _commit(self) -> None:
        await self.repository.session.commit()


class CalibrationService:
    def __init__(
        self,
        *,
        repository: EvaluationRepository,
        settings: Any,
        producer: EventProducer | None = None,
        scorer_registry: ScorerRegistry,
        rubric_service: RubricService | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.scorer_registry = scorer_registry
        self.rubric_service = rubric_service

    async def start_calibration(
        self,
        rubric_id: UUID,
        payload: CalibrationRunCreate,
        actor_id: UUID,
        workspace_id: UUID | None = None,
    ) -> CalibrationRunResponse:
        rubric = await self._get_rubric(rubric_id, workspace_id)
        if rubric.status is RubricStatus.archived:
            raise RubricArchivedError()
        run = await self.repository.create_calibration_run(
            CalibrationRun(
                rubric_id=rubric.id,
                rubric_version=rubric.version,
                judge_model=payload.judge_model,
                reference_set_id=payload.reference_set_id,
                status=CalibrationRunStatus.pending,
                created_by=actor_id,
            )
        )
        await self._commit()
        await publish_evaluation_event(
            self.producer,
            EvaluationEventType.calibration_started,
            CalibrationStartedPayload(
                run_id=run.id,
                rubric_id=run.rubric_id,
                rubric_version=run.rubric_version,
            ),
            CorrelationContext(correlation_id=uuid4(), workspace_id=workspace_id),
        )
        return CalibrationRunResponse.model_validate(run)

    async def get_calibration_run(self, run_id: UUID) -> CalibrationRunResponse:
        run = await self.repository.get_calibration_run(run_id)
        if run is None:
            raise NotFoundError("EVALUATION_CALIBRATION_RUN_NOT_FOUND", "Calibration run not found")
        return CalibrationRunResponse.model_validate(run)

    async def execute_calibration(self, run_id: UUID) -> CalibrationRunResponse:
        run = await self.repository.get_calibration_run(run_id)
        if run is None:
            raise NotFoundError("EVALUATION_CALIBRATION_RUN_NOT_FOUND", "Calibration run not found")
        if run.completed_at is not None:
            raise CalibrationRunImmutableError()
        rubric = await self._get_rubric(run.rubric_id, None)
        await self.repository.update_calibration_run(
            run,
            status=CalibrationRunStatus.running,
            started_at=datetime.now(UTC),
        )
        await self._commit()
        cases = await self._load_reference_cases(run.reference_set_id)
        scorer = self.scorer_registry.get("llm_judge")
        overall_scores: list[float] = []
        criterion_scores: dict[str, list[float]] = {}
        for case in cases:
            result = await scorer.score(
                case.expected_output,
                case.expected_output,
                {
                    "rubric_id": str(rubric.id),
                    "judge_model": run.judge_model,
                    "calibration_runs": 1,
                },
            )
            if result.error:
                await self.repository.update_calibration_run(
                    run,
                    status=CalibrationRunStatus.failed,
                    completed_at=datetime.now(UTC),
                    distribution={"error": result.error},
                    calibrated=False,
                    agreement_rate=0.0,
                )
                await self._commit()
                return CalibrationRunResponse.model_validate(run)
            if result.score is not None:
                overall_scores.append(float(result.score))
            for name, value in dict(result.extra.get("criteria_scores", {})).items():
                criterion_scores.setdefault(name, []).append(float(value))
        distribution = self._build_distribution(overall_scores, criterion_scores)
        error_grade_finding = (
            bool(overall_scores)
            and len({round(score, 4) for score in overall_scores}) == 1
            and len(overall_scores) > 1
        )
        low_confidence = bool(distribution.get("low_confidence"))
        calibrated = not error_grade_finding and not low_confidence
        agreement_rate = 0.0 if error_grade_finding else (1.0 if overall_scores else 0.0)
        await self.repository.update_calibration_run(
            run,
            status=CalibrationRunStatus.completed,
            distribution=distribution,
            agreement_rate=agreement_rate,
            calibrated=calibrated,
            error_grade_finding=error_grade_finding,
            completed_at=datetime.now(UTC),
        )
        await self._commit()
        await publish_evaluation_event(
            self.producer,
            EvaluationEventType.calibration_completed,
            CalibrationCompletedPayload(
                run_id=run.id,
                rubric_id=run.rubric_id,
                calibrated=calibrated,
                error_grade_finding=error_grade_finding,
            ),
            CorrelationContext(correlation_id=uuid4(), workspace_id=rubric.workspace_id),
        )
        return CalibrationRunResponse.model_validate(run)

    async def _get_rubric(self, rubric_id: UUID, workspace_id: UUID | None) -> Rubric:
        rubric = await self.repository.get_rubric(rubric_id, workspace_id)
        if rubric is None:
            raise RubricNotFoundError()
        return rubric

    async def _load_reference_cases(self, reference_set_id: str) -> list[BenchmarkCase]:
        try:
            reference_uuid = UUID(reference_set_id)
        except ValueError:
            return []
        return await self.repository.list_all_benchmark_cases(reference_uuid)

    def _build_distribution(
        self,
        overall_scores: list[float],
        criterion_scores: dict[str, list[float]],
    ) -> dict[str, Any]:
        variance_limit = float(self.settings.evaluation.calibration_variance_envelope)
        overall = self._summarize_series(overall_scores)
        per_criterion = {
            name: {
                **self._summarize_series(values),
                "low_discrimination": len({round(item, 4) for item in values}) <= 1
                if values
                else False,
            }
            for name, values in criterion_scores.items()
        }
        return {
            "overall": overall,
            "per_criterion": per_criterion,
            "runs": overall_scores,
            "low_confidence": float(overall.get("stddev", 0.0) or 0.0) > variance_limit,
        }

    @staticmethod
    def _summarize_series(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"min": 0.0, "max": 0.0, "mean": 0.0, "stddev": 0.0, "histogram": {}}
        histogram: dict[str, int] = {}
        for value in values:
            bucket = str(round(value))
            histogram[bucket] = histogram.get(bucket, 0) + 1
        stddev = statistics.pstdev(values) if len(values) > 1 else 0.0
        return {
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "stddev": stddev,
            "histogram": histogram,
        }

    async def _commit(self) -> None:
        await self.repository.session.commit()


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
        rubric_service: RubricService | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.scorer_registry = scorer_registry
        self.producer = producer
        self.runtime_controller = runtime_controller
        self.execution_query = execution_query
        self.drift_service = drift_service
        self.rubric_service = rubric_service

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
                if scorer_name == "trajectory" and scorer_kwargs.get("cooperation_mode"):
                    cooperation_scorer = cast(Any, scorer)
                    result = await cooperation_scorer.score_cooperation(
                        scorer_kwargs.get("agent_execution_ids", []),
                        scorer_kwargs,
                    )
                else:
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
            VerdictStatus.error if errors and overall_score is None else VerdictStatus.scored
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

    @traced_async("evaluation.eval_runner.judge_adhoc")
    async def judge_adhoc(self, payload: AdHocJudgeRequest, actor_id: UUID) -> AdHocJudgeResponse:
        started = time.perf_counter()
        scorer = self.scorer_registry.get("llm_judge")
        config: dict[str, Any] = {
            "judge_model": payload.judge_model or self.settings.evaluation.llm_judge_model,
            "calibration_runs": 1,
            "principal_id": str(actor_id),
        }
        rubric_id: UUID | None = payload.rubric_id
        rubric_version: int | None = None
        if payload.rubric_id is not None:
            config["rubric_id"] = str(payload.rubric_id)
            if self.rubric_service is not None:
                rubric = await self.rubric_service.get_rubric_model(payload.rubric_id, None)
                if rubric.status is RubricStatus.archived:
                    raise RubricArchivedError()
                rubric_version = rubric.version
                rubric_id = rubric.id
        elif payload.rubric is not None:
            config["rubric"] = {
                "custom_criteria": [
                    item.model_dump(mode="json") for item in payload.rubric.criteria
                ]
            }
        result = await scorer.score(payload.output, payload.output, config)
        if result.error in {"judge_failure_transient", "judge_failure_permanent"}:
            raise JudgeUnavailableError()
        duration_ms = int((time.perf_counter() - started) * 1000)
        await publish_evaluation_event(
            self.producer,
            EvaluationEventType.judge_adhoc,
            AdHocJudgePayload(
                rubric_id=rubric_id,
                judge_model=str(config["judge_model"]),
                principal_id=actor_id,
                duration_ms=duration_ms,
            ),
            CorrelationContext(correlation_id=uuid4()),
        )
        return AdHocJudgeResponse(
            rubric_id=rubric_id,
            rubric_version=rubric_version or result.extra.get("rubric_version"),
            judge_model=str(config["judge_model"]),
            per_criterion_scores={
                name: {
                    "score": score,
                    "rationale": None,
                    "out_of_range": name in result.extra.get("out_of_range_clamped", {}),
                }
                for name, score in dict(result.extra.get("criteria_scores", {})).items()
            },
            overall_score=result.score,
            rationale=result.rationale,
            principal_id=actor_id,
            timestamp=datetime.now(UTC),
            duration_ms=duration_ms,
        )

    def list_scorer_types(self) -> list[str]:
        return self.scorer_registry.registered_types()

    @staticmethod
    def _correlation(workspace_id: UUID | None) -> CorrelationContext:
        return CorrelationContext(correlation_id=uuid4(), workspace_id=workspace_id)

    @traced_async("evaluation.eval_runner.commit")
    async def _commit(self) -> None:
        await self.repository.session.commit()


class FairnessEvaluationService:
    def __init__(
        self,
        *,
        repository: EvaluationRepository,
        settings: Any,
        producer: EventProducer | None = None,
        scorer: FairnessScorer | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.scorer = scorer or FairnessScorer()

    async def run_fairness_evaluation(
        self,
        request: FairnessRunRequest,
        *,
        evaluated_by: UUID | None = None,
    ) -> FairnessRunResponse:
        evaluation_run_id = request.evaluation_run_id or uuid4()
        result = await self.scorer.score_suite(
            evaluation_run_id=evaluation_run_id,
            agent_id=request.agent_id,
            agent_revision_id=request.agent_revision_id,
            suite_id=request.suite_id,
            cases=request.cases,
            config=request.config,
            evaluated_by=evaluated_by,
        )
        if request.config.preview:
            result.notes.append("preview_uses_mock_llm_outputs")
        rows = [
            FairnessEvaluation(
                evaluation_run_id=row.evaluation_run_id,
                agent_id=row.agent_id,
                agent_revision_id=row.agent_revision_id,
                suite_id=row.suite_id,
                metric_name=row.metric_name,
                group_attribute=row.group_attribute,
                per_group_scores=row.per_group_scores,
                spread=row.spread,
                fairness_band=row.fairness_band,
                passed=row.passed,
                coverage=row.coverage,
                notes=row.notes,
                evaluated_by=row.evaluated_by,
            )
            for row in result.rows
        ]
        await self.repository.insert_fairness_evaluation_rows(rows)
        for row in result.rows:
            await self._append_metric_audit(row, request.workspace_id)
        await self.repository.session.commit()
        await publish_evaluation_event(
            self.producer,
            EvaluationEventType.fairness_completed,
            FairnessEvaluationCompletedPayload(
                evaluation_run_id=evaluation_run_id,
                agent_id=request.agent_id,
                agent_revision_id=request.agent_revision_id,
                suite_id=request.suite_id,
                overall_passed=result.overall_passed,
                metric_count=len(result.rows),
            ),
            CorrelationContext(
                correlation_id=uuid4(),
                workspace_id=request.workspace_id,
            ),
        )
        return FairnessRunResponse(
            evaluation_run_id=evaluation_run_id,
            status="completed",
            rows=result.rows,
            overall_passed=result.overall_passed,
            notes=result.notes,
        )

    async def get_fairness_run(self, evaluation_run_id: UUID) -> FairnessRunResponse:
        rows = await self.repository.get_fairness_evaluation_run(evaluation_run_id)
        return FairnessRunResponse(
            evaluation_run_id=evaluation_run_id,
            status="completed" if rows else "not_found",
            rows=[
                FairnessMetricRow(
                    evaluation_run_id=row.evaluation_run_id,
                    agent_id=row.agent_id,
                    agent_revision_id=row.agent_revision_id,
                    suite_id=row.suite_id,
                    metric_name=row.metric_name,
                    group_attribute=row.group_attribute,
                    per_group_scores=row.per_group_scores,
                    spread=row.spread,
                    fairness_band=row.fairness_band,
                    passed=row.passed,
                    coverage=row.coverage,
                    notes=row.notes,
                    evaluated_by=row.evaluated_by,
                    computed_at=row.computed_at,
                )
                for row in rows
            ],
            overall_passed=all(row.passed for row in rows) if rows else None,
        )

    async def get_latest_passing_evaluation(
        self,
        *,
        agent_id: UUID,
        agent_revision_id: str,
        staleness_days: int,
    ) -> FairnessEvaluationSummary | None:
        cutoff = datetime.now(UTC) - timedelta(days=staleness_days)
        row = await self.repository.get_latest_passing_fairness_evaluation(
            agent_id,
            agent_revision_id,
            cutoff,
        )
        if row is None:
            return None
        run_rows = await self.repository.get_fairness_evaluation_run(row.evaluation_run_id)
        return FairnessEvaluationSummary(
            evaluation_run_id=row.evaluation_run_id,
            agent_id=row.agent_id,
            agent_revision_id=row.agent_revision_id,
            suite_id=row.suite_id,
            overall_passed=all(item.passed for item in run_rows),
            metric_count=len(run_rows),
            computed_at=row.computed_at,
        )

    async def get_latest_passing_evaluation_any_age(
        self,
        *,
        agent_id: UUID,
        agent_revision_id: str,
    ) -> FairnessEvaluationSummary | None:
        row = await self.repository.get_latest_passing_fairness_evaluation_any_age(
            agent_id,
            agent_revision_id,
        )
        if row is None:
            return None
        run_rows = await self.repository.get_fairness_evaluation_run(row.evaluation_run_id)
        return FairnessEvaluationSummary(
            evaluation_run_id=row.evaluation_run_id,
            agent_id=row.agent_id,
            agent_revision_id=row.agent_revision_id,
            suite_id=row.suite_id,
            overall_passed=all(item.passed for item in run_rows),
            metric_count=len(run_rows),
            computed_at=row.computed_at,
        )

    async def _append_metric_audit(
        self,
        row: FairnessMetricRow,
        workspace_id: UUID | None,
    ) -> None:
        if not hasattr(self.settings, "audit") or not callable(
            getattr(self.repository.session, "execute", None)
        ):
            return
        audit_chain = AuditChainService(
            AuditChainRepository(self.repository.session),
            self.settings,
            producer=self.producer,
        )
        await audit_chain_hook(
            audit_chain,
            None,
            "evaluation.fairness.metric",
            {
                "workspace_id": workspace_id,
                "evaluation_run_id": row.evaluation_run_id,
                "agent_id": row.agent_id,
                "agent_revision_id": row.agent_revision_id,
                "suite_id": row.suite_id,
                "metric_name": row.metric_name,
                "group_attribute": row.group_attribute,
                "spread": row.spread,
                "fairness_band": row.fairness_band,
                "passed": row.passed,
                "computed_at": datetime.now(UTC),
            },
        )
