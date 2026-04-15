from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.agentops.events import AgentOpsEventType
from platform.agentops.governance.triggers import (
    AgentOpsGovernanceTriggers,
    _event_key,
    _mean,
    _percentile,
    _stddev,
    register_agentops_governance_consumers,
)
from platform.agentops.models import BaselineStatus, BehavioralBaseline
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest


class _BaselineRepositoryStub:
    def __init__(self, baseline: BehavioralBaseline, baselines: list[BehavioralBaseline]) -> None:
        self.baseline = baseline
        self.baselines = baselines

    async def get_baseline_by_revision(self, revision_id):
        if self.baseline.revision_id == revision_id:
            return self.baseline
        return None

    async def create_baseline(self, baseline: BehavioralBaseline) -> BehavioralBaseline:
        self.baseline = baseline
        self.baselines.append(baseline)
        return baseline

    async def list_baselines(self, agent_fqn, workspace_id, *, cursor=None, limit=100):
        del agent_fqn, workspace_id, cursor, limit
        return self.baselines, None


@pytest.mark.asyncio
async def test_governance_triggers_materializes_pending_baseline_when_samples_are_ready() -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    pending = BehavioralBaseline(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        revision_id=revision_id,
        baseline_window_start=datetime.now(UTC) - timedelta(days=30),
        baseline_window_end=datetime.now(UTC),
        status=BaselineStatus.pending,
    )
    detector = SimpleNamespace(
        minimum_sample_size=5,
        detect=lambda **_: None,
        fetch_samples=_enough_samples,
    )
    triggers = AgentOpsGovernanceTriggers(
        repository=_BaselineRepositoryStub(pending, [pending]),  # type: ignore[arg-type]
        detector=detector,
        evaluation_repository=SimpleNamespace(
            get_run=lambda run_id, workspace_id=None: _run("finance:agent", workspace_id)
        ),
        registry_service=SimpleNamespace(
            list_active_agents=lambda workspace_id: _active_agent("finance:agent", revision_id)
        ),
    )

    await triggers.handle_evaluation_event(
        _run_completed_envelope(workspace_id),
    )

    assert pending.status == BaselineStatus.ready
    assert pending.sample_size == 10
    assert pending.quality_mean > 0.0


@pytest.mark.asyncio
async def test_governance_triggers_calls_detector_for_ready_baseline() -> None:
    workspace_id = uuid4()
    current_revision_id = uuid4()
    previous_revision_id = uuid4()
    current = BehavioralBaseline(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        revision_id=current_revision_id,
        baseline_window_start=datetime.now(UTC) - timedelta(days=30),
        baseline_window_end=datetime.now(UTC),
        status=BaselineStatus.ready,
    )
    previous = BehavioralBaseline(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        revision_id=previous_revision_id,
        baseline_window_start=datetime.now(UTC) - timedelta(days=30),
        baseline_window_end=datetime.now(UTC),
        status=BaselineStatus.ready,
    )
    captured: dict[str, object] = {}
    detector = SimpleNamespace(
        minimum_sample_size=5,
        fetch_samples=_enough_samples,
        detect=_capture_calls(captured),
    )
    triggers = AgentOpsGovernanceTriggers(
        repository=_BaselineRepositoryStub(current, [previous, current]),  # type: ignore[arg-type]
        detector=detector,
        evaluation_repository=SimpleNamespace(
            get_run=lambda run_id, workspace_id=None: _run("finance:agent", workspace_id)
        ),
        registry_service=SimpleNamespace(
            list_active_agents=lambda workspace_id: _active_agent(
                "finance:agent",
                current_revision_id,
            )
        ),
    )

    await triggers.handle_evaluation_event(_run_completed_envelope(workspace_id))

    assert captured == {
        "new_revision_id": current_revision_id,
        "baseline_revision_id": previous_revision_id,
        "agent_fqn": "finance:agent",
        "workspace_id": workspace_id,
    }


@pytest.mark.asyncio
async def test_governance_triggers_handles_retirement_trigger_event() -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    captured: dict[str, object] = {}
    triggers = AgentOpsGovernanceTriggers(
        repository=_BaselineRepositoryStub(
            BehavioralBaseline(
                workspace_id=workspace_id,
                agent_fqn="finance:agent",
                revision_id=revision_id,
                baseline_window_start=datetime.now(UTC) - timedelta(days=30),
                baseline_window_end=datetime.now(UTC),
                status=BaselineStatus.pending,
            ),
            [],
        ),  # type: ignore[arg-type]
        detector=SimpleNamespace(),
        evaluation_repository=SimpleNamespace(),
        registry_service=None,
        agentops_service=SimpleNamespace(
            initiate_retirement_from_trigger=_capture_retirement(captured)
        ),
    )

    await triggers.handle_agentops_event(
        EventEnvelope(
            event_type="agentops.retirement.trigger",
            source="platform.agentops",
            correlation_context=CorrelationContext(
                workspace_id=workspace_id,
                correlation_id=uuid4(),
            ),
            payload={
                "agent_fqn": "finance:agent",
                "workspace_id": str(workspace_id),
                "revision_id": str(revision_id),
            },
        )
    )

    assert captured == {
        "agent_fqn": "finance:agent",
        "revision_id": revision_id,
        "workspace_id": workspace_id,
        "trigger_reason": "sustained_degradation",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "handler_name", "trigger_reason"),
    [
        ("trust.agent_revision_changed", "handle_trust_event", "revision_changed"),
        ("trust.policy_changed", "handle_trust_event", "policy_changed"),
        ("trust.certification_expiring", "handle_trust_event", "expiry_approaching"),
        ("trust.conformance_failed", "handle_trust_event", "conformance_failed"),
        (
            AgentOpsEventType.regression_detected.value,
            "handle_agentops_event",
            "regression_detected",
        ),
    ],
)
async def test_governance_triggers_fire_recertification_for_all_trigger_types(
    event_type: str,
    handler_name: str,
    trigger_reason: str,
) -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    trust_service = _TrustServiceStub()
    governance_publisher = _GovernancePublisherStub()
    triggers = AgentOpsGovernanceTriggers(
        repository=_BaselineRepositoryStub(_baseline(workspace_id, revision_id), []),  # type: ignore[arg-type]
        detector=SimpleNamespace(),
        evaluation_repository=SimpleNamespace(),
        registry_service=None,
        trust_service=trust_service,
        governance_publisher=governance_publisher,  # type: ignore[arg-type]
    )

    envelope = EventEnvelope(
        event_type=event_type,
        source="platform.test",
        correlation_context=CorrelationContext(
            workspace_id=workspace_id,
            correlation_id=uuid4(),
        ),
        payload={
            "event_id": str(uuid4()),
            "agent_fqn": "finance:agent",
            "workspace_id": str(workspace_id),
            "revision_id": str(revision_id),
        },
    )

    await getattr(triggers, handler_name)(envelope)

    assert trust_service.calls == [("finance:agent", revision_id, trigger_reason)]
    assert governance_publisher.calls[0]["event_type"] == "agentops.recertification.triggered"


@pytest.mark.asyncio
async def test_governance_consumer_is_idempotent_for_duplicate_events() -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    event_id = str(uuid4())
    trust_service = _TrustServiceStub()
    triggers = AgentOpsGovernanceTriggers(
        repository=_BaselineRepositoryStub(_baseline(workspace_id, revision_id), []),  # type: ignore[arg-type]
        detector=SimpleNamespace(),
        evaluation_repository=SimpleNamespace(),
        registry_service=None,
        trust_service=trust_service,
        governance_publisher=_GovernancePublisherStub(),  # type: ignore[arg-type]
    )
    envelope = EventEnvelope(
        event_type="trust.policy_changed",
        source="platform.test",
        correlation_context=CorrelationContext(
            workspace_id=workspace_id,
            correlation_id=uuid4(),
        ),
        payload={
            "event_id": event_id,
            "agent_fqn": "finance:agent",
            "workspace_id": str(workspace_id),
            "revision_id": str(revision_id),
        },
    )

    await triggers.handle_trust_event(envelope)
    await triggers.handle_trust_event(envelope)

    assert trust_service.calls == [("finance:agent", revision_id, "policy_changed")]


@pytest.mark.asyncio
async def test_governance_triggers_ignore_missing_or_non_matching_events() -> None:
    workspace_id = uuid4()
    triggers = AgentOpsGovernanceTriggers(
        repository=_BaselineRepositoryStub(_baseline(workspace_id, uuid4()), []),  # type: ignore[arg-type]
        detector=SimpleNamespace(
            minimum_sample_size=5,
            fetch_samples=_not_enough_samples,
            detect=_capture_calls({}),
        ),
        evaluation_repository=SimpleNamespace(get_run=_missing_run),
        registry_service=None,
        agentops_service=None,
    )

    await triggers.handle_evaluation_event(
        EventEnvelope(
            event_type="evaluation.run.started",
            source="platform.test",
            correlation_context=CorrelationContext(
                workspace_id=workspace_id,
                correlation_id=uuid4(),
            ),
            payload={},
        )
    )
    await triggers.handle_evaluation_event(
        EventEnvelope(
            event_type="evaluation.run.completed",
            source="platform.test",
            correlation_context=CorrelationContext(
                workspace_id=workspace_id,
                correlation_id=uuid4(),
            ),
            payload={},
        )
    )
    await triggers.handle_agentops_event(
        EventEnvelope(
            event_type="agentops.ignored",
            source="platform.test",
            correlation_context=CorrelationContext(
                workspace_id=workspace_id,
                correlation_id=uuid4(),
            ),
            payload={},
        )
    )
    await triggers.handle_trust_event(
        EventEnvelope(
            event_type="trust.ignored",
            source="platform.test",
            correlation_context=CorrelationContext(
                workspace_id=workspace_id,
                correlation_id=uuid4(),
            ),
            payload={},
        )
    )


@pytest.mark.asyncio
async def test_governance_triggers_cover_current_target_and_ate_completion_branches() -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    captured: dict[str, object] = {}
    pipeline = SimpleNamespace(handle_ate_result=_capture_ate(captured))
    triggers = AgentOpsGovernanceTriggers(
        repository=_BaselineRepositoryStub(_baseline(workspace_id, revision_id), []),  # type: ignore[arg-type]
        detector=SimpleNamespace(),
        evaluation_repository=SimpleNamespace(),
        registry_service=SimpleNamespace(list_active_agents=_active_agents_without_revision),
        agentops_service=SimpleNamespace(_adaptation_pipeline=lambda: pipeline),
    )

    assert await triggers._current_target("finance:agent", workspace_id) is None

    triggers.registry_service = SimpleNamespace(
        list_active_agents=AsyncMock(
            return_value=[{"agent_fqn": "finance:agent", "revision_id": str(revision_id)}]
        )
    )
    assert await triggers._current_target("finance:agent", workspace_id) == {
        "revision_id": revision_id
    }

    await triggers.handle_evaluation_event(
        EventEnvelope(
            event_type="evaluation.ate.run.completed",
            source="platform.test",
            correlation_context=CorrelationContext(
                workspace_id=workspace_id,
                correlation_id=uuid4(),
            ),
            payload={"ate_run_id": str(uuid4())},
        )
    )
    await triggers.handle_evaluation_event(
        EventEnvelope(
            event_type="evaluation.ate.run.failed",
            source="platform.test",
            correlation_context=CorrelationContext(
                workspace_id=workspace_id,
                correlation_id=uuid4(),
            ),
            payload={"ate_run_id": str(uuid4())},
        )
    )
    await triggers._handle_ate_completion(
        EventEnvelope(
            event_type="evaluation.ate.run.completed",
            source="platform.test",
            correlation_context=CorrelationContext(
                workspace_id=workspace_id,
                correlation_id=uuid4(),
            ),
            payload={},
        ),
        passed=True,
    )

    assert captured["calls"] == 2


def test_governance_trigger_helper_functions_and_consumer_registration() -> None:
    manager = SimpleNamespace(subscribe=Mock())
    triggers = SimpleNamespace(
        handle_evaluation_event=Mock(),
        handle_agentops_event=Mock(),
        handle_trust_event=Mock(),
    )

    register_agentops_governance_consumers(
        manager,
        group_id="agentops",
        triggers=triggers,
    )

    envelope = EventEnvelope(
        event_type="trust.policy_changed",
        source="platform.test",
        correlation_context=CorrelationContext(workspace_id=uuid4(), correlation_id=uuid4()),
        payload={"event_id": "evt-1"},
    )
    fallback_key = _event_key(
        EventEnvelope(
            event_type="agentops.regression_detected",
            source="platform.test",
            correlation_context=CorrelationContext(workspace_id=uuid4(), correlation_id=uuid4()),
            payload={},
        )
    )

    assert _mean([]) == 0.0
    assert _mean([1.0, 2.0, 3.0]) == 2.0
    assert _stddev([1.0]) == 0.0
    assert round(_stddev([1.0, 2.0, 3.0]), 2) == 1.0
    assert _percentile([], 95.0) == 0.0
    assert _percentile([1.0, 2.0, 3.0], 50.0) == 2.0
    assert _event_key(envelope) == "evt-1"
    assert fallback_key.startswith("agentops.regression_detected:")
    assert manager.subscribe.call_count == 3


async def _run(agent_fqn: str, workspace_id):
    return SimpleNamespace(agent_fqn=agent_fqn, workspace_id=workspace_id)


async def _active_agent(agent_fqn: str, revision_id):
    return [{"agent_fqn": agent_fqn, "revision_id": str(revision_id)}]


async def _active_agents_without_revision(workspace_id):
    del workspace_id
    return [{"agent_fqn": "finance:agent"}]


async def _enough_samples(**kwargs):
    dimension = kwargs["dimension"]
    if dimension == "quality":
        return [0.80 + (index * 0.01) for index in range(10)]
    if dimension == "latency":
        return [120.0 + index for index in range(10)]
    if dimension == "cost":
        return [0.10 + (index * 0.01) for index in range(10)]
    return [1.0] * 10


async def _not_enough_samples(**kwargs):
    del kwargs
    return [0.9, 0.8]


async def _missing_run(run_id, workspace_id):
    del run_id, workspace_id
    return None


def _baseline(workspace_id, revision_id):
    return BehavioralBaseline(
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        revision_id=revision_id,
        baseline_window_start=datetime.now(UTC) - timedelta(days=30),
        baseline_window_end=datetime.now(UTC),
        status=BaselineStatus.pending,
    )


def _capture_calls(captured: dict[str, object]):
    async def _detect(**kwargs):
        captured.update(kwargs)
        return None

    return _detect


def _capture_retirement(captured: dict[str, object]):
    async def _initiate(
        agent_fqn,
        revision_id,
        workspace_id,
        *,
        trigger_reason,
    ):
        captured.update(
            {
                "agent_fqn": agent_fqn,
                "revision_id": revision_id,
                "workspace_id": workspace_id,
                "trigger_reason": trigger_reason,
            }
        )
        return None

    return _initiate


def _capture_ate(captured: dict[str, object]):
    async def _handle(ate_run_id, *, passed):
        captured["calls"] = int(captured.get("calls", 0)) + 1
        captured[str(ate_run_id)] = passed

    return _handle


class _TrustServiceStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, str]] = []

    async def trigger_recertification(self, agent_fqn, revision_id, trigger_reason):
        self.calls.append((agent_fqn, revision_id, trigger_reason))


class _GovernancePublisherStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def record(self, event_type, agent_fqn, workspace_id, **kwargs):
        self.calls.append(
            {
                "event_type": event_type,
                "agent_fqn": agent_fqn,
                "workspace_id": workspace_id,
                **kwargs,
            }
        )


def _run_completed_envelope(workspace_id):
    return EventEnvelope(
        event_type="evaluation.run.completed",
        source="platform.evaluation",
        correlation_context=CorrelationContext(
            workspace_id=workspace_id,
            correlation_id=uuid4(),
        ),
        payload={"run_id": str(uuid4()), "workspace_id": str(workspace_id)},
    )
