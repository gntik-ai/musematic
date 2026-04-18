from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.governance.consumers import ObserverSignalConsumer, VerdictConsumer, _uuid_or_none
from platform.governance.events import GovernanceEventType, VerdictIssuedPayload
from platform.governance.models import GovernanceVerdict, VerdictType
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


class SessionStub:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class ManagerStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def subscribe(self, topic: str, group: str, handler) -> None:
        self.calls.append((topic, group, handler))


class JudgeServiceStub:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[object, object, object]] = []

    async def process_signal(self, envelope, fleet_id, workspace_id):
        self.calls.append((envelope, fleet_id, workspace_id))
        if self.fail:
            raise RuntimeError("boom")
        return ["processed"]


class PipelineConfigStub:
    def __init__(self, chain: object | None) -> None:
        self.chain = chain
        self.calls: list[tuple[object, object]] = []

    async def resolve_chain(self, fleet_id, workspace_id):
        self.calls.append((fleet_id, workspace_id))
        return self.chain


class EnforcerServiceStub:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[object, object]] = []

    async def process_verdict(self, verdict, chain):
        self.calls.append((verdict, chain))
        if self.fail:
            raise RuntimeError("boom")
        return {"status": "processed"}


def _verdict(verdict_type: VerdictType = VerdictType.VIOLATION) -> GovernanceVerdict:
    verdict = GovernanceVerdict(
        id=uuid4(),
        judge_agent_fqn="platform:judge",
        verdict_type=verdict_type,
        policy_id=uuid4(),
        evidence={"target_agent_fqn": "agent:target"},
        rationale="matched",
        recommended_action="block",
        source_event_id=uuid4(),
        fleet_id=uuid4(),
        workspace_id=uuid4(),
    )
    verdict.created_at = datetime.now(UTC)
    verdict.updated_at = verdict.created_at
    return verdict


def _observer_envelope(**payload) -> EventEnvelope:
    return EventEnvelope(
        event_type="monitor.alert",
        source="pytest",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload=payload,
    )


def _verdict_envelope(verdict: GovernanceVerdict) -> EventEnvelope:
    payload = VerdictIssuedPayload(
        verdict_id=verdict.id,
        judge_agent_fqn=verdict.judge_agent_fqn,
        verdict_type=verdict.verdict_type.value,
        policy_id=verdict.policy_id,
        fleet_id=verdict.fleet_id,
        workspace_id=verdict.workspace_id,
        source_event_id=verdict.source_event_id,
        created_at=verdict.created_at,
    )
    return EventEnvelope(
        event_type=GovernanceEventType.verdict_issued.value,
        source="pytest",
        correlation_context=CorrelationContext(
            correlation_id=uuid4(),
            fleet_id=verdict.fleet_id,
            workspace_id=verdict.workspace_id,
        ),
        payload=payload.model_dump(mode="json"),
    )


@pytest.mark.asyncio
async def test_observer_signal_consumer_registers_processes_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = SimpleNamespace(kafka=SimpleNamespace(consumer_group="platform"))
    session = SessionStub()
    service = JudgeServiceStub()

    @asynccontextmanager
    async def _session_scope():
        yield session

    monkeypatch.setattr(
        "platform.governance.consumers.database.AsyncSessionLocal",
        lambda: _session_scope(),
    )
    monkeypatch.setattr(
        "platform.governance.consumers.build_judge_service",
        lambda **kwargs: service,
    )

    consumer = ObserverSignalConsumer(
        settings=settings,  # type: ignore[arg-type]
        redis_client=FakeAsyncRedisClient(),  # type: ignore[arg-type]
        producer=RecordingProducer(),
        registry_service=None,
    )
    manager = ManagerStub()
    consumer.register(manager)
    envelope = _observer_envelope(workspace_id=str(uuid4()), observer_fqn="platform:observer")

    await consumer.handle_event(envelope)

    assert manager.calls[0][0] == "monitor.alerts"
    assert manager.calls[0][1] == "platform.governance-observer-signals"
    assert len(service.calls) == 1
    assert session.committed is True
    assert session.rolled_back is False

    untouched = {"count": 0}
    monkeypatch.setattr(
        "platform.governance.consumers.database.AsyncSessionLocal",
        lambda: untouched.__setitem__("count", untouched["count"] + 1),
    )
    await consumer.handle_event(_observer_envelope(observer_fqn="platform:observer"))
    assert untouched["count"] == 0

    failing_session = SessionStub()
    failing_service = JudgeServiceStub(fail=True)

    @asynccontextmanager
    async def _failing_scope():
        yield failing_session

    monkeypatch.setattr(
        "platform.governance.consumers.database.AsyncSessionLocal",
        lambda: _failing_scope(),
    )
    monkeypatch.setattr(
        "platform.governance.consumers.build_judge_service",
        lambda **kwargs: failing_service,
    )
    with caplog.at_level("ERROR"):
        await consumer.handle_event(_observer_envelope(fleet_id=str(uuid4())))

    assert failing_session.committed is False
    assert failing_session.rolled_back is True
    assert "Failed to process governance observer signal" in caplog.text


@pytest.mark.asyncio
async def test_verdict_consumer_registers_skips_and_processes(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = SimpleNamespace(kafka=SimpleNamespace(consumer_group="platform"))
    consumer = VerdictConsumer(
        settings=settings,  # type: ignore[arg-type]
        producer=RecordingProducer(),
        registry_service=None,
    )
    manager = ManagerStub()
    consumer.register(manager)
    assert manager.calls[0][0] == "governance.events"
    assert manager.calls[0][1] == "platform.governance-verdict-enforcer"

    await consumer.handle_event(
        EventEnvelope(
            event_type="other.event",
            source="pytest",
            correlation_context=CorrelationContext(correlation_id=uuid4()),
            payload={},
        )
    )

    verdict = _verdict()
    skipped_session = SessionStub()
    repo_calls: list[UUID] = []

    @asynccontextmanager
    async def _skipped_scope():
        yield skipped_session

    class RepoFactory:
        def __init__(self, session) -> None:
            del session

        async def get_verdict(self, verdict_id: UUID):
            repo_calls.append(verdict_id)
            return None

    monkeypatch.setattr(
        "platform.governance.consumers.database.AsyncSessionLocal",
        lambda: _skipped_scope(),
    )
    monkeypatch.setattr("platform.governance.consumers.GovernanceRepository", RepoFactory)
    monkeypatch.setattr(
        "platform.governance.consumers.build_pipeline_config_service",
        lambda **kwargs: PipelineConfigStub(chain=None),
    )
    monkeypatch.setattr(
        "platform.governance.consumers.build_enforcer_service",
        lambda **kwargs: EnforcerServiceStub(),
    )

    await consumer.handle_event(_verdict_envelope(verdict))

    assert repo_calls == [verdict.id]
    assert skipped_session.committed is False
    assert skipped_session.rolled_back is False

    compliant = _verdict(VerdictType.COMPLIANT)
    compliant_session = SessionStub()
    compliant_chain = SimpleNamespace(verdict_to_action_mapping={})

    @asynccontextmanager
    async def _compliant_scope():
        yield compliant_session

    monkeypatch.setattr(
        "platform.governance.consumers.database.AsyncSessionLocal",
        lambda: _compliant_scope(),
    )

    async def _get_compliant_verdict(verdict_id: UUID):
        del verdict_id
        return compliant

    monkeypatch.setattr(
        "platform.governance.consumers.GovernanceRepository",
        lambda session: SimpleNamespace(get_verdict=_get_compliant_verdict),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        "platform.governance.consumers.build_pipeline_config_service",
        lambda **kwargs: PipelineConfigStub(chain=compliant_chain),
    )

    await consumer.handle_event(_verdict_envelope(compliant))

    assert compliant_session.committed is False
    assert compliant_session.rolled_back is False

    active_verdict = _verdict()
    active_session = SessionStub()
    chain = SimpleNamespace(verdict_to_action_mapping={"VIOLATION": "block"})
    enforcer = EnforcerServiceStub()

    @asynccontextmanager
    async def _active_scope():
        yield active_session

    monkeypatch.setattr(
        "platform.governance.consumers.database.AsyncSessionLocal",
        lambda: _active_scope(),
    )

    class ActiveRepoFactory:
        def __init__(self, session) -> None:
            del session

        async def get_verdict(self, verdict_id: UUID):
            assert verdict_id == active_verdict.id
            return active_verdict

    monkeypatch.setattr("platform.governance.consumers.GovernanceRepository", ActiveRepoFactory)
    monkeypatch.setattr(
        "platform.governance.consumers.build_pipeline_config_service",
        lambda **kwargs: PipelineConfigStub(chain=chain),
    )
    monkeypatch.setattr(
        "platform.governance.consumers.build_enforcer_service",
        lambda **kwargs: enforcer,
    )

    await consumer.handle_event(_verdict_envelope(active_verdict))

    assert len(enforcer.calls) == 1
    assert active_session.committed is True
    assert active_session.rolled_back is False

    failing_session = SessionStub()
    failing_enforcer = EnforcerServiceStub(fail=True)

    @asynccontextmanager
    async def _failing_scope():
        yield failing_session

    monkeypatch.setattr(
        "platform.governance.consumers.database.AsyncSessionLocal",
        lambda: _failing_scope(),
    )
    monkeypatch.setattr(
        "platform.governance.consumers.build_enforcer_service",
        lambda **kwargs: failing_enforcer,
    )
    with caplog.at_level("ERROR"):
        await consumer.handle_event(_verdict_envelope(active_verdict))

    assert failing_session.committed is False
    assert failing_session.rolled_back is True
    assert "Failed to process governance verdict" in caplog.text


def test_uuid_or_none_handles_uuid_strings_and_invalid_values() -> None:
    value = uuid4()

    assert _uuid_or_none(value) == value
    assert _uuid_or_none(str(value)) == value
    assert _uuid_or_none(None) is None
    assert _uuid_or_none("not-a-uuid") is None
