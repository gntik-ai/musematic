from __future__ import annotations

import statistics
from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError
from platform.common.tracing import traced_async
from platform.evaluation.events import (
    EvaluationEventType,
    RobustnessCompletedPayload,
    publish_evaluation_event,
)
from platform.evaluation.models import RobustnessTestRun, RunStatus
from platform.evaluation.repository import EvaluationRepository
from platform.evaluation.schemas import RobustnessRunCreate, RobustnessTestRunResponse
from platform.evaluation.service import EvalRunnerService
from uuid import UUID, uuid4


class RobustnessTestService:
    def __init__(
        self,
        *,
        repository: EvaluationRepository,
        eval_runner_service: EvalRunnerService,
        producer: EventProducer | None = None,
    ) -> None:
        self.repository = repository
        self.eval_runner_service = eval_runner_service
        self.producer = producer

    @traced_async("evaluation.robustness.start_run")
    async def start_run(self, payload: RobustnessRunCreate) -> RobustnessTestRunResponse:
        run = await self.repository.create_robustness_run(
            RobustnessTestRun(
                workspace_id=payload.workspace_id,
                eval_set_id=payload.eval_set_id,
                benchmark_case_id=payload.benchmark_case_id,
                agent_fqn=payload.agent_fqn,
                trial_count=payload.trial_count,
                variance_threshold=payload.variance_threshold,
                status=RunStatus.pending,
            )
        )
        await self._commit()
        return RobustnessTestRunResponse.model_validate(run)

    @traced_async("evaluation.robustness.execute_run")
    async def execute_run(self, run_id: UUID) -> RobustnessTestRunResponse:
        run = await self.repository.get_robustness_run(run_id)
        if run is None:
            raise NotFoundError("ROBUSTNESS_RUN_NOT_FOUND", "Robustness run not found")
        await self.repository.update_robustness_run(run, status=RunStatus.running)
        await self._commit()
        scores: list[float] = []
        trial_ids: list[str] = []
        for _ in range(run.trial_count):
            response = await self.eval_runner_service.run_eval_set(
                eval_set_id=run.eval_set_id,
                workspace_id=run.workspace_id,
                agent_fqn=run.agent_fqn,
                benchmark_case_id=run.benchmark_case_id,
            )
            trial_ids.append(str(response.id))
            if response.aggregate_score is not None:
                scores.append(response.aggregate_score)
            await self.repository.update_robustness_run(
                run,
                completed_trials=len(trial_ids),
                trial_run_ids=trial_ids,
            )
            await self._commit()
        distribution = self._distribution(scores)
        score_stddev = float(distribution["stddev"]) if distribution is not None else 0.0
        is_unreliable = score_stddev > run.variance_threshold
        await self.repository.update_robustness_run(
            run,
            status=RunStatus.completed,
            completed_trials=len(trial_ids),
            trial_run_ids=trial_ids,
            distribution=distribution,
            is_unreliable=is_unreliable,
            updated_at=datetime.now(UTC),
        )
        await self._commit()
        await publish_evaluation_event(
            self.producer,
            EvaluationEventType.robustness_completed,
            RobustnessCompletedPayload(
                robustness_run_id=run.id,
                workspace_id=run.workspace_id,
                is_unreliable=is_unreliable,
                distribution=distribution,
            ),
            CorrelationContext(correlation_id=uuid4(), workspace_id=run.workspace_id),
        )
        return RobustnessTestRunResponse.model_validate(run)

    @traced_async("evaluation.robustness.get_run")
    async def get_run(self, run_id: UUID) -> RobustnessTestRunResponse:
        run = await self.repository.get_robustness_run(run_id)
        if run is None:
            raise NotFoundError("ROBUSTNESS_RUN_NOT_FOUND", "Robustness run not found")
        return RobustnessTestRunResponse.model_validate(run)

    @staticmethod
    def _distribution(scores: list[float]) -> dict[str, float] | None:
        if not scores:
            return None
        ordered = sorted(scores)
        if len(ordered) == 1:
            only = ordered[0]
            return {
                "mean": only,
                "stddev": 0.0,
                "p5": only,
                "p25": only,
                "p50": only,
                "p75": only,
                "p95": only,
                "min": only,
                "max": only,
            }
        quantiles = statistics.quantiles(ordered, n=20, method="inclusive")
        return {
            "mean": statistics.mean(ordered),
            "stddev": statistics.stdev(ordered),
            "p5": quantiles[0],
            "p25": quantiles[4],
            "p50": statistics.median(ordered),
            "p75": quantiles[14],
            "p95": quantiles[18],
            "min": ordered[0],
            "max": ordered[-1],
        }

    @traced_async("evaluation.robustness.commit")
    async def _commit(self) -> None:
        await self.repository.session.commit()
