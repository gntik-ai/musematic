from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.agentops.models import ProficiencyAssessment, ProficiencyLevel
from platform.agentops.repository import AgentOpsRepository
from platform.agentops.schemas import (
    ProficiencyFleetResponse,
    ProficiencyHistoryResponse,
    ProficiencyResponse,
)
from platform.common.exceptions import NotFoundError
from platform.context_engineering.models import ContextAssemblyRecord
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select

_LEVEL_ORDER = [
    ProficiencyLevel.undetermined,
    ProficiencyLevel.novice,
    ProficiencyLevel.competent,
    ProficiencyLevel.advanced,
    ProficiencyLevel.expert,
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ProficiencyService:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        registry_service: Any,
        min_observations_per_dimension: int,
        dwell_time_hours: int,
    ) -> None:
        self.repository = repository
        self.registry_service = registry_service
        self.min_observations_per_dimension = min_observations_per_dimension
        self.dwell_time_hours = dwell_time_hours

    async def compute_for_agent(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        trigger: str = "scheduled",
    ) -> ProficiencyResponse:
        if await self.registry_service.get_profile_state(agent_fqn, workspace_id) is None:
            raise NotFoundError("REGISTRY_AGENT_NOT_FOUND", "Agent not found")
        records = await self._load_records(agent_fqn, workspace_id)
        dimension_values, counts = _derive_dimensions(records)
        missing_dimensions = [
            name for name, count in counts.items() if count < self.min_observations_per_dimension
        ]
        observation_count = sum(counts.values())
        aggregate = _aggregate_score(dimension_values)
        level = _score_to_level(aggregate)
        if missing_dimensions:
            level = ProficiencyLevel.undetermined
        latest = await self.repository.get_latest_proficiency_assessment(agent_fqn, workspace_id)
        now = _utcnow()
        if (
            latest is not None
            and latest.level != level
            and latest.assessed_at > now - timedelta(hours=self.dwell_time_hours)
        ):
            return _to_response(latest)
        assessment = ProficiencyAssessment(
            id=uuid4(),
            agent_fqn=agent_fqn,
            workspace_id=workspace_id,
            level=level,
            dimension_values={
                **dimension_values,
                "aggregate_score": aggregate,
                "min_observations_required": float(self.min_observations_per_dimension),
            },
            observation_count=observation_count,
            trigger=trigger,
            assessed_at=now,
        )
        stored = await self.repository.create_proficiency_assessment(assessment)
        response = _to_response(stored)
        response.missing_dimensions = missing_dimensions
        if missing_dimensions:
            response.dimension_values["min_observations_required"] = float(
                self.min_observations_per_dimension
            )
        return response

    async def get_current(self, agent_fqn: str, workspace_id: UUID) -> ProficiencyResponse:
        assessment = await self.repository.get_latest_proficiency_assessment(
            agent_fqn, workspace_id
        )
        if assessment is None:
            return await self.compute_for_agent(agent_fqn, workspace_id, trigger="manual")
        return _to_response(assessment)

    async def list_history(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> ProficiencyHistoryResponse:
        items, next_cursor = await self.repository.list_proficiency_assessments(
            agent_fqn,
            workspace_id,
            cursor=cursor,
            limit=limit,
        )
        return ProficiencyHistoryResponse(
            items=[_to_response(item) for item in items], next_cursor=next_cursor
        )

    async def query_fleet(
        self,
        workspace_id: UUID,
        *,
        level_at_or_below: str | None = None,
        level: str | None = None,
    ) -> ProficiencyFleetResponse:
        levels: list[str] | None = None
        if level is not None:
            levels = [level]
        elif level_at_or_below is not None:
            threshold = ProficiencyLevel(level_at_or_below)
            levels = [
                item.value
                for item in _LEVEL_ORDER
                if item != ProficiencyLevel.undetermined
                and _LEVEL_ORDER.index(item) <= _LEVEL_ORDER.index(threshold)
            ]
        items = await self.repository.list_proficiency_fleet(workspace_id, levels=levels)
        return ProficiencyFleetResponse(
            items=[_to_response(item) for item in items], total=len(items)
        )

    async def _load_records(
        self, agent_fqn: str, workspace_id: UUID
    ) -> list[ContextAssemblyRecord]:
        result = await self.repository.session.execute(
            select(ContextAssemblyRecord)
            .where(
                ContextAssemblyRecord.agent_fqn == agent_fqn,
                ContextAssemblyRecord.workspace_id == workspace_id,
            )
            .order_by(ContextAssemblyRecord.created_at.desc(), ContextAssemblyRecord.id.desc())
        )
        return list(result.scalars().all())


def _derive_dimensions(
    records: list[ContextAssemblyRecord],
) -> tuple[dict[str, float], dict[str, int]]:
    retrieval = [_clamp(record.quality_score_post) for record in records]
    adherence = [
        _clamp(record.quality_score_pre or record.quality_score_post) for record in records
    ]
    coherence = [
        _clamp(
            1.0
            - abs(record.token_count_post - record.token_count_pre)
            / max(record.token_count_pre or 1, 1)
        )
        for record in records
    ]
    return (
        {
            "retrieval_accuracy": _mean(retrieval),
            "instruction_adherence": _mean(adherence),
            "context_coherence": _mean(coherence),
        },
        {
            "retrieval_accuracy": len(retrieval),
            "instruction_adherence": len(adherence),
            "context_coherence": len(coherence),
        },
    )


def _aggregate_score(values: dict[str, float]) -> float:
    return round(
        (values.get("retrieval_accuracy", 0.0) * 0.4)
        + (values.get("instruction_adherence", 0.0) * 0.3)
        + (values.get("context_coherence", 0.0) * 0.3),
        4,
    )


def _score_to_level(score: float) -> ProficiencyLevel:
    if score >= 0.9:
        return ProficiencyLevel.expert
    if score >= 0.75:
        return ProficiencyLevel.advanced
    if score >= 0.55:
        return ProficiencyLevel.competent
    return ProficiencyLevel.novice


def _to_response(item: ProficiencyAssessment) -> ProficiencyResponse:
    values = {
        key: float(value)
        for key, value in dict(item.dimension_values or {}).items()
        if isinstance(value, (int, float))
    }
    return ProficiencyResponse(
        agent_fqn=item.agent_fqn,
        workspace_id=item.workspace_id,
        level=item.level,
        dimension_values=values,
        observation_count=item.observation_count,
        trigger=item.trigger,
        assessed_at=item.assessed_at,
        missing_dimensions=[],
    )


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))
