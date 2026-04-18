from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.governance.models import VerdictType
from platform.governance.services.judge_service import JudgeService
from platform.governance.services.pipeline_config import ChainConfig
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.auth_support import RecordingProducer
from tests.unit.governance.test_judge_service import (
    FleetPolicyRepoStub,
    PipelineStub,
    PolicyRepoStub,
    RedisStub,
    RepoStub,
)


def _layered_chain() -> ChainConfig:
    return ChainConfig(
        observer_fqns=["platform:observer"],
        judge_fqns=["platform:judge-1", "platform:judge-2"],
        enforcer_fqns=["platform:enforcer"],
        policy_binding_ids=[str(uuid4())],
        verdict_to_action_mapping={"VIOLATION": "block"},
        scope="fleet",
    )


def _service() -> tuple[JudgeService, RepoStub]:
    binding = SimpleNamespace(policy_id=uuid4())
    policy = SimpleNamespace(
        id=binding.policy_id,
        current_version=SimpleNamespace(rules={"threshold": 0.8}),
    )
    repo = RepoStub()
    service = JudgeService(
        repository=repo,  # type: ignore[arg-type]
        pipeline_config=PipelineStub(_layered_chain()),  # type: ignore[arg-type]
        fleet_policy_repo=FleetPolicyRepoStub(binding),  # type: ignore[arg-type]
        policy_repo=PolicyRepoStub(policy),  # type: ignore[arg-type]
        settings=PlatformSettings(),
        producer=RecordingProducer(),
        redis_client=RedisStub(),  # type: ignore[arg-type]
    )
    return service, repo


def _signal(judge_verdicts: dict[str, object]) -> EventEnvelope:
    return EventEnvelope(
        event_type="monitor.alert",
        source="pytest",
        correlation_context=CorrelationContext(correlation_id=uuid4(), fleet_id=uuid4()),
        payload={
            "observer_fqn": "platform:observer",
            "value": 0.4,
            "judge_verdicts": judge_verdicts,
        },
    )


@pytest.mark.asyncio
async def test_layered_chain_runs_second_judge_after_compliant() -> None:
    service, repo = _service()

    verdicts = await service.process_signal(
        _signal(
            {
                "platform:judge-1": {
                    "verdict_type": "COMPLIANT",
                    "rationale": "first pass",
                    "evidence": {},
                },
                "platform:judge-2": {
                    "verdict_type": "WARNING",
                    "rationale": "second pass",
                    "evidence": {},
                },
            }
        ),
        uuid4(),
        None,
    )

    assert [item.verdict_type for item in verdicts] == [
        VerdictType.COMPLIANT,
        VerdictType.WARNING,
    ]
    assert [item.judge_agent_fqn for item in repo.created] == [
        "platform:judge-1",
        "platform:judge-2",
    ]


@pytest.mark.asyncio
async def test_layered_chain_stops_on_violation() -> None:
    service, repo = _service()

    verdicts = await service.process_signal(
        _signal(
            {
                "platform:judge-1": {
                    "verdict_type": "VIOLATION",
                    "rationale": "stop now",
                    "evidence": {},
                },
                "platform:judge-2": {
                    "verdict_type": "WARNING",
                    "rationale": "should not run",
                    "evidence": {},
                },
            }
        ),
        uuid4(),
        None,
    )

    assert [item.verdict_type for item in verdicts] == [VerdictType.VIOLATION]
    assert [item.judge_agent_fqn for item in repo.created] == ["platform:judge-1"]


@pytest.mark.asyncio
async def test_layered_chain_stops_on_escalation() -> None:
    service, repo = _service()

    verdicts = await service.process_signal(
        _signal(
            {
                "platform:judge-1": {
                    "verdict_type": "ESCALATE_TO_HUMAN",
                    "rationale": "manual review",
                    "evidence": {},
                },
                "platform:judge-2": {
                    "verdict_type": "WARNING",
                    "rationale": "should not run",
                    "evidence": {},
                },
            }
        ),
        uuid4(),
        None,
    )

    assert [item.verdict_type for item in verdicts] == [VerdictType.ESCALATE_TO_HUMAN]
    assert [item.judge_agent_fqn for item in repo.created] == ["platform:judge-1"]
