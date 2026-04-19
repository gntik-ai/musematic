from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import sqrt
from platform.common.events.envelope import CorrelationContext
from platform.context_engineering.events import (
    ContextEngineeringEventType,
    CorrelationComputedPayload,
    CorrelationStrongNegativePayload,
    publish_context_engineering_event,
)
from platform.context_engineering.models import (
    ContextAssemblyRecord,
    CorrelationClassification,
    CorrelationResult,
)
from platform.context_engineering.repository import ContextEngineeringRepository
from platform.context_engineering.schemas import (
    CorrelationFleetResponse,
    CorrelationResultResponse,
)
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CorrelationService:
    def __init__(
        self,
        *,
        repository: ContextEngineeringRepository,
        event_producer: Any | None,
        min_data_points: int,
    ) -> None:
        self.repository = repository
        self.event_producer = event_producer
        self.min_data_points = min_data_points

    async def compute_for_agent(
        self,
        workspace_id: UUID,
        agent_fqn: str,
        *,
        window_days: int,
    ) -> list[CorrelationResultResponse]:
        end = _utcnow()
        start = end - timedelta(days=window_days)
        records = await self._load_records(workspace_id, agent_fqn, start)
        metrics = _derive_metrics(records)
        results: list[CorrelationResultResponse] = []
        for dimension, values in metrics["dimensions"].items():
            for performance_metric, perf_values in metrics["performance"].items():
                coefficient: float | None
                classification: CorrelationClassification
                if min(len(values), len(perf_values)) < self.min_data_points:
                    coefficient = None
                    classification = CorrelationClassification.inconclusive
                else:
                    coefficient = _pearson(values, perf_values)
                    classification = _classify(coefficient)
                stored = await self.repository.upsert_correlation_result(
                    CorrelationResult(
                        id=uuid4(),
                        workspace_id=workspace_id,
                        agent_fqn=agent_fqn,
                        dimension=dimension,
                        performance_metric=performance_metric,
                        window_start=start,
                        window_end=end,
                        coefficient=coefficient,
                        classification=classification,
                        data_point_count=min(len(values), len(perf_values)),
                        computed_at=end,
                    )
                )
                response = CorrelationResultResponse.model_validate(stored)
                results.append(response)
                await publish_context_engineering_event(
                    self.event_producer,
                    ContextEngineeringEventType.correlation_computed,
                    CorrelationComputedPayload(
                        result_id=stored.id,
                        workspace_id=workspace_id,
                        agent_fqn=agent_fqn,
                        dimension=dimension,
                        performance_metric=performance_metric,
                        classification=classification.value,
                        data_point_count=stored.data_point_count,
                    ),
                    CorrelationContext(workspace_id=workspace_id, correlation_id=uuid4()),
                )
                if classification is CorrelationClassification.strong_negative:
                    await publish_context_engineering_event(
                        self.event_producer,
                        ContextEngineeringEventType.correlation_strong_negative,
                        CorrelationStrongNegativePayload(
                            result_id=stored.id,
                            workspace_id=workspace_id,
                            agent_fqn=agent_fqn,
                            dimension=dimension,
                            performance_metric=performance_metric,
                            classification=classification.value,
                            data_point_count=stored.data_point_count,
                            coefficient=coefficient,
                        ),
                        CorrelationContext(
                            workspace_id=workspace_id,
                            correlation_id=uuid4(),
                        ),
                    )
        return results

    async def get_latest(
        self,
        workspace_id: UUID,
        agent_fqn: str,
        *,
        window_days: int | None = None,
        classification: str | None = None,
    ) -> CorrelationFleetResponse:
        rows = await self.repository.get_latest_by_agent(
            workspace_id,
            agent_fqn,
            window_days=window_days,
        )
        if classification is not None:
            rows = [row for row in rows if str(row.classification) == classification]
        return CorrelationFleetResponse(
            items=[CorrelationResultResponse.model_validate(row) for row in rows],
            total=len(rows),
        )

    async def query_fleet(
        self,
        workspace_id: UUID,
        *,
        classification: str | None = None,
    ) -> CorrelationFleetResponse:
        rows = await self.repository.list_fleet_by_classification(
            workspace_id,
            classification=classification,
        )
        return CorrelationFleetResponse(
            items=[CorrelationResultResponse.model_validate(row) for row in rows],
            total=len(rows),
        )

    async def _load_records(
        self,
        workspace_id: UUID,
        agent_fqn: str,
        window_start: datetime,
    ) -> list[ContextAssemblyRecord]:
        result = await self.repository.session.execute(
            select(ContextAssemblyRecord)
            .where(
                ContextAssemblyRecord.workspace_id == workspace_id,
                ContextAssemblyRecord.agent_fqn == agent_fqn,
                ContextAssemblyRecord.created_at >= window_start,
            )
            .order_by(
                ContextAssemblyRecord.created_at.asc(),
                ContextAssemblyRecord.id.asc(),
            )
        )
        return list(result.scalars().all())


def _derive_metrics(
    records: list[ContextAssemblyRecord],
) -> dict[str, dict[str, list[float]]]:
    retrieval = [max(0.0, min(float(record.quality_score_post), 1.0)) for record in records]
    adherence = [
        max(0.0, min(float(record.quality_score_pre or record.quality_score_post), 1.0))
        for record in records
    ]
    coherence = [
        max(
            0.0,
            min(
                1.0
                - abs(record.token_count_post - record.token_count_pre)
                / max(record.token_count_pre or 1, 1),
                1.0,
            ),
        )
        for record in records
    ]
    quality = [max(0.0, min(float(record.quality_score_post), 1.0)) for record in records]
    return {
        "dimensions": {
            "retrieval_accuracy": retrieval,
            "instruction_adherence": adherence,
            "context_coherence": coherence,
        },
        "performance": {
            "quality_score": quality,
        },
    }


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = min(len(xs), len(ys))
    if n == 0:
        return 0.0
    xs = xs[:n]
    ys = ys[:n]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=False))
    denominator_x = sum((x - mean_x) ** 2 for x in xs)
    denominator_y = sum((y - mean_y) ** 2 for y in ys)
    denominator = sqrt(denominator_x * denominator_y)
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _classify(coefficient: float | None) -> CorrelationClassification:
    if coefficient is None:
        return CorrelationClassification.inconclusive
    if coefficient >= 0.7:
        return CorrelationClassification.strong_positive
    if coefficient >= 0.4:
        return CorrelationClassification.moderate_positive
    if coefficient <= -0.7:
        return CorrelationClassification.strong_negative
    if coefficient <= -0.4:
        return CorrelationClassification.moderate_negative
    return CorrelationClassification.weak
