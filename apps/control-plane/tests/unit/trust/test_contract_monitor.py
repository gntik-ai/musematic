from __future__ import annotations

from contextlib import asynccontextmanager
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.trust.contract_monitor import ContractMonitorConsumer
from uuid import uuid4

import pytest

from tests.trust_support import build_contract_create, build_trust_bundle


@asynccontextmanager
async def _session_scope():
    class _Session:
        commits = 0

        async def commit(self) -> None:
            self.commits += 1

    yield _Session()


def _execution_envelope(
    execution_id,
    *,
    event_type: str = "runtime.lifecycle.completed",
    **payload,
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        source="tests",
        correlation_context=CorrelationContext(
            correlation_id=uuid4(),
            execution_id=execution_id,
        ),
        payload={"execution_id": str(execution_id), "event_type": event_type, **payload},
    )


def _interaction_envelope(
    interaction_id,
    *,
    event_type: str = "runtime.lifecycle.completed",
    **payload,
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        source="tests",
        correlation_context=CorrelationContext(
            correlation_id=uuid4(),
            interaction_id=interaction_id,
        ),
        payload={"interaction_id": str(interaction_id), "event_type": event_type, **payload},
    )


@pytest.mark.asyncio
async def test_contract_monitor_skips_targets_without_contract(monkeypatch) -> None:
    bundle = build_trust_bundle()
    consumer = ContractMonitorConsumer(
        settings=bundle.settings,
        producer=bundle.producer,
        session_factory=_session_scope,
    )
    monkeypatch.setattr(
        "platform.trust.contract_monitor.build_contract_service",
        lambda **_: bundle.contract_service,
    )

    await consumer.handle_event(_execution_envelope(uuid4(), token_count=1500))

    assert bundle.repository.breach_events == []
    assert bundle.producer.events == []


@pytest.mark.asyncio
async def test_contract_monitor_records_cost_breach_and_deduplicates(monkeypatch) -> None:
    bundle = build_trust_bundle()
    contract = await bundle.contract_service.create_contract(
        build_contract_create().model_copy(
            update={
                "cost_limit_tokens": 1000,
                "time_constraint_seconds": None,
                "quality_thresholds": None,
                "enforcement_policy": "warn",
            }
        ),
        uuid4(),
        uuid4(),
    )
    execution_id = uuid4()
    await bundle.contract_service.attach_to_execution(execution_id, contract.id)

    consumer = ContractMonitorConsumer(
        settings=bundle.settings,
        producer=bundle.producer,
        session_factory=_session_scope,
    )
    monkeypatch.setattr(
        "platform.trust.contract_monitor.build_contract_service",
        lambda **_: bundle.contract_service,
    )

    envelope = _execution_envelope(
        execution_id,
        event_type="workflow.runtime.progress",
        token_count=1501,
    )
    await consumer.handle_event(envelope)
    await consumer.handle_event(envelope)

    assert len(bundle.repository.breach_events) == 1
    breach = bundle.repository.breach_events[0]
    assert breach.breached_term == "cost_limit"
    assert breach.enforcement_action == "warn"
    assert breach.enforcement_outcome == "success"
    assert [event["event_type"] for event in bundle.producer.events] == [
        "trust.contract.breach",
        "trust.contract.enforcement",
    ]


@pytest.mark.asyncio
async def test_contract_monitor_handles_time_and_quality_paths(monkeypatch) -> None:
    bundle = build_trust_bundle()
    terminate_contract = await bundle.contract_service.create_contract(
        build_contract_create().model_copy(
            update={
                "time_constraint_seconds": 10,
                "cost_limit_tokens": None,
                "quality_thresholds": None,
                "enforcement_policy": "terminate",
            }
        ),
        uuid4(),
        uuid4(),
    )
    unavailable_contract = await bundle.contract_service.create_contract(
        build_contract_create().model_copy(
            update={
                "time_constraint_seconds": None,
                "cost_limit_tokens": None,
                "quality_thresholds": {"accuracy_min": 0.95},
                "enforcement_policy": "warn",
            }
        ),
        uuid4(),
        uuid4(),
    )
    quality_contract = await bundle.contract_service.create_contract(
        build_contract_create().model_copy(
            update={
                "time_constraint_seconds": None,
                "cost_limit_tokens": None,
                "quality_thresholds": {"accuracy_min": 0.95},
                "enforcement_policy": "warn",
            }
        ),
        uuid4(),
        uuid4(),
    )

    execution_id = uuid4()
    interaction_id = uuid4()
    quality_interaction_id = uuid4()
    await bundle.contract_service.attach_to_execution(execution_id, terminate_contract.id)
    await bundle.contract_service.attach_to_interaction(interaction_id, unavailable_contract.id)
    await bundle.contract_service.attach_to_interaction(quality_interaction_id, quality_contract.id)

    consumer = ContractMonitorConsumer(
        settings=bundle.settings,
        producer=None,
        session_factory=_session_scope,
    )
    monkeypatch.setattr(
        "platform.trust.contract_monitor.build_contract_service",
        lambda **_: bundle.contract_service,
    )

    await consumer.handle_event(_execution_envelope(execution_id, elapsed_seconds=15))
    await consumer.handle_event(_interaction_envelope(interaction_id))
    await consumer.handle_event(_interaction_envelope(quality_interaction_id, accuracy=0.9))

    assert len(bundle.repository.breach_events) == 3
    time_breach = next(
        item for item in bundle.repository.breach_events if item.target_id == execution_id
    )
    unavailable_breach = next(
        item for item in bundle.repository.breach_events if item.target_id == interaction_id
    )
    quality_breach = next(
        item
        for item in bundle.repository.breach_events
        if item.target_id == quality_interaction_id
    )
    assert time_breach.enforcement_outcome == "failed: quarantine_required"
    assert unavailable_breach.observed_value == {"status": "not_evaluated"}
    assert quality_breach.observed_value == {"accuracy_min": 0.9}
    assert quality_breach.threshold_value == {"accuracy_min": 0.95}
