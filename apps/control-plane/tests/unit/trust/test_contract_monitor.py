from __future__ import annotations

from contextlib import asynccontextmanager
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.trust.contract_monitor import ContractMonitorConsumer
from uuid import uuid4

import pytest

from tests.trust_support import build_contract_create, build_trust_bundle


class _ManagerStub:
    def __init__(self) -> None:
        self.subscriptions: list[tuple[str, str, object]] = []

    def subscribe(self, topic: str, group: str, handler) -> None:
        self.subscriptions.append((topic, group, handler))


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


def test_contract_monitor_registers_topics_and_uuid_helper() -> None:
    bundle = build_trust_bundle()
    consumer = ContractMonitorConsumer(
        settings=bundle.settings,
        producer=bundle.producer,
        session_factory=_session_scope,
    )
    manager = _ManagerStub()

    consumer.register(manager)

    assert manager.subscriptions == [
        (
            "workflow.runtime",
            "platform.trust-contract-monitor",
            consumer.handle_event,
        ),
        (
            "runtime.lifecycle",
            "platform.trust-contract-monitor-lifecycle",
            consumer.handle_event,
        ),
    ]
    value = uuid4()
    assert consumer._uuid_or_none(value) == value
    assert consumer._uuid_or_none("not-a-uuid") is None


@pytest.mark.asyncio
async def test_contract_monitor_ignores_invalid_snapshots_and_publish_failures(monkeypatch) -> None:
    bundle = build_trust_bundle()
    contract = await bundle.contract_service.create_contract(
        build_contract_create().model_copy(
            update={
                "quality_thresholds": {"latency_max": 0.5, "score": "n/a"},
                "cost_limit_tokens": None,
                "time_constraint_seconds": None,
                "enforcement_policy": "escalate",
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

    bundle.repository.execution_attachments[execution_id]["snapshot"]["id"] = "bad-id"
    await consumer.handle_event(_execution_envelope(execution_id, token_count=999))
    bundle.repository.execution_attachments[execution_id]["snapshot"]["id"] = str(uuid4())
    await consumer.handle_event(_execution_envelope(execution_id, token_count=999))

    failing_producer = type(
        "FailingProducer",
        (),
        {"publish": staticmethod(_raise_publish_error)},
    )()
    failing_consumer = ContractMonitorConsumer(
        settings=bundle.settings,
        producer=failing_producer,
        session_factory=_session_scope,
    )
    quality_breaches = failing_consumer._evaluate_breaches(
        event_type="runtime.lifecycle.completed",
        payload={"latency": 0.8, "score": "bad"},
        snapshot={
            "quality_thresholds": {"latency_max": 0.5, "score": "n/a"},
            "enforcement_policy": "escalate",
        },
    )
    outcome = await failing_consumer._enforce(contract, "execution", execution_id, "escalate")

    assert bundle.repository.breach_events == []
    assert quality_breaches == [
        {
            "term": "quality_threshold",
            "observed": {"latency_max": 0.8},
            "threshold": {"latency_max": 0.5},
            "action": "escalate",
        }
    ]
    assert outcome == "failed"


async def _raise_publish_error(*args, **kwargs) -> None:
    del args, kwargs
    raise RuntimeError("publish failed")


@pytest.mark.asyncio
async def test_contract_monitor_covers_exact_key_quality_and_enforcement_branches() -> None:
    bundle = build_trust_bundle()
    consumer = ContractMonitorConsumer(
        settings=bundle.settings,
        producer=bundle.producer,
        session_factory=_session_scope,
    )
    contract = await bundle.contract_service.create_contract(
        build_contract_create(),
        uuid4(),
        uuid4(),
    )
    execution_id = uuid4()
    exact_key_breaches = consumer._evaluate_breaches(
        event_type="runtime.lifecycle.completed",
        payload={"latency_max": 0.7},
        snapshot={
            "quality_thresholds": {"latency_max": 0.5},
            "enforcement_policy": "terminate",
        },
    )
    no_producer_consumer = ContractMonitorConsumer(
        settings=bundle.settings,
        producer=None,
        session_factory=_session_scope,
    )
    success_outcome = await consumer._enforce(contract, "execution", execution_id, "terminate")
    no_producer_outcome = await no_producer_consumer._enforce(
        contract,
        "execution",
        execution_id,
        "escalate",
    )
    terminate_failure = await ContractMonitorConsumer(
        settings=bundle.settings,
        producer=type("FailingProducer", (), {"publish": staticmethod(_raise_publish_error)})(),
        session_factory=_session_scope,
    )._enforce(contract, "execution", execution_id, "terminate")

    assert exact_key_breaches == [
        {
            "term": "quality_threshold",
            "observed": {"latency_max": 0.7},
            "threshold": {"latency_max": 0.5},
            "action": "terminate",
        }
    ]
    assert success_outcome == "success"
    assert no_producer_outcome == "failed"
    assert terminate_failure == "failed: quarantine_required"
