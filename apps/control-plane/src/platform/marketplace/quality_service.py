from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.common.config import PlatformSettings
from platform.common.events.envelope import EventEnvelope
from platform.common.events.producer import EventProducer
from platform.marketplace.repository import MarketplaceRepository
from uuid import UUID


class MarketplaceQualityAggregateService:
    def __init__(
        self,
        *,
        repository: MarketplaceRepository,
        settings: PlatformSettings,
        producer: EventProducer | None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer

    async def handle_execution_event(self, event: dict[str, object] | EventEnvelope) -> None:
        event_type, payload = _event_parts(event)
        agent_id = _coerce_uuid(payload.get("agent_id") or payload.get("agent_profile_id"))
        if agent_id is None:
            return
        aggregate = await self.repository.get_or_create_quality_aggregate(agent_id)
        if event_type == "step.completed":
            aggregate.execution_count += 1
            aggregate.success_count += 1
        elif event_type == "step.failed":
            aggregate.execution_count += 1
            aggregate.failure_count += 1
        elif event_type == "step.self_corrected":
            aggregate.execution_count += 1
            aggregate.success_count += 1
            aggregate.self_correction_count += 1
        else:
            return
        aggregate.has_data = True
        aggregate.data_source_last_updated_at = datetime.now(UTC)
        aggregate.source_unavailable_since = None
        await self.repository.update_quality_aggregate(aggregate)

    async def handle_evaluation_event(self, event: dict[str, object] | EventEnvelope) -> None:
        _, payload = _event_parts(event)
        agent_id = _coerce_uuid(payload.get("agent_id") or payload.get("agent_profile_id"))
        score = payload.get("score") or payload.get("quality_score")
        if agent_id is None or score is None:
            return
        aggregate = await self.repository.get_or_create_quality_aggregate(agent_id)
        aggregate.quality_score_sum += Decimal(str(score))
        aggregate.quality_score_count += 1
        aggregate.has_data = True
        aggregate.data_source_last_updated_at = datetime.now(UTC)
        aggregate.source_unavailable_since = None
        await self.repository.update_quality_aggregate(aggregate)

    async def handle_trust_event(self, event: dict[str, object] | EventEnvelope) -> None:
        _, payload = _event_parts(event)
        agent_id = _coerce_uuid(payload.get("agent_id") or payload.get("agent_profile_id"))
        certification_status = payload.get("certification_status") or payload.get("status")
        if agent_id is None or certification_status is None:
            return
        aggregate = await self.repository.get_or_create_quality_aggregate(agent_id)
        aggregate.certification_status = str(certification_status)
        aggregate.data_source_last_updated_at = datetime.now(UTC)
        aggregate.source_unavailable_since = None
        await self.repository.update_quality_aggregate(aggregate)

    async def update_satisfaction_aggregate(self, agent_id: UUID) -> None:
        total_score, count = await self.repository.get_rating_totals(agent_id)
        aggregate = await self.repository.get_or_create_quality_aggregate(agent_id)
        aggregate.satisfaction_sum = Decimal(str(total_score))
        aggregate.satisfaction_count = count
        aggregate.data_source_last_updated_at = datetime.now(UTC)
        if count > 0:
            aggregate.has_data = True
        await self.repository.update_quality_aggregate(aggregate)


def _event_parts(
    event: dict[str, object] | EventEnvelope,
) -> tuple[str, dict[str, object]]:
    if isinstance(event, EventEnvelope):
        return event.event_type, dict(event.payload)
    event_type = str(event.get("event_type") or "")
    payload = event.get("payload")
    if isinstance(payload, dict):
        return event_type, dict(payload)
    return event_type, dict(event)


def _coerce_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None
