from __future__ import annotations

import math
import statistics
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError, ValidationError
from platform.common.tracing import traced_async
from platform.evaluation.events import (
    AbExperimentCompletedPayload,
    EvaluationEventType,
    publish_evaluation_event,
)
from platform.evaluation.models import AbExperiment, ExperimentStatus, RunStatus
from platform.evaluation.repository import EvaluationRepository
from platform.evaluation.schemas import AbExperimentCreate, AbExperimentResponse
from uuid import UUID, uuid4


class AbExperimentService:
    def __init__(
        self,
        *,
        repository: EvaluationRepository,
        producer: EventProducer | None = None,
    ) -> None:
        self.repository = repository
        self.producer = producer

    @traced_async("evaluation.ab_experiment.start_experiment")
    async def start_experiment(self, payload: AbExperimentCreate) -> AbExperimentResponse:
        run_a = await self.repository.get_run(payload.run_a_id, payload.workspace_id)
        run_b = await self.repository.get_run(payload.run_b_id, payload.workspace_id)
        if run_a is None or run_b is None:
            raise NotFoundError("EVALUATION_RUN_NOT_FOUND", "Comparison runs not found")
        if run_a.status is not RunStatus.completed or run_b.status is not RunStatus.completed:
            raise ValidationError(
                "RUN_NOT_COMPLETED",
                "Both runs must be completed before comparison",
            )
        if run_a.eval_set_id != run_b.eval_set_id:
            raise ValidationError("MISMATCHED_EVAL_SET", "Runs must target the same evaluation set")
        experiment = await self.repository.create_ab_experiment(
            AbExperiment(
                workspace_id=payload.workspace_id,
                name=payload.name,
                run_a_id=payload.run_a_id,
                run_b_id=payload.run_b_id,
                status=ExperimentStatus.pending,
            )
        )
        await self._commit()
        return AbExperimentResponse.model_validate(experiment)

    @traced_async("evaluation.ab_experiment.run_experiment")
    async def run_experiment(self, experiment_id: UUID) -> AbExperimentResponse:
        experiment = await self.repository.get_ab_experiment(experiment_id)
        if experiment is None:
            raise NotFoundError("AB_EXPERIMENT_NOT_FOUND", "A/B experiment not found")
        scores_a = await self.repository.get_run_score_array(experiment.run_a_id)
        scores_b = await self.repository.get_run_score_array(experiment.run_b_id)
        p_value, effect_size, confidence_interval, winner = self._compare(scores_a, scores_b)
        diff = (
            statistics.mean(scores_a) - statistics.mean(scores_b)
            if scores_a and scores_b
            else 0.0
        )
        analysis_summary = self._build_summary(winner, p_value, effect_size, diff)
        await self.repository.update_ab_experiment(
            experiment,
            status=ExperimentStatus.completed,
            p_value=p_value,
            effect_size=effect_size,
            confidence_interval=confidence_interval,
            winner=winner,
            analysis_summary=analysis_summary,
        )
        await self._commit()
        await publish_evaluation_event(
            self.producer,
            EvaluationEventType.ab_experiment_completed,
            AbExperimentCompletedPayload(
                experiment_id=experiment.id,
                workspace_id=experiment.workspace_id,
                winner=winner,
                p_value=p_value,
                effect_size=effect_size,
            ),
            CorrelationContext(
                correlation_id=uuid4(),
                workspace_id=experiment.workspace_id,
            ),
        )
        return AbExperimentResponse.model_validate(experiment)

    @traced_async("evaluation.ab_experiment.get_experiment")
    async def get_experiment(self, experiment_id: UUID) -> AbExperimentResponse:
        experiment = await self.repository.get_ab_experiment(experiment_id)
        if experiment is None:
            raise NotFoundError("AB_EXPERIMENT_NOT_FOUND", "A/B experiment not found")
        return AbExperimentResponse.model_validate(experiment)

    @staticmethod
    def _compare(
        scores_a: list[float],
        scores_b: list[float],
    ) -> tuple[float | None, float | None, dict[str, float] | None, str]:
        if len(scores_a) < 2 or len(scores_b) < 2:
            return None, None, None, "inconclusive"
        mean_a = statistics.mean(scores_a)
        mean_b = statistics.mean(scores_b)
        variance_a = statistics.variance(scores_a)
        variance_b = statistics.variance(scores_b)
        se = math.sqrt((variance_a / len(scores_a)) + (variance_b / len(scores_b)))
        if se == 0:
            return 1.0, 0.0, {"lower": 0.0, "upper": 0.0, "alpha": 0.05}, "inconclusive"
        diff = mean_a - mean_b
        z_score = diff / se
        normal = statistics.NormalDist()
        p_value = 2 * (1 - normal.cdf(abs(z_score)))
        pooled = math.sqrt(
            (
                ((len(scores_a) - 1) * variance_a)
                + ((len(scores_b) - 1) * variance_b)
            )
            / max(1, len(scores_a) + len(scores_b) - 2)
        )
        effect_size = diff / pooled if pooled else 0.0
        margin = 1.96 * se
        confidence_interval = {"lower": diff - margin, "upper": diff + margin, "alpha": 0.05}
        if p_value < 0.05:
            winner = "a" if diff > 0 else "b"
        else:
            winner = "inconclusive"
        return p_value, effect_size, confidence_interval, winner

    @staticmethod
    def _build_summary(
        winner: str,
        p_value: float | None,
        effect_size: float | None,
        diff: float,
    ) -> str:
        if p_value is None:
            return "Insufficient verdict count for significance testing."
        if winner == "inconclusive":
            return f"No statistically significant winner (p={p_value:.3f}, diff={diff:.3f})."
        return (
            f"Variant {winner.upper()} outperforms the other run "
            f"(p={p_value:.3f}, effect={effect_size or 0.0:.3f})."
        )

    @traced_async("evaluation.ab_experiment.commit")
    async def _commit(self) -> None:
        await self.repository.session.commit()
