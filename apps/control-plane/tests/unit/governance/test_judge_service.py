from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.governance.models import GovernanceVerdict, VerdictType
from platform.governance.services.judge_service import JudgeService
from platform.governance.services.pipeline_config import ChainConfig
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.auth_oauth_support import RateLimitResultStub
from tests.auth_support import RecordingProducer


class RepoStub:
    def __init__(self) -> None:
        self.created: list[GovernanceVerdict] = []

    async def create_verdict(self, verdict: GovernanceVerdict) -> GovernanceVerdict:
        verdict.id = uuid4()
        verdict.created_at = datetime.now(UTC)
        verdict.updated_at = verdict.created_at
        self.created.append(verdict)
        return verdict


class PipelineStub:
    def __init__(self, chain: ChainConfig | None) -> None:
        self.chain = chain

    async def resolve_chain(self, fleet_id, workspace_id):
        del fleet_id, workspace_id
        return self.chain


class FleetPolicyRepoStub:
    def __init__(self, binding=None) -> None:
        self.binding = binding

    async def get_by_id(self, binding_id, fleet_id):
        del binding_id, fleet_id
        return self.binding


class PolicyRepoStub:
    def __init__(self, policy=None) -> None:
        self.policy = policy

    async def get_by_id(self, policy_id):
        del policy_id
        return self.policy


class RedisStub:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[tuple[str, str, int, int]] = []

    async def check_rate_limit(self, scope: str, key: str, limit: int, window_ms: int):
        self.calls.append((scope, key, limit, window_ms))
        return RateLimitResultStub(allowed=self.allowed)


def _chain() -> ChainConfig:
    return ChainConfig(
        observer_fqns=["platform:observer"],
        judge_fqns=["platform:judge-1"],
        enforcer_fqns=["platform:enforcer-1"],
        policy_binding_ids=[str(uuid4())],
        verdict_to_action_mapping={"VIOLATION": "block"},
        scope="fleet",
    )


def _signal(*, value: float = 0.9, workspace_id=None, fleet_id=None, extra=None) -> EventEnvelope:
    payload = {"observer_fqn": "platform:observer", "value": value}
    if extra:
        payload.update(extra)
    return EventEnvelope(
        event_type="monitor.alert",
        source="pytest",
        correlation_context=CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=workspace_id,
            fleet_id=fleet_id,
        ),
        payload=payload,
    )


def _policy(binding: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        id=binding.policy_id,
        current_version=SimpleNamespace(rules={"threshold": 0.8}),
    )


def _service(*, chain=None, redis_allowed=True, policy=None, binding=None, timeout=30):
    base_settings = PlatformSettings()
    settings = base_settings.model_copy(
        update={
            "governance": base_settings.governance.model_copy(
                update={"judge_timeout_seconds": timeout}
            )
        }
    )
    repo = RepoStub()
    producer = RecordingProducer()
    service = JudgeService(
        repository=repo,  # type: ignore[arg-type]
        pipeline_config=PipelineStub(chain),  # type: ignore[arg-type]
        fleet_policy_repo=FleetPolicyRepoStub(binding),  # type: ignore[arg-type]
        policy_repo=PolicyRepoStub(policy),  # type: ignore[arg-type]
        settings=settings,
        producer=producer,
        redis_client=RedisStub(redis_allowed),  # type: ignore[arg-type]
    )
    return service, repo, producer


@pytest.mark.asyncio
async def test_process_signal_persists_violation_verdict() -> None:
    fleet_id = uuid4()
    binding = SimpleNamespace(policy_id=uuid4())
    service, repo, producer = _service(chain=_chain(), policy=_policy(binding), binding=binding)

    verdicts = await service.process_signal(_signal(fleet_id=fleet_id, value=0.97), fleet_id, None)

    assert len(verdicts) == 1
    assert verdicts[0].verdict_type is VerdictType.VIOLATION
    assert repo.created[0].policy_id == binding.policy_id
    assert producer.events[0]["event_type"] == "governance.verdict.issued"


@pytest.mark.asyncio
async def test_process_signal_persists_compliant_verdict() -> None:
    fleet_id = uuid4()
    binding = SimpleNamespace(policy_id=uuid4())
    service, repo, _producer = _service(chain=_chain(), policy=_policy(binding), binding=binding)

    verdicts = await service.process_signal(_signal(fleet_id=fleet_id, value=0.3), fleet_id, None)

    assert len(verdicts) == 1
    assert verdicts[0].verdict_type is VerdictType.COMPLIANT
    assert repo.created[0].recommended_action is None


@pytest.mark.asyncio
async def test_process_signal_skips_when_no_chain() -> None:
    service, repo, producer = _service(chain=None)

    verdicts = await service.process_signal(_signal(value=0.9), uuid4(), None)

    assert verdicts == []
    assert repo.created == []
    assert producer.events == []


@pytest.mark.asyncio
async def test_process_signal_escalates_when_policy_missing() -> None:
    service, repo, _producer = _service(chain=_chain(), policy=None, binding=None)

    verdicts = await service.process_signal(_signal(value=0.9), uuid4(), None)

    assert len(verdicts) == 1
    assert verdicts[0].verdict_type is VerdictType.ESCALATE_TO_HUMAN
    assert "policy" in verdicts[0].rationale.lower()
    assert repo.created[0].policy_id is None


@pytest.mark.asyncio
async def test_process_signal_drops_when_rate_limited() -> None:
    binding = SimpleNamespace(policy_id=uuid4())
    service, repo, producer = _service(
        chain=_chain(),
        policy=_policy(binding),
        binding=binding,
        redis_allowed=False,
    )

    verdicts = await service.process_signal(_signal(value=0.9), uuid4(), None)

    assert verdicts == []
    assert repo.created == []
    assert producer.events == []


@pytest.mark.asyncio
async def test_process_signal_escalates_when_judge_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = SimpleNamespace(policy_id=uuid4())
    service, repo, _producer = _service(
        chain=_chain(),
        policy=_policy(binding),
        binding=binding,
        timeout=0,
    )

    async def _never_returns(*, judge_fqn, signal, policy):
        del judge_fqn, signal, policy
        await pytest.importorskip("asyncio").sleep(0.01)
        return {"verdict_type": "COMPLIANT", "rationale": "late", "evidence": {}}

    monkeypatch.setattr(service, "_invoke_judge", _never_returns)

    verdicts = await service.process_signal(_signal(value=0.9), uuid4(), None)

    assert len(verdicts) == 1
    assert verdicts[0].verdict_type is VerdictType.ESCALATE_TO_HUMAN
    assert verdicts[0].rationale == "judge unavailable"
    assert repo.created[0].verdict_type is VerdictType.ESCALATE_TO_HUMAN
