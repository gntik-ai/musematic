from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.governance.dependencies import (
    GovernanceService,
    _get_producer,
    _get_redis,
    _get_settings,
    build_enforcer_service,
    build_governance_service,
    build_judge_service,
    build_pipeline_config_service,
    get_enforcer_service,
    get_governance_service,
    get_judge_service,
    get_pipeline_config_service,
)
from platform.governance.exceptions import VerdictNotFoundError
from platform.governance.models import ActionType, EnforcementAction, GovernanceVerdict, VerdictType
from platform.governance.schemas import EnforcementActionListQuery, VerdictListQuery
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


def _verdict() -> GovernanceVerdict:
    verdict = GovernanceVerdict(
        id=uuid4(),
        judge_agent_fqn="platform:judge",
        verdict_type=VerdictType.VIOLATION,
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


def _action(verdict_id) -> EnforcementAction:
    action = EnforcementAction(
        id=uuid4(),
        enforcer_agent_fqn="platform:enforcer",
        verdict_id=verdict_id,
        action_type=ActionType.block,
        target_agent_fqn="agent:target",
        outcome={"blocked": True},
        workspace_id=uuid4(),
    )
    action.created_at = datetime.now(UTC)
    action.updated_at = action.created_at
    return action


class RepoStub:
    def __init__(self, *, verdict: GovernanceVerdict | None = None) -> None:
        self.verdict = verdict
        self.action = _action(verdict.id) if verdict is not None else None
        if verdict is not None:
            verdict.enforcement_actions = [self.action] if self.action is not None else []

    async def list_verdicts(self, query: VerdictListQuery):
        del query
        items = [self.verdict] if self.verdict is not None else []
        return items, len(items), "cursor-1" if items else None

    async def get_verdict(self, verdict_id):
        del verdict_id
        return self.verdict

    async def list_enforcement_actions(self, query: EnforcementActionListQuery):
        del query
        items = [self.action] if self.action is not None else []
        return items, len(items), "cursor-2" if items else None


def test_builders_wire_expected_dependencies() -> None:
    settings = PlatformSettings()
    producer = RecordingProducer()
    redis_client = FakeAsyncRedisClient()
    session = object()
    registry_service = object()

    pipeline = build_pipeline_config_service(
        session=session,  # type: ignore[arg-type]
        registry_service=registry_service,  # type: ignore[arg-type]
    )
    judge = build_judge_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        producer=producer,
        redis_client=redis_client,  # type: ignore[arg-type]
        registry_service=registry_service,  # type: ignore[arg-type]
    )
    enforcer = build_enforcer_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        producer=producer,
    )
    service = build_governance_service(session=session)  # type: ignore[arg-type]

    assert pipeline.registry_service is registry_service
    assert judge.settings is settings
    assert judge.producer is producer
    assert judge.redis_client is redis_client
    assert enforcer.producer is producer
    assert service.repository.session is session


def test_governance_service_lists_and_reads_entities() -> None:
    verdict = _verdict()
    service = GovernanceService(RepoStub(verdict=verdict))  # type: ignore[arg-type]

    verdicts = __import__("asyncio").run(service.list_verdicts(VerdictListQuery()))
    detail = __import__("asyncio").run(service.get_verdict(verdict.id))
    actions = __import__("asyncio").run(
        service.list_enforcement_actions(EnforcementActionListQuery())
    )

    assert verdicts.total == 1
    assert verdicts.items[0].id == verdict.id
    assert detail.id == verdict.id
    assert detail.enforcement_action is not None
    assert detail.enforcement_action.verdict_id == verdict.id
    assert actions.total == 1
    assert actions.items[0].verdict_id == verdict.id


def test_governance_service_raises_when_verdict_is_missing() -> None:
    service = GovernanceService(RepoStub(verdict=None))  # type: ignore[arg-type]

    with pytest.raises(VerdictNotFoundError):
        __import__("asyncio").run(service.get_verdict(uuid4()))


def test_dependency_helpers_read_request_state() -> None:
    settings = PlatformSettings()
    producer = RecordingProducer()
    redis_client = FakeAsyncRedisClient()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={"kafka": producer, "redis": redis_client},
            )
        )
    )

    assert _get_settings(request) is settings
    assert _get_producer(request) is producer
    assert _get_redis(request) is redis_client


@pytest.mark.asyncio
async def test_getters_build_services_from_request_state(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = PlatformSettings()
    producer = RecordingProducer()
    redis_client = FakeAsyncRedisClient()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={"kafka": producer, "redis": redis_client},
            )
        )
    )
    session = object()
    registry_service = object()
    captured: dict[str, dict[str, object]] = {}

    def _capture(name: str):
        def _builder(**kwargs):
            captured[name] = kwargs
            return name

        return _builder

    monkeypatch.setattr(
        "platform.governance.dependencies.build_pipeline_config_service",
        _capture("pipeline"),
    )
    monkeypatch.setattr(
        "platform.governance.dependencies.build_judge_service",
        _capture("judge"),
    )
    monkeypatch.setattr(
        "platform.governance.dependencies.build_enforcer_service",
        _capture("enforcer"),
    )
    monkeypatch.setattr(
        "platform.governance.dependencies.build_governance_service",
        _capture("service"),
    )

    pipeline = await get_pipeline_config_service(
        request,  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
        registry_service=registry_service,  # type: ignore[arg-type]
    )
    judge = await get_judge_service(
        request,  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
        registry_service=registry_service,  # type: ignore[arg-type]
    )
    enforcer = await get_enforcer_service(
        request,  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
    )
    service = await get_governance_service(
        request,  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
    )

    assert (pipeline, judge, enforcer, service) == ("pipeline", "judge", "enforcer", "service")
    assert captured["pipeline"] == {"session": session, "registry_service": registry_service}
    assert captured["judge"] == {
        "session": session,
        "settings": settings,
        "producer": producer,
        "redis_client": redis_client,
        "registry_service": registry_service,
    }
    assert captured["enforcer"] == {
        "session": session,
        "settings": settings,
        "producer": producer,
    }
    assert captured["service"] == {"session": session}
