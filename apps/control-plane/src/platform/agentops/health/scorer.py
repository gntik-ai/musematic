from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.agentops.events import AgentOpsEventPublisher, AgentOpsEventType
from platform.agentops.health.dimensions import DimensionResult, HealthDimensionProvider
from platform.agentops.models import AgentHealthConfig, AgentHealthScore
from platform.agentops.repository import AgentOpsRepository
from typing import Any
from uuid import UUID

HEALTH_DIMENSIONS = (
    "uptime",
    "quality",
    "safety",
    "cost_efficiency",
    "satisfaction",
)


@dataclass(slots=True)
class AgentHealthTarget:
    agent_fqn: str
    workspace_id: UUID
    revision_id: UUID


class HealthScorer:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        dimensions: HealthDimensionProvider,
        event_publisher: AgentOpsEventPublisher,
        redis_client: Any | None = None,
        critical_interval_threshold: int = 5,
    ) -> None:
        self.repository = repository
        self.dimensions = dimensions
        self.event_publisher = event_publisher
        self.redis_client = redis_client
        self.critical_interval_threshold = critical_interval_threshold

    async def compute(
        self,
        *,
        agent_fqn: str,
        workspace_id: UUID,
        revision_id: UUID,
        config: AgentHealthConfig | None = None,
        observation_end: datetime | None = None,
    ) -> AgentHealthScore:
        resolved_config = config or await self._get_or_create_config(workspace_id)
        previous = await self.repository.get_current_health_score(agent_fqn, workspace_id)

        observation_end = observation_end or datetime.now(UTC)
        observation_start = observation_end - timedelta(days=resolved_config.rolling_window_days)

        results = await self._collect_dimension_results(
            agent_fqn=agent_fqn,
            workspace_id=workspace_id,
            config=resolved_config,
        )
        score = AgentHealthScore(
            workspace_id=workspace_id,
            agent_fqn=agent_fqn,
            revision_id=revision_id,
            composite_score=_decimal(self._composite_score(results, resolved_config)),
            uptime_score=_optional_decimal(results["uptime"].score),
            quality_score=_optional_decimal(results["quality"].score),
            safety_score=_optional_decimal(results["safety"].score),
            cost_efficiency_score=_optional_decimal(results["cost_efficiency"].score),
            satisfaction_score=_optional_decimal(results["satisfaction"].score),
            weights_snapshot=self._effective_weights(results, resolved_config),
            missing_dimensions=[
                name for name, result in results.items() if result.score is None
            ],
            sample_counts={name: result.sample_count for name, result in results.items()},
            computed_at=observation_end,
            observation_window_start=observation_start,
            observation_window_end=observation_end,
            below_warning=False,
            below_critical=False,
            insufficient_data=all(result.score is None for result in results.values()),
        )
        if not score.insufficient_data:
            composite_value = float(score.composite_score)
            score.below_warning = composite_value < float(resolved_config.warning_threshold)
            score.below_critical = composite_value < float(resolved_config.critical_threshold)

        persisted = await self.repository.upsert_health_score(score)
        await self._publish_threshold_event(
            previous=previous,
            current=persisted,
            config=resolved_config,
        )
        await self._track_critical_intervals(
            current=persisted,
            config=resolved_config,
        )
        return persisted

    async def _get_or_create_config(self, workspace_id: UUID) -> AgentHealthConfig:
        config = await self.repository.get_health_config(workspace_id)
        if config is not None:
            return config
        return await self.repository.upsert_health_config(
            AgentHealthConfig(workspace_id=workspace_id)
        )

    async def _collect_dimension_results(
        self,
        *,
        agent_fqn: str,
        workspace_id: UUID,
        config: AgentHealthConfig,
    ) -> dict[str, DimensionResult]:
        uptime, quality, safety, cost_efficiency, satisfaction = await asyncio.gather(
            self.dimensions.uptime_score(
                agent_fqn=agent_fqn,
                minimum_sample_size=config.min_sample_size,
            ),
            self.dimensions.quality_score(
                agent_fqn=agent_fqn,
                workspace_id=workspace_id,
                window_days=config.rolling_window_days,
                minimum_sample_size=config.min_sample_size,
            ),
            self.dimensions.safety_score(
                agent_fqn=agent_fqn,
                workspace_id=workspace_id,
                window_days=config.rolling_window_days,
                minimum_sample_size=config.min_sample_size,
            ),
            self.dimensions.cost_efficiency_score(
                agent_fqn=agent_fqn,
                workspace_id=workspace_id,
                window_days=config.rolling_window_days,
                minimum_sample_size=config.min_sample_size,
            ),
            self.dimensions.satisfaction_score(
                agent_fqn=agent_fqn,
                workspace_id=workspace_id,
                window_days=config.rolling_window_days,
                minimum_sample_size=config.min_sample_size,
            ),
        )
        return {
            "uptime": uptime,
            "quality": quality,
            "safety": safety,
            "cost_efficiency": cost_efficiency,
            "satisfaction": satisfaction,
        }

    def _composite_score(
        self,
        results: dict[str, DimensionResult],
        config: AgentHealthConfig,
    ) -> float:
        effective_weights = self._effective_weights(results, config)
        weighted_total = 0.0
        for name, result in results.items():
            if result.score is None:
                continue
            weighted_total += result.score * (effective_weights[name] / 100.0)
        return round(weighted_total, 2)

    def _effective_weights(
        self,
        results: dict[str, DimensionResult],
        config: AgentHealthConfig,
    ) -> dict[str, float]:
        base_weights = _config_weights(config)
        available = [name for name, result in results.items() if result.score is not None]
        available_total = sum(base_weights[name] for name in available)
        if not available or available_total <= 0.0:
            return dict.fromkeys(HEALTH_DIMENSIONS, 0.0)
        return {
            name: (
                round((base_weights[name] / available_total) * 100.0, 4)
                if name in available
                else 0.0
            )
            for name in HEALTH_DIMENSIONS
        }

    async def _publish_threshold_event(
        self,
        *,
        previous: AgentHealthScore | None,
        current: AgentHealthScore,
        config: AgentHealthConfig,
    ) -> None:
        if current.insufficient_data:
            return

        previous_warning = bool(previous and previous.below_warning)
        previous_critical = bool(previous and previous.below_critical)
        event_type: AgentOpsEventType | None = None

        if current.below_critical and not previous_critical:
            event_type = AgentOpsEventType.health_critical
        elif current.below_warning and not previous_warning:
            event_type = AgentOpsEventType.health_warning

        if event_type is None:
            return

        await self.event_publisher.publish(
            event_type=event_type.value,
            agent_fqn=current.agent_fqn,
            workspace_id=current.workspace_id,
            payload={
                "composite_score": float(current.composite_score),
                "warning_threshold": float(config.warning_threshold),
                "critical_threshold": float(config.critical_threshold),
                "missing_dimensions": list(current.missing_dimensions),
                "sample_counts": dict(current.sample_counts),
                "computed_at": current.computed_at.isoformat(),
            },
        )

    async def _track_critical_intervals(
        self,
        *,
        current: AgentHealthScore,
        config: AgentHealthConfig,
    ) -> None:
        if self.redis_client is None:
            return
        key = _critical_intervals_key(current.workspace_id, current.agent_fqn)
        if current.insufficient_data or not current.below_critical:
            await self.redis_client.delete(key)
            return

        raw_count = await self.redis_client.get(key)
        count = _decode_counter(raw_count)
        next_count = count + 1
        ttl_seconds = max(1, config.scoring_interval_minutes * 120)
        await self.redis_client.set(
            key,
            str(next_count).encode(),
            ttl=ttl_seconds,
        )
        if (
            next_count < self.critical_interval_threshold
            or count >= self.critical_interval_threshold
        ):
            return
        await self.event_publisher.publish(
            event_type=AgentOpsEventType.retirement_trigger.value,
            agent_fqn=current.agent_fqn,
            workspace_id=current.workspace_id,
            payload={
                "revision_id": str(current.revision_id),
                "composite_score": float(current.composite_score),
                "critical_intervals": next_count,
                "required_intervals": self.critical_interval_threshold,
            },
        )


def _config_weights(config: AgentHealthConfig) -> dict[str, float]:
    return {
        "uptime": float(config.weight_uptime),
        "quality": float(config.weight_quality),
        "safety": float(config.weight_safety),
        "cost_efficiency": float(config.weight_cost_efficiency),
        "satisfaction": float(config.weight_satisfaction),
    }


def _decimal(value: float) -> Decimal:
    return Decimal(f"{value:.2f}")


def _optional_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value)


def _critical_intervals_key(workspace_id: UUID, agent_fqn: str) -> str:
    return f"agentops:critical_intervals:{workspace_id}:{agent_fqn}"


def _decode_counter(value: bytes | None) -> int:
    if value is None:
        return 0
    try:
        return int(value.decode())
    except (UnicodeDecodeError, ValueError):
        return 0
