from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from platform.agentops.events import AgentOpsEventType, GovernanceEventPublisher
from platform.agentops.models import CiCdGateResult
from platform.agentops.repository import AgentOpsRepository
from platform.agentops.schemas import CiCdGateResultResponse
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class GateVerdict:
    passed: bool
    detail: dict[str, Any]
    remediation: str | None


class CiCdGate:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        governance_publisher: GovernanceEventPublisher | None,
        trust_service: Any | None,
        eval_suite_service: Any | None,
        policy_service: Any | None,
        regression_provider: Callable[[str, UUID, UUID], Awaitable[list[Any]]],
    ) -> None:
        self.repository = repository
        self.governance_publisher = governance_publisher
        self.trust_service = trust_service
        self.eval_suite_service = eval_suite_service
        self.policy_service = policy_service
        self.regression_provider = regression_provider

    async def evaluate(
        self,
        *,
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
        requested_by: UUID,
    ) -> CiCdGateResultResponse:
        started_at = time.perf_counter()
        gates = await asyncio.gather(
            self._policy_gate(agent_fqn, revision_id, workspace_id),
            self._evaluation_gate(agent_fqn, workspace_id),
            self._certification_gate(agent_fqn, revision_id),
            self._regression_gate(agent_fqn, revision_id, workspace_id),
            self._trust_gate(agent_fqn, workspace_id),
        )
        (
            policy_gate,
            evaluation_gate,
            certification_gate,
            regression_gate,
            trust_gate,
        ) = gates
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        overall_passed = all(
            gate.passed
            for gate in (
                policy_gate,
                evaluation_gate,
                certification_gate,
                regression_gate,
                trust_gate,
            )
        )
        persisted = await self.repository.create_gate_result(
            CiCdGateResult(
                agent_fqn=agent_fqn,
                workspace_id=workspace_id,
                revision_id=revision_id,
                requested_by=requested_by,
                overall_passed=overall_passed,
                policy_gate_passed=policy_gate.passed,
                policy_gate_detail=policy_gate.detail,
                policy_gate_remediation=policy_gate.remediation,
                evaluation_gate_passed=evaluation_gate.passed,
                evaluation_gate_detail=evaluation_gate.detail,
                evaluation_gate_remediation=evaluation_gate.remediation,
                certification_gate_passed=certification_gate.passed,
                certification_gate_detail=certification_gate.detail,
                certification_gate_remediation=certification_gate.remediation,
                regression_gate_passed=regression_gate.passed,
                regression_gate_detail=regression_gate.detail,
                regression_gate_remediation=regression_gate.remediation,
                trust_tier_gate_passed=trust_gate.passed,
                trust_tier_gate_detail=trust_gate.detail,
                trust_tier_gate_remediation=trust_gate.remediation,
                evaluation_duration_ms=duration_ms,
            )
        )
        response = CiCdGateResultResponse.model_validate(persisted)
        if self.governance_publisher is not None:
            await self.governance_publisher.record(
                AgentOpsEventType.gate_checked.value,
                agent_fqn,
                workspace_id,
                payload={
                    "revision_id": str(revision_id),
                    "overall_passed": overall_passed,
                    "duration_ms": duration_ms,
                    "policy_gate_passed": policy_gate.passed,
                    "evaluation_gate_passed": evaluation_gate.passed,
                    "certification_gate_passed": certification_gate.passed,
                    "regression_gate_passed": regression_gate.passed,
                    "trust_tier_gate_passed": trust_gate.passed,
                },
                actor=requested_by,
                revision_id=revision_id,
            )
        return response

    async def _policy_gate(
        self,
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
    ) -> GateVerdict:
        if self.policy_service is None:
            return GateVerdict(
                False,
                {"reason": "policy_service_unavailable"},
                "Restore policy service",
            )
        result = await self.policy_service.evaluate_conformance(
            agent_fqn, revision_id, workspace_id
        )
        detail = _as_mapping(result)
        passed = bool(detail.get("passed", False))
        remediation = None if passed else "Resolve policy violations before deployment."
        return GateVerdict(passed, detail, remediation)

    async def _evaluation_gate(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> GateVerdict:
        if self.eval_suite_service is None:
            return GateVerdict(
                False,
                {"reason": "evaluation_service_unavailable"},
                "Restore evaluation service",
            )
        result = await self.eval_suite_service.get_latest_agent_score(agent_fqn, workspace_id)
        if result is None:
            return GateVerdict(
                False,
                {"reason": "missing_evaluation"},
                "Run a fresh evaluation before deployment.",
            )
        detail = _as_mapping(result)
        if "passed" not in detail:
            aggregate_score = float(detail.get("aggregate_score", 0.0))
            threshold = float(detail.get("threshold", 0.8))
            detail["aggregate_score"] = aggregate_score
            detail["threshold"] = threshold
            detail["passed"] = aggregate_score >= threshold
        passed = bool(detail["passed"])
        remediation = None if passed else "Increase evaluation score above the release threshold."
        return GateVerdict(passed, detail, remediation)

    async def _certification_gate(
        self,
        agent_fqn: str,
        revision_id: UUID,
    ) -> GateVerdict:
        if self.trust_service is None:
            return GateVerdict(
                False,
                {"reason": "trust_service_unavailable"},
                "Restore trust service",
            )
        result = await self.trust_service.is_agent_certified(agent_fqn, revision_id)
        detail = _as_mapping(result)
        status = str(detail.get("status", detail.get("certified", result))).lower()
        passed = status in {"active", "true", "1"} or result is True
        remediation = None if passed else "Renew or activate certification before deployment."
        return GateVerdict(passed, detail, remediation)

    async def _regression_gate(
        self,
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
    ) -> GateVerdict:
        alerts = await self.regression_provider(agent_fqn, revision_id, workspace_id)
        detail = {
            "active_alert_count": len(alerts),
            "alerts": [_as_mapping(alert) for alert in alerts],
        }
        passed = len(alerts) == 0
        remediation = None if passed else "Resolve active regression alerts before deployment."
        return GateVerdict(passed, detail, remediation)

    async def _trust_gate(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> GateVerdict:
        if self.trust_service is None:
            return GateVerdict(
                False,
                {"reason": "trust_service_unavailable"},
                "Restore trust service",
            )
        result = await self.trust_service.get_agent_trust_tier(agent_fqn, workspace_id)
        detail = _as_mapping(result)
        tier = _coerce_tier(detail.get("tier", result))
        detail["tier"] = tier
        passed = tier >= 1
        remediation = None if passed else "Raise trust tier above 0 before deployment."
        return GateVerdict(passed, detail, remediation)


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, bool):
        return {"value": value}
    if isinstance(value, (int, float)):
        return {"aggregate_score": float(value)}
    if hasattr(value, "model_dump"):
        return dict(value.model_dump())
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {"value": value}


def _coerce_tier(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    mapping = {"untrusted": 0, "provisional": 1, "certified": 3}
    return mapping.get(str(value).lower(), 0)
