from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from platform.agentops.events import AgentOpsEventType, GovernanceEventPublisher
from platform.agentops.exceptions import InsufficientSampleError
from platform.agentops.models import BehavioralRegressionAlert, RegressionAlertStatus
from platform.agentops.regression.statistics import ComparisonResult, StatisticalComparator
from platform.agentops.repository import AgentOpsRepository
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RegressionDimensionConfig:
    column: str
    higher_is_better: bool


REGRESSION_DIMENSIONS = {
    "quality": RegressionDimensionConfig(column="quality_score", higher_is_better=True),
    "latency": RegressionDimensionConfig(column="execution_duration_ms", higher_is_better=False),
    "cost": RegressionDimensionConfig(column="cost_usd", higher_is_better=False),
    "safety": RegressionDimensionConfig(column="toFloat64(safety_passed)", higher_is_better=True),
}


class RegressionDetector:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        governance_publisher: GovernanceEventPublisher | None,
        clickhouse_client: Any | None,
        alpha: float = 0.05,
        minimum_sample_size: int = 30,
    ) -> None:
        self.repository = repository
        self.governance_publisher = governance_publisher
        self.clickhouse_client = clickhouse_client
        self.alpha = alpha
        self.minimum_sample_size = minimum_sample_size

    async def detect(
        self,
        *,
        new_revision_id: UUID,
        baseline_revision_id: UUID,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> BehavioralRegressionAlert | None:
        insufficient: tuple[str, int] | None = None
        regressed_dimensions: list[str] = []
        comparisons: dict[str, ComparisonResult] = {}
        sample_sizes: dict[str, int] = {}

        for dimension, config in REGRESSION_DIMENSIONS.items():
            baseline_samples = await self.fetch_samples(
                revision_id=baseline_revision_id,
                agent_fqn=agent_fqn,
                workspace_id=workspace_id,
                dimension=dimension,
                column=config.column,
            )
            new_samples = await self.fetch_samples(
                revision_id=new_revision_id,
                agent_fqn=agent_fqn,
                workspace_id=workspace_id,
                dimension=dimension,
                column=config.column,
            )
            baseline_count = len(baseline_samples)
            new_count = len(new_samples)
            if baseline_count < self.minimum_sample_size or new_count < self.minimum_sample_size:
                if insufficient is None:
                    insufficient = (dimension, min(baseline_count, new_count))
                continue

            comparison = StatisticalComparator.compare(
                baseline_samples,
                new_samples,
                alpha=self.alpha,
            )
            sample_sizes[dimension] = min(baseline_count, new_count)
            if comparison.significant and _is_regression(
                dimension=dimension,
                baseline_samples=baseline_samples,
                new_samples=new_samples,
                higher_is_better=config.higher_is_better,
            ):
                regressed_dimensions.append(dimension)
                comparisons[dimension] = comparison

        if not sample_sizes and insufficient is not None:
            dimension, actual = insufficient
            raise InsufficientSampleError(dimension, self.minimum_sample_size, actual)

        if not regressed_dimensions:
            return None

        primary_dimension = min(
            regressed_dimensions,
            key=lambda dimension: comparisons[dimension].p_value,
        )
        primary = comparisons[primary_dimension]
        alert = await self.repository.create_regression_alert(
            BehavioralRegressionAlert(
                agent_fqn=agent_fqn,
                workspace_id=workspace_id,
                new_revision_id=new_revision_id,
                baseline_revision_id=baseline_revision_id,
                status=RegressionAlertStatus.active,
                regressed_dimensions=regressed_dimensions,
                statistical_test=primary.test_type,
                p_value=primary.p_value,
                effect_size=primary.effect_size,
                significance_threshold=self.alpha,
                sample_sizes=sample_sizes,
                detected_at=datetime.now(UTC),
                triggered_rollback=False,
            )
        )
        if self.governance_publisher is not None:
            await self.governance_publisher.record(
                AgentOpsEventType.regression_detected.value,
                agent_fqn,
                workspace_id,
                payload={
                    "revision_id": str(new_revision_id),
                    "baseline_revision_id": str(baseline_revision_id),
                    "regressed_dimensions": regressed_dimensions,
                    "p_value": primary.p_value,
                    "effect_size": primary.effect_size,
                    "statistical_test": primary.test_type,
                },
                revision_id=new_revision_id,
            )
        return alert

    async def fetch_samples(
        self,
        *,
        revision_id: UUID,
        agent_fqn: str,
        workspace_id: UUID,
        dimension: str,
        column: str,
    ) -> list[float]:
        del dimension
        if self.clickhouse_client is None:
            return []
        rows = await self.clickhouse_client.execute_query(
            f"""
            SELECT {column} AS metric_value
            FROM agentops_behavioral_versions
            WHERE workspace_id = {{workspace_id:UUID}}
              AND agent_fqn = %(agent_fqn)s
              AND revision_id = {{revision_id:UUID}}
              AND {column} IS NOT NULL
            ORDER BY measured_at ASC
            """,
            {
                "workspace_id": workspace_id,
                "agent_fqn": agent_fqn,
                "revision_id": revision_id,
            },
        )
        return [float(row["metric_value"]) for row in rows if row.get("metric_value") is not None]


def _is_regression(
    *,
    dimension: str,
    baseline_samples: list[float],
    new_samples: list[float],
    higher_is_better: bool,
) -> bool:
    del dimension
    baseline_mean = sum(baseline_samples) / len(baseline_samples)
    new_mean = sum(new_samples) / len(new_samples)
    if higher_is_better:
        return new_mean < baseline_mean
    return new_mean > baseline_mean
