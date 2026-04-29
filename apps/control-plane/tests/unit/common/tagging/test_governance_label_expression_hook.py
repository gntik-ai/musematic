from __future__ import annotations

from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.governance.models import VerdictType
from platform.governance.services.judge_service import JudgeService
from platform.governance.services.pipeline_config import ChainConfig
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class _PipelineConfig:
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
            judge_fqns=["platform:governance-judge"],
            enforcer_fqns=[],
            policy_binding_ids=[str(self.policy_id)],
            verdict_to_action_mapping={},
            scope="workspace",
        )


class _PolicyRepo:
    def __init__(self, policy: object) -> None:
        self.policy = policy

    async def get_by_id(self, policy_id: UUID) -> object:
        del policy_id
        return self.policy


class _FleetPolicyRepo:
    async def get_by_id(self, binding_id: UUID, fleet_id: UUID) -> None:
        del binding_id, fleet_id
        return None


class _Redis:
    async def check_rate_limit(
        self,
        namespace: str,
        key: str,
        limit: int,
        window_ms: int,
    ) -> object:
        del namespace, key, limit, window_ms
        return SimpleNamespace(allowed=True)


class _Cache:
    def __init__(self) -> None:
        self.calls: list[tuple[object, int, str | None]] = []

    async def get_or_compile(self, policy_id: object, version: int, expression: str | None) -> str:
        self.calls.append((policy_id, version, expression))
        return "compiled"


class _Evaluator:
    def __init__(self, result: bool) -> None:
        self.result = result
        self.calls: list[tuple[object, dict[str, str]]] = []

    async def evaluate(self, ast: object, target_labels: dict[str, str]) -> bool:
        self.calls.append((ast, target_labels))
        return self.result


class _JudgeService(JudgeService):
    def __init__(
        self,
        *,
        policy: object,
        cache: _Cache,
        evaluator: _Evaluator,
    ) -> None:
        super().__init__(
            repository=object(),
            pipeline_config=_PipelineConfig(policy.id),
            fleet_policy_repo=_FleetPolicyRepo(),
            policy_repo=_PolicyRepo(policy),
            settings=SimpleNamespace(
                governance=SimpleNamespace(
                    judge_timeout_seconds=1,
                    rate_limit_per_observer_per_minute=10,
                )
            ),
            producer=None,
            redis_client=_Redis(),
            label_expression_cache=cache,
            label_expression_evaluator=evaluator,
        )
        self.persisted = 0

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
            "rationale": "matched",
            "evidence": {},
        }

    async def _persist_verdict(self, **kwargs: object) -> object:
        del kwargs
        self.persisted += 1
        return SimpleNamespace(id=uuid4(), verdict_type=VerdictType.COMPLIANT)


def _policy(label_expression: str | None) -> object:
    policy_id = uuid4()
    rules = {"label_expression": label_expression} if label_expression is not None else {}
    return SimpleNamespace(
        id=policy_id,
        current_version=SimpleNamespace(version_number=7, rules=rules),
    )


def _signal(labels: dict[str, str]) -> EventEnvelope:
    return EventEnvelope(
        event_type="governance.signal",
        source="tests",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={"target": {"labels": labels}},
    )


@pytest.mark.asyncio
async def test_governance_label_expression_match_allows_policy() -> None:
    cache = _Cache()
    evaluator = _Evaluator(True)
    policy = _policy("env=production")
    service = _JudgeService(policy=policy, cache=cache, evaluator=evaluator)

    verdicts = await service.process_signal(_signal({"env": "production"}), None, uuid4())

    assert len(verdicts) == 1
    assert service.persisted == 1
    assert cache.calls == [(policy.id, 7, "env=production")]
    assert evaluator.calls == [("compiled", {"env": "production"})]


@pytest.mark.asyncio
async def test_governance_label_expression_miss_skips_policy() -> None:
    cache = _Cache()
    evaluator = _Evaluator(False)
    service = _JudgeService(policy=_policy("env=production"), cache=cache, evaluator=evaluator)

    verdicts = await service.process_signal(_signal({"env": "staging"}), None, uuid4())

    assert verdicts == []
    assert service.persisted == 0
    assert len(cache.calls) == 1
    assert evaluator.calls == [("compiled", {"env": "staging"})]


@pytest.mark.asyncio
async def test_policy_without_label_expression_has_zero_evaluator_cost() -> None:
    cache = _Cache()
    evaluator = _Evaluator(True)
    service = _JudgeService(policy=_policy(None), cache=cache, evaluator=evaluator)

    verdicts = await service.process_signal(_signal({"env": "production"}), None, uuid4())

    assert len(verdicts) == 1
    assert cache.calls == []
    assert evaluator.calls == []
