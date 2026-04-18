from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.governance.models import GovernanceVerdict, VerdictType
from platform.governance.services.judge_service import JudgeService
from platform.governance.services.pipeline_config import ChainConfig
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from tests.auth_oauth_support import RateLimitResultStub
from tests.auth_support import RecordingProducer


class RepoStub:
    async def create_verdict(self, verdict: GovernanceVerdict) -> GovernanceVerdict:
        verdict.id = uuid4()
        verdict.created_at = datetime.now(UTC)
        verdict.updated_at = verdict.created_at
        return verdict


class PipelineStub:
    async def resolve_chain(self, fleet_id, workspace_id):
        del fleet_id, workspace_id
        return None


class FleetPolicyRepoStub:
    def __init__(self, binding=None) -> None:
        self.binding = binding
        self.calls: list[tuple[UUID, UUID]] = []

    async def get_by_id(self, binding_id, fleet_id):
        self.calls.append((binding_id, fleet_id))
        return self.binding


class PolicyRepoStub:
    def __init__(self, policy=None) -> None:
        self.policy = policy
        self.calls: list[UUID] = []

    async def get_by_id(self, policy_id):
        self.calls.append(policy_id)
        return self.policy


class RedisStub:
    async def check_rate_limit(self, scope: str, key: str, limit: int, window_ms: int):
        del scope, key, limit, window_ms
        return RateLimitResultStub(allowed=True)


def _service(*, binding=None, policy=None) -> JudgeService:
    return JudgeService(
        repository=RepoStub(),  # type: ignore[arg-type]
        pipeline_config=PipelineStub(),  # type: ignore[arg-type]
        fleet_policy_repo=FleetPolicyRepoStub(binding),  # type: ignore[arg-type]
        policy_repo=PolicyRepoStub(policy),  # type: ignore[arg-type]
        settings=PlatformSettings(),
        producer=RecordingProducer(),
        redis_client=RedisStub(),  # type: ignore[arg-type]
    )


def _verdict() -> GovernanceVerdict:
    verdict = GovernanceVerdict(
        id=uuid4(),
        judge_agent_fqn="platform:judge",
        verdict_type=VerdictType.VIOLATION,
        policy_id=uuid4(),
        evidence={"target_agent_fqn": "agent:target"},
        rationale="matched",
        recommended_action=None,
        source_event_id=uuid4(),
        fleet_id=uuid4(),
        workspace_id=uuid4(),
    )
    verdict.created_at = datetime.now(UTC)
    verdict.updated_at = verdict.created_at
    return verdict


def _signal(
    payload: dict[str, object] | None = None,
    *,
    agent_fqn: str | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_type="monitor.alert",
        source="pytest",
        correlation_context=CorrelationContext(
            correlation_id=uuid4(),
            agent_fqn=agent_fqn,
        ),
        payload=dict(payload or {}),
    )


@pytest.mark.asyncio
async def test_process_fleet_anomaly_signal_reports_processed_and_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    fleet_id = uuid4()
    workspace_id = uuid4()
    verdict = _verdict()
    calls: list[tuple[EventEnvelope, UUID, UUID | None]] = []

    async def _processed(envelope: EventEnvelope, resolved_fleet_id: UUID, resolved_workspace_id):
        calls.append((envelope, resolved_fleet_id, resolved_workspace_id))
        return [verdict]

    monkeypatch.setattr(service, "process_signal", _processed)
    result = await service.process_fleet_anomaly_signal(
        fleet_id,
        SimpleNamespace(
            workspace_id=workspace_id,
            observer_fqns=["observer:one"],
            judge_fqns=["judge:one"],
            enforcer_fqns=["enforcer:one"],
            policy_binding_ids=[],
            verdict_to_action_mapping={},
        ),
        {"event_type": "monitor.alert", "agent_fqn": "observer:one"},
    )

    async def _skipped(envelope: EventEnvelope, resolved_fleet_id: UUID, resolved_workspace_id):
        calls.append((envelope, resolved_fleet_id, resolved_workspace_id))
        return []

    monkeypatch.setattr(service, "process_signal", _skipped)
    skipped = await service.process_fleet_anomaly_signal(
        fleet_id,
        SimpleNamespace(
            observer_fqns=[],
            judge_fqns=[],
            enforcer_fqns=[],
            policy_binding_ids=[],
            verdict_to_action_mapping={},
        ),
        {"signal_value": 0.7},
    )

    assert result == {
        "status": "processed",
        "fleet_id": str(fleet_id),
        "verdict_ids": [str(verdict.id)],
        "scope": "workspace",
    }
    assert skipped["status"] == "skipped"
    assert skipped["scope"] == "fleet"
    assert calls[0][0].correlation_context.workspace_id == workspace_id


@pytest.mark.asyncio
async def test_resolve_policy_and_invoke_judge_cover_helper_paths() -> None:
    binding_id = uuid4()
    policy_id = uuid4()
    binding = SimpleNamespace(policy_id=policy_id)
    policy = SimpleNamespace(
        id=policy_id,
        current_version=SimpleNamespace(rules={"conditions": {"threshold": 0.6}}),
    )
    service = _service(binding=binding, policy=policy)

    resolved_fleet_policy = await service._resolve_policy(
        ChainConfig(
            observer_fqns=[],
            judge_fqns=[],
            enforcer_fqns=[],
            policy_binding_ids=["invalid", str(binding_id)],
            verdict_to_action_mapping={},
            scope="fleet",
        ),
        uuid4(),
    )
    resolved_workspace_policy = await service._resolve_policy(
        ChainConfig(
            observer_fqns=[],
            judge_fqns=[],
            enforcer_fqns=[],
            policy_binding_ids=["invalid", str(policy_id)],
            verdict_to_action_mapping={},
            scope="workspace",
        ),
        None,
    )
    missing_policy = await service._resolve_policy(
        ChainConfig(
            observer_fqns=[],
            judge_fqns=[],
            enforcer_fqns=[],
            policy_binding_ids=["invalid"],
            verdict_to_action_mapping={},
            scope="workspace",
        ),
        None,
    )

    envelope = _signal(
        {
            "judge_verdicts": {
                "judge:one": {"verdict_type": "WARNING", "rationale": "manual", "evidence": {}},
                "judge:two": "ESCALATE_TO_HUMAN",
            }
        }
    )
    direct_override = await service._invoke_judge(
        judge_fqn="judge:one",
        signal=envelope,
        policy=policy,
    )
    string_override = await service._invoke_judge(
        judge_fqn="judge:two",
        signal=envelope,
        policy=policy,
    )
    single_override = await service._invoke_judge(
        judge_fqn="judge:three",
        signal=_signal(
            {
                "judge_verdict": {
                    "verdict_type": "COMPLIANT",
                    "rationale": "ok",
                    "evidence": {},
                }
            }
        ),
        policy=policy,
    )
    computed = await service._invoke_judge(
        judge_fqn="judge:four",
        signal=_signal({"score": 0.9}),
        policy=policy,
    )
    escalated = await service._invoke_judge(
        judge_fqn="judge:five",
        signal=_signal({"value": "bad"}),
        policy=SimpleNamespace(current_version=SimpleNamespace(rules={})),
    )

    assert resolved_fleet_policy is policy
    assert resolved_workspace_policy is policy
    assert missing_policy is None
    assert direct_override["verdict_type"] == "WARNING"
    assert string_override["verdict_type"] == "ESCALATE_TO_HUMAN"
    assert single_override["verdict_type"] == "COMPLIANT"
    assert computed["verdict_type"] == VerdictType.VIOLATION.value
    assert computed["evidence"]["threshold"] == 0.6
    assert escalated["verdict_type"] == VerdictType.ESCALATE_TO_HUMAN.value


def test_judge_service_helper_methods_cover_remaining_branches() -> None:
    service = _service()
    event_id = uuid4()

    @dataclass
    class VerdictPayload:
        verdict_type: str
        rationale: str
        evidence: dict[str, object]

    normalized_dataclass = service._normalize_verdict(
        VerdictPayload("WARNING", "dataclass", {"x": 1})
    )
    normalized_dict = service._normalize_verdict(
        {"verdict": "COMPLIANT", "reasoning": "dict", "evidence": None}
    )
    invalid = service._normalize_verdict(
        {"verdict_type": "BAD", "rationale": "nope", "evidence": {}}
    )

    assert normalized_dataclass == {
        "verdict_type": "WARNING",
        "rationale": "dataclass",
        "evidence": {"x": 1},
    }
    assert normalized_dict == {
        "verdict": "COMPLIANT",
        "reasoning": "dict",
        "evidence": {},
        "verdict_type": "COMPLIANT",
        "rationale": "dict",
    }
    assert invalid is None
    assert service._observer_fqn(_signal({"agent_fqn": "  observer:two  "})) == "observer:two"
    assert service._observer_fqn(_signal(agent_fqn="observer:ctx")) == "observer:ctx"
    assert service._extract_threshold(
        SimpleNamespace(current_version=SimpleNamespace(rules={"conditions": {"threshold": 0.4}}))
    ) == 0.4
    assert (
        service._extract_threshold(
            SimpleNamespace(current_version=SimpleNamespace(rules="bad"))
        )
        is None
    )
    assert service._extract_signal_value({"signal_value": 0.5}) == 0.5
    assert service._extract_signal_value({"score": 0.6}) == 0.6
    assert service._extract_signal_value({"value": "bad"}) is None
    assert service._source_event_id(_signal({"execution_id": str(event_id)})) == event_id
    assert service._source_event_id(_signal({"signal_id": "not-a-uuid"})) is None
    assert service._uuid_or_none(event_id) == event_id
    assert service._uuid_or_none(None) is None
    assert service._uuid_or_none("invalid") is None
    original_chain = ChainConfig([], [], [], [], {}, "fleet")
    assert service._coerce_chain_config(original_chain) is original_chain
    coerced = service._coerce_chain_config(
        SimpleNamespace(
            workspace_id=uuid4(),
            observer_fqns=["observer"],
            judge_fqns=["judge"],
            enforcer_fqns=["enforcer"],
            policy_binding_ids=[event_id],
            verdict_to_action_mapping={"VIOLATION": "block"},
        )
    )
    assert coerced.scope == "workspace"
    assert coerced.policy_binding_ids == [str(event_id)]
