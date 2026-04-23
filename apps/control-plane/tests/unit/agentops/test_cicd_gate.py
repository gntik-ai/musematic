from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from platform.agentops.cicd.gate import CiCdGate, GateVerdict, _as_mapping, _coerce_tier
from platform.agentops.models import CiCdGateResult
from platform.agentops.service import AgentOpsService
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest


class _RepositoryStub:
    def __init__(self, *, active_alerts: list[Any] | None = None) -> None:
        self.active_alerts = active_alerts or []
        self.persisted_gate_results: list[CiCdGateResult] = []

    async def create_gate_result(self, result_model: CiCdGateResult) -> CiCdGateResult:
        now = datetime.now(UTC)
        if getattr(result_model, "id", None) is None:
            result_model.id = uuid4()
        result_model.created_at = now
        result_model.updated_at = now
        result_model.evaluated_at = now
        self.persisted_gate_results.append(result_model)
        return result_model

    async def list_regression_alerts(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        status: str | None = None,
        new_revision_id: UUID | None = None,
    ) -> tuple[list[Any], str | None]:
        del agent_fqn, workspace_id, cursor, limit, new_revision_id
        if status == "active":
            return self.active_alerts, None
        return [], None


class _GovernancePublisherStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def record(
        self,
        event_type: str,
        agent_fqn: str,
        workspace_id: UUID,
        **kwargs: Any,
    ) -> None:
        self.calls.append(
            {
                "event_type": event_type,
                "agent_fqn": agent_fqn,
                "workspace_id": workspace_id,
                **kwargs,
            }
        )


class _PolicyServiceStub:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls = 0

    async def evaluate_conformance(
        self,
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
    ) -> Any:
        del agent_fqn, revision_id, workspace_id
        self.calls += 1
        return self.result


class _EvalServiceStub:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls = 0

    async def get_latest_agent_score(self, agent_fqn: str, workspace_id: UUID) -> Any:
        del agent_fqn, workspace_id
        self.calls += 1
        return self.result


class _TrustServiceStub:
    def __init__(self, *, certification: Any, tier: Any) -> None:
        self.certification = certification
        self.tier = tier
        self.certification_calls = 0
        self.tier_calls = 0

    async def is_agent_certified(self, agent_fqn: str, revision_id: UUID) -> Any:
        del agent_fqn, revision_id
        self.certification_calls += 1
        return self.certification

    async def get_agent_trust_tier(self, agent_fqn: str, workspace_id: UUID) -> Any:
        del agent_fqn, workspace_id
        self.tier_calls += 1
        return self.tier


@pytest.mark.asyncio
async def test_cicd_gate_all_passes_and_persists_result() -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    requested_by = uuid4()
    repository = _RepositoryStub()
    governance = _GovernancePublisherStub()
    gate = CiCdGate(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=governance,  # type: ignore[arg-type]
        trust_service=_TrustServiceStub(
            certification={"status": "active"},
            tier={"tier": 2, "score": 0.92},
        ),
        eval_suite_service=_EvalServiceStub(
            {"aggregate_score": 0.91, "threshold": 0.8, "passed": True}
        ),
        policy_service=_PolicyServiceStub({"passed": True, "violations": []}),
        regression_provider=lambda *args: _resolved([]),
    )

    result = await gate.evaluate(
        agent_fqn="finance:agent",
        revision_id=revision_id,
        workspace_id=workspace_id,
        requested_by=requested_by,
    )

    assert result.overall_passed is True
    assert result.policy_gate_passed is True
    assert result.evaluation_gate_passed is True
    assert result.certification_gate_passed is True
    assert result.regression_gate_passed is True
    assert result.trust_tier_gate_passed is True
    assert result.evaluation_duration_ms >= 0
    assert len(repository.persisted_gate_results) == 1
    assert repository.persisted_gate_results[0].overall_passed is True
    assert governance.calls[0]["event_type"] == "agentops.gate.checked"
    assert governance.calls[0]["payload"]["overall_passed"] is True


class _CallTracker:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def run(self, result: Any) -> Any:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0)
        self.active -= 1
        return result


@pytest.mark.asyncio
async def test_cicd_gate_evaluates_shared_dependencies_sequentially() -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    requested_by = uuid4()
    tracker = _CallTracker()
    repository = _RepositoryStub()

    class _TrackedPolicyService(_PolicyServiceStub):
        async def evaluate_conformance(
            self,
            agent_fqn: str,
            revision_id: UUID,
            workspace_id: UUID,
        ) -> Any:
            del agent_fqn, revision_id, workspace_id
            self.calls += 1
            return await tracker.run(self.result)

    class _TrackedEvalService(_EvalServiceStub):
        async def get_latest_agent_score(self, agent_fqn: str, workspace_id: UUID) -> Any:
            del agent_fqn, workspace_id
            self.calls += 1
            return await tracker.run(self.result)

    class _TrackedTrustService(_TrustServiceStub):
        async def is_agent_certified(self, agent_fqn: str, revision_id: UUID) -> Any:
            del agent_fqn, revision_id
            self.certification_calls += 1
            return await tracker.run(self.certification)

        async def get_agent_trust_tier(self, agent_fqn: str, workspace_id: UUID) -> Any:
            del agent_fqn, workspace_id
            self.tier_calls += 1
            return await tracker.run(self.tier)

    async def regression_provider(
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
    ) -> list[Any]:
        del agent_fqn, revision_id, workspace_id
        return await tracker.run([])

    gate = CiCdGate(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=None,
        trust_service=_TrackedTrustService(
            certification={"status": "active"},
            tier={"tier": 2, "score": 0.92},
        ),
        eval_suite_service=_TrackedEvalService(
            {"aggregate_score": 0.91, "threshold": 0.8, "passed": True}
        ),
        policy_service=_TrackedPolicyService({"passed": True, "violations": []}),
        regression_provider=regression_provider,
    )

    result = await gate.evaluate(
        agent_fqn="finance:agent",
        revision_id=revision_id,
        workspace_id=workspace_id,
        requested_by=requested_by,
    )

    assert result.overall_passed is True
    assert tracker.max_active == 1


@pytest.mark.asyncio
async def test_cicd_gate_serializes_datetime_details_before_persisting() -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    requested_by = uuid4()
    repository = _RepositoryStub()
    timestamp = datetime.now(UTC)
    trust_service = _TrustServiceStub(
        certification={"status": "active", "activated_at": timestamp},
        tier={"tier": 2, "score": 0.92, "evaluated_at": timestamp},
    )
    gate = CiCdGate(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=None,
        trust_service=trust_service,
        eval_suite_service=_EvalServiceStub(
            {"aggregate_score": 0.91, "threshold": 0.8, "passed": True}
        ),
        policy_service=_PolicyServiceStub({"passed": True, "violations": []}),
        regression_provider=lambda *args: _resolved([]),
    )

    result = await gate.evaluate(
        agent_fqn="finance:agent",
        revision_id=revision_id,
        workspace_id=workspace_id,
        requested_by=requested_by,
    )

    assert result.overall_passed is True
    persisted = repository.persisted_gate_results[0]
    assert persisted.certification_gate_detail["activated_at"] == timestamp.isoformat()
    assert persisted.trust_tier_gate_detail["evaluated_at"] == timestamp.isoformat()


@pytest.mark.asyncio
async def test_cicd_gate_failure_does_not_short_circuit_and_service_returns_summary() -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    requested_by = uuid4()
    repository = _RepositoryStub()
    governance = _GovernancePublisherStub()
    policy_service = _PolicyServiceStub({"passed": True, "violations": []})
    eval_service = _EvalServiceStub({"aggregate_score": 0.87, "threshold": 0.8, "passed": True})
    trust_service = _TrustServiceStub(
        certification={"status": "expired"},
        tier={"tier": 2, "score": 0.78},
    )
    regression_calls: list[tuple[str, UUID, UUID]] = []

    async def regression_provider(
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
    ) -> list[Any]:
        regression_calls.append((agent_fqn, revision_id, workspace_id))
        return []

    gate = CiCdGate(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=governance,  # type: ignore[arg-type]
        trust_service=trust_service,
        eval_suite_service=eval_service,
        policy_service=policy_service,
        regression_provider=regression_provider,
    )

    result = await gate.evaluate(
        agent_fqn="finance:agent",
        revision_id=revision_id,
        workspace_id=workspace_id,
        requested_by=requested_by,
    )

    assert result.overall_passed is False
    assert result.certification_gate_passed is False
    assert result.certification_gate_remediation is not None
    assert policy_service.calls == 1
    assert eval_service.calls == 1
    assert trust_service.certification_calls == 1
    assert trust_service.tier_calls == 1
    assert regression_calls == [("finance:agent", revision_id, workspace_id)]

    service = AgentOpsService(
        repository=repository,  # type: ignore[arg-type]
        event_publisher=SimpleNamespace(),
        governance_publisher=governance,  # type: ignore[arg-type]
        trust_service=trust_service,
        eval_suite_service=eval_service,
        policy_service=policy_service,
        workflow_service=None,
        registry_service=None,
    )
    summary = await service.run_gate_check(
        "finance:agent",
        revision_id,
        workspace_id,
        requested_by,
    )

    assert summary.overall_passed is False
    assert summary.summary["certification_gate_passed"] is False
    assert summary.summary["policy_gate_passed"] is True


@pytest.mark.asyncio
async def test_cicd_gate_multi_failure_populates_failure_details_and_remediation() -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    requested_by = uuid4()
    repository = _RepositoryStub(active_alerts=[{"dimension": "quality"}])
    gate = CiCdGate(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=None,
        trust_service=_TrustServiceStub(
            certification={"status": "revoked"},
            tier={"tier": 0, "score": 0.21},
        ),
        eval_suite_service=_EvalServiceStub(
            {"aggregate_score": 0.62, "threshold": 0.8, "passed": False}
        ),
        policy_service=_PolicyServiceStub(
            {
                "passed": False,
                "violations": [{"policy_id": "safety", "rule_id": "R1"}],
            }
        ),
        regression_provider=lambda *args: _resolved(repository.active_alerts),
    )

    result = await gate.evaluate(
        agent_fqn="finance:agent",
        revision_id=revision_id,
        workspace_id=workspace_id,
        requested_by=requested_by,
    )

    assert result.overall_passed is False
    assert result.policy_gate_passed is False
    assert result.evaluation_gate_passed is False
    assert result.certification_gate_passed is False
    assert result.regression_gate_passed is False
    assert result.trust_tier_gate_passed is False
    assert result.policy_gate_detail["violations"][0]["policy_id"] == "safety"
    assert result.evaluation_gate_detail["aggregate_score"] == 0.62
    assert result.certification_gate_detail["status"] == "revoked"
    assert result.regression_gate_detail["active_alert_count"] == 1
    assert result.trust_tier_gate_detail["tier"] == 0
    assert result.policy_gate_remediation is not None
    assert result.evaluation_gate_remediation is not None
    assert result.certification_gate_remediation is not None
    assert result.regression_gate_remediation is not None
    assert result.trust_tier_gate_remediation is not None


@pytest.mark.asyncio
async def test_cicd_gate_private_branches_cover_missing_services_and_inferred_scores() -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    gate = CiCdGate(
        repository=_RepositoryStub(),  # type: ignore[arg-type]
        governance_publisher=None,
        trust_service=None,
        eval_suite_service=_EvalServiceStub(0.7),
        policy_service=None,
        regression_provider=lambda *args: _resolved([{"id": "alert"}]),
    )

    policy = await gate._policy_gate("finance:agent", revision_id, workspace_id)
    evaluation = await gate._evaluation_gate("finance:agent", workspace_id)
    certification = await gate._certification_gate("finance:agent", revision_id)
    regression = await gate._regression_gate("finance:agent", revision_id, workspace_id)
    trust = await gate._trust_gate("finance:agent", workspace_id)

    assert policy == GateVerdict(
        False,
        {"reason": "policy_service_unavailable"},
        "Restore policy service",
    )
    assert evaluation.passed is False
    assert evaluation.detail["threshold"] == 0.8
    assert certification.remediation == "Restore trust service"
    assert regression.detail["active_alert_count"] == 1
    assert trust.detail["reason"] == "trust_service_unavailable"

    gate.eval_suite_service = _EvalServiceStub(None)
    missing_evaluation = await gate._evaluation_gate("finance:agent", workspace_id)
    gate.trust_service = _TrustServiceStub(certification=True, tier=False)
    certification_true = await gate._certification_gate("finance:agent", revision_id)
    trust_false = await gate._trust_gate("finance:agent", workspace_id)

    assert missing_evaluation.detail["reason"] == "missing_evaluation"
    assert certification_true.passed is True
    assert trust_false.passed is False


def test_cicd_gate_helper_functions_cover_mapping_and_tier_coercion() -> None:
    model = SimpleNamespace(model_dump=lambda: {"passed": True})

    assert _as_mapping(None) == {}
    assert _as_mapping({"a": 1}) == {"a": 1}
    assert _as_mapping(True) == {"value": True}
    assert _as_mapping(0.8) == {"aggregate_score": 0.8}
    assert _as_mapping(model) == {"passed": True}
    assert _as_mapping(SimpleNamespace(status="active")) == {"status": "active"}
    assert _coerce_tier(True) == 1
    assert _coerce_tier(2.9) == 2
    assert _coerce_tier("certified") == 3


async def _resolved(value: Any) -> Any:
    return value
