from __future__ import annotations

from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.common.tagging.label_expression.cache import LabelExpressionCache
from platform.common.tagging.label_expression.evaluator import LabelExpressionEvaluator
from platform.governance.models import VerdictType
from platform.governance.services.judge_service import JudgeService
from platform.governance.services.pipeline_config import ChainConfig
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class PipelineConfigStub:
    def __init__(self, policy_id: UUID) -> None:
        self.policy_id = policy_id

    async def resolve_chain(
        self,
        fleet_id: UUID | None,
        workspace_id: UUID | None,
    ) -> ChainConfig:
        del fleet_id, workspace_id
        return ChainConfig(
            observer_fqns=[],
            judge_fqns=["platform:judge"],
            enforcer_fqns=[],
            policy_binding_ids=[str(self.policy_id)],
            verdict_to_action_mapping={},
            scope="workspace",
        )


class PolicyRepoStub:
    def __init__(self, policy: object) -> None:
        self.policy = policy

    async def get_by_id(self, policy_id: UUID) -> object:
        del policy_id
        return self.policy


class FleetPolicyRepoStub:
    async def get_by_id(self, binding_id: UUID, fleet_id: UUID) -> None:
        del binding_id, fleet_id
        return None


class RedisStub:
    async def check_rate_limit(
        self,
        namespace: str,
        key: str,
        limit: int,
        window_ms: int,
    ) -> object:
        del namespace, key, limit, window_ms
        return SimpleNamespace(allowed=True)


class JudgeServiceStub(JudgeService):
    def __init__(self, policy: object) -> None:
        super().__init__(
            repository=object(),
            pipeline_config=PipelineConfigStub(policy.id),
            fleet_policy_repo=FleetPolicyRepoStub(),
            policy_repo=PolicyRepoStub(policy),
            settings=SimpleNamespace(
                governance=SimpleNamespace(
                    judge_timeout_seconds=1,
                    rate_limit_per_observer_per_minute=100,
                ),
                tagging=SimpleNamespace(
                    label_expression_lru_size=16,
                    label_expression_redis_ttl_seconds=86_400,
                ),
            ),
            producer=None,
            redis_client=RedisStub(),
            label_expression_cache=LabelExpressionCache(None, lru_size=16),
            label_expression_evaluator=LabelExpressionEvaluator(),
        )

    async def _invoke_judge(
        self,
        *,
        judge_fqn: str,
        signal: EventEnvelope,
        policy: object,
    ) -> dict[str, object]:
        del judge_fqn, signal, policy
        return {
            "verdict_type": VerdictType.COMPLIANT.value,
            "rationale": "label expression matched",
            "evidence": {},
        }

    async def _persist_verdict(self, **kwargs: object) -> object:
        del kwargs
        return SimpleNamespace(id=uuid4(), verdict_type=VerdictType.COMPLIANT)


def policy_with_expression(expression: str) -> object:
    policy_id = uuid4()
    return SimpleNamespace(
        id=policy_id,
        current_version=SimpleNamespace(
            version_number=1,
            rules={"label_expression": expression},
        ),
    )


def signal_with_labels(labels: dict[str, str]) -> EventEnvelope:
    return EventEnvelope(
        event_type="governance.signal",
        source="tagging.integration",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={"target": {"labels": labels}},
    )


@pytest.mark.parametrize(
    ("expression", "matching_labels", "missing_labels"),
    [
        ("env=production", {"env": "production"}, {"env": "staging"}),
        (
            "env=production AND tier=critical",
            {"env": "production", "tier": "critical"},
            {"env": "production"},
        ),
        (
            "NOT lifecycle=experimental",
            {},
            {"lifecycle": "experimental"},
        ),
    ],
)
async def test_policy_label_expression_controls_governance_match(
    expression: str,
    matching_labels: dict[str, str],
    missing_labels: dict[str, str],
) -> None:
    service = JudgeServiceStub(policy_with_expression(expression))

    matched = await service.process_signal(signal_with_labels(matching_labels), None, uuid4())
    missed = await service.process_signal(signal_with_labels(missing_labels), None, uuid4())

    assert len(matched) == 1
    assert missed == []
