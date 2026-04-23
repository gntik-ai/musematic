from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from uuid import uuid4

import pytest
from tests.marketplace_support import build_quality_aggregate, build_quality_service, build_rating


def test_quality_aggregate_computed_properties_cover_rates_and_zero_division() -> None:
    populated = build_quality_aggregate(
        execution_count=100,
        success_count=95,
        self_correction_count=10,
        quality_score_sum=Decimal("8000"),
        quality_score_count=100,
        satisfaction_sum=Decimal("43"),
        satisfaction_count=10,
    )
    empty = build_quality_aggregate(
        has_data=False,
        execution_count=0,
        success_count=0,
        self_correction_count=0,
        quality_score_sum=Decimal("0"),
        quality_score_count=0,
        satisfaction_sum=Decimal("0"),
        satisfaction_count=0,
        updated_at=None,
    )

    assert populated.success_rate == 0.95
    assert populated.self_correction_rate == 0.1
    assert populated.quality_score_avg == 80.0
    assert populated.satisfaction_avg == 4.3
    assert empty.success_rate == 0.0
    assert empty.self_correction_rate == 0.0
    assert empty.quality_score_avg == 0.0
    assert empty.satisfaction_avg == 0.0


@pytest.mark.asyncio
async def test_quality_service_handlers_update_aggregate_state() -> None:
    service, repository, _producer = build_quality_service()
    agent_id = uuid4()
    older = datetime.now(UTC) - timedelta(days=2)
    aggregate = await repository.get_or_create_quality_aggregate(agent_id)
    aggregate.source_unavailable_since = older

    await service.handle_execution_event(
        {"event_type": "step.completed", "agent_id": str(agent_id)}
    )
    await service.handle_execution_event(
        {"event_type": "step.failed", "agent_id": str(agent_id)}
    )
    await service.handle_execution_event(
        {"event_type": "step.self_corrected", "agent_id": str(agent_id)}
    )
    await service.handle_evaluation_event(
        {"event_type": "evaluation.scored", "agent_id": str(agent_id), "score": 80.0}
    )
    await service.handle_trust_event(
        {
            "event_type": "certification.status_changed",
            "agent_id": str(agent_id),
            "certification_status": "compliant",
        }
    )

    updated = await repository.get_or_create_quality_aggregate(agent_id)
    assert updated.execution_count == 3
    assert updated.success_count == 2
    assert updated.failure_count == 1
    assert updated.self_correction_count == 1
    assert updated.quality_score_sum == Decimal("80.0")
    assert updated.quality_score_count == 1
    assert updated.certification_status == "compliant"
    assert updated.has_data is True
    assert updated.source_unavailable_since is None
    assert updated.data_source_last_updated_at is not None


@pytest.mark.asyncio
async def test_quality_service_infers_trust_status_from_event_type_when_payload_omits_it() -> None:
    service, repository, _producer = build_quality_service()
    agent_id = uuid4()
    envelope = EventEnvelope(
        event_type="certification.activated",
        payload={"agent_id": str(agent_id)},
        source="tests.marketplace",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
    )

    await service.handle_trust_event(envelope)

    aggregate = await repository.get_or_create_quality_aggregate(agent_id)
    assert aggregate.certification_status == "active"


@pytest.mark.asyncio
async def test_quality_service_updates_satisfaction_from_ratings() -> None:
    service, repository, _producer = build_quality_service()
    agent_id = uuid4()
    repository.ratings[(uuid4(), agent_id)] = build_rating(agent_id=agent_id, score=5)
    repository.ratings[(uuid4(), agent_id)] = build_rating(agent_id=agent_id, score=3)

    await service.update_satisfaction_aggregate(agent_id)

    aggregate = await repository.get_or_create_quality_aggregate(agent_id)
    assert aggregate.satisfaction_sum == Decimal("8.0")
    assert aggregate.satisfaction_count == 2
    assert aggregate.satisfaction_avg == 4.0


@pytest.mark.asyncio
async def test_quality_service_ignores_invalid_payloads_and_supports_event_envelopes() -> None:
    service, repository, _producer = build_quality_service()
    agent_id = uuid4()

    await service.handle_execution_event({"event_type": "step.unknown", "agent_id": str(agent_id)})
    await service.handle_execution_event({"event_type": "step.completed"})
    await service.handle_evaluation_event({"event_type": "evaluation.scored"})
    await service.handle_trust_event({"event_type": "trust.changed"})
    await service.update_satisfaction_aggregate(agent_id)
    envelope = EventEnvelope(
        event_type="step.completed",
        payload={"agent_id": str(agent_id)},
        source="tests.marketplace",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
    )
    await service.handle_execution_event(envelope)

    aggregate = await repository.get_or_create_quality_aggregate(agent_id)
    assert aggregate.execution_count == 1
    assert aggregate.success_count == 1
    assert aggregate.satisfaction_count == 0
