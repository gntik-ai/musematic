from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from platform.agentops.adaptation.analyzer import AdaptationSignal, BehavioralAnalyzer
from platform.agentops.events import AgentOpsEventType, GovernanceEventPublisher
from platform.agentops.models import AdaptationProposal, AdaptationProposalStatus
from platform.agentops.repository import AgentOpsRepository
from platform.common.exceptions import NotFoundError, ValidationError
from typing import Any, cast
from uuid import UUID, uuid4

_ADJUSTMENT_MAP: dict[str, dict[str, str]] = {
    "quality_trend": {
        "target": "context_profile",
        "action": "refresh_context_profile",
        "summary": "Refresh context profile and retrieval defaults to recover quality drift.",
    },
    "cost_quality": {
        "target": "model_params",
        "action": "optimize_model_params",
        "summary": "Tune model parameters to reduce cost per quality point.",
    },
    "failure_pattern": {
        "target": "approach_text",
        "action": "revise_approach_text",
        "summary": "Revise approach text and recovery instructions for recurring failures.",
    },
    "tool_utilization": {
        "target": "tool_selection",
        "action": "rebalance_tool_selection",
        "summary": "Simplify and reprioritize tool selection based on actual utilization.",
    },
    "convergence_regression": {
        "target": "self_correction_strategy",
        "action": "stabilize_convergence_strategy",
        "summary": "Adjust self-correction guidance to reduce convergence loops.",
    },
}


class AdaptationPipeline:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        analyzer: BehavioralAnalyzer,
        governance_publisher: GovernanceEventPublisher | None,
        registry_service: Any | None,
        eval_suite_service: Any | None,
        proposal_ttl_hours: int = 168,
        observation_window_hours: int = 72,
    ) -> None:
        self.repository = repository
        self.analyzer = analyzer
        self.governance_publisher = governance_publisher
        self.registry_service = registry_service
        self.eval_suite_service = eval_suite_service
        self.proposal_ttl_hours = proposal_ttl_hours
        self.observation_window_hours = observation_window_hours

    async def propose(
        self,
        *,
        agent_fqn: str,
        workspace_id: UUID,
        revision_id: UUID | None,
        triggered_by: UUID | None,
        signal_source: str = "manual",
    ) -> AdaptationProposal:
        existing_loader = getattr(self.repository, "get_open_adaptation", None)
        if callable(existing_loader):
            existing = cast(
                AdaptationProposal | None,
                await existing_loader(agent_fqn, workspace_id),
            )
            if existing is not None:
                return existing

        signals = await self.analyzer.analyze(agent_fqn, workspace_id)
        adjustments = [_build_adjustment(signal) for signal in signals]
        ate_config_id = await self._resolve_ate_config(workspace_id)
        status = (
            AdaptationProposalStatus.proposed
            if signals
            else AdaptationProposalStatus.no_opportunities
        )
        expected_improvement = _build_expected_improvement(signals, self.observation_window_hours)
        proposal = AdaptationProposal(
            id=uuid4(),
            workspace_id=workspace_id,
            agent_fqn=agent_fqn,
            revision_id=revision_id,
            status=status,
            proposal_details={
                "adjustments": adjustments,
                "ate_config_id": str(ate_config_id) if ate_config_id is not None else None,
            },
            signals=[signal.as_payload() for signal in signals],
            expected_improvement=expected_improvement,
            signal_source=signal_source,
            expires_at=datetime.now(UTC) + timedelta(hours=self.proposal_ttl_hours),
            completion_note=(None if signals else "No adaptation opportunities detected."),
        )
        created = await self.repository.create_adaptation(proposal)
        await self._record_governance(
            AgentOpsEventType.adaptation_proposed.value,
            agent_fqn,
            workspace_id,
            payload={
                "proposal_id": str(created.id),
                "revision_id": str(revision_id) if revision_id is not None else None,
                "status": str(created.status),
                "signal_count": len(signals),
                "signal_source": signal_source,
            },
            actor=triggered_by,
            revision_id=revision_id,
        )
        return created

    async def review(
        self,
        proposal_id: UUID,
        *,
        decision: str,
        reason: str,
        reviewed_by: UUID,
    ) -> AdaptationProposal:
        proposal = await self.repository.get_adaptation(proposal_id)
        if proposal is None:
            raise NotFoundError("AGENTOPS_ADAPTATION_NOT_FOUND", "Adaptation proposal not found")
        if proposal.status == AdaptationProposalStatus.expired.value:
            raise ValidationError(
                "AGENTOPS_ADAPTATION_EXPIRED",
                "Expired adaptation proposals cannot be reviewed.",
            )
        if proposal.status == AdaptationProposalStatus.orphaned.value:
            raise ValidationError(
                "AGENTOPS_ADAPTATION_ORPHANED",
                "Orphaned adaptation proposals cannot be reviewed.",
            )

        proposal.review_reason = reason
        proposal.reviewed_by = reviewed_by
        proposal.reviewed_at = datetime.now(UTC)

        if decision == "rejected":
            proposal.status = AdaptationProposalStatus.rejected
            proposal.completed_at = datetime.now(UTC)
            proposal.completion_note = "Adaptation proposal rejected by human review."
        elif decision == "approved":
            proposal.status = AdaptationProposalStatus.approved
            proposal.completion_note = "Adaptation proposal approved and awaiting explicit apply."
        else:
            raise ValidationError(
                "AGENTOPS_ADAPTATION_DECISION_INVALID",
                "Invalid adaptation decision",
            )

        updated = await self.repository.update_adaptation(proposal)
        await self._record_governance(
            AgentOpsEventType.adaptation_reviewed.value,
            updated.agent_fqn,
            updated.workspace_id,
            payload={
                "proposal_id": str(updated.id),
                "decision": decision,
                "reason": reason,
                "status": str(updated.status),
            },
            actor=reviewed_by,
            revision_id=updated.revision_id,
        )
        return updated

    async def revoke_approval(
        self,
        proposal_id: UUID,
        *,
        reason: str,
        actor: UUID,
    ) -> AdaptationProposal:
        proposal = await self.repository.get_adaptation(proposal_id)
        if proposal is None:
            raise NotFoundError("AGENTOPS_ADAPTATION_NOT_FOUND", "Adaptation proposal not found")
        if proposal.status != AdaptationProposalStatus.approved.value:
            raise ValidationError(
                "AGENTOPS_ADAPTATION_NOT_APPROVED",
                "Only approved proposals can have approval revoked.",
            )
        proposal.status = AdaptationProposalStatus.proposed
        proposal.revoked_at = datetime.now(UTC)
        proposal.revoked_by = actor
        proposal.revoke_reason = reason
        proposal.completion_note = "Approval revoked; proposal returned to proposed state."
        updated = await self.repository.update_adaptation(proposal)
        await self._record_governance(
            AgentOpsEventType.adaptation_approval_revoked.value,
            updated.agent_fqn,
            updated.workspace_id,
            payload={"proposal_id": str(updated.id), "reason": reason},
            actor=actor,
            revision_id=updated.revision_id,
        )
        return updated

    async def handle_ate_result(
        self,
        ate_run_id: UUID | None,
        *,
        passed: bool,
    ) -> AdaptationProposal | None:
        if ate_run_id is None:
            return None
        proposal = await self.repository.get_adaptation_by_evaluation_run_id(ate_run_id)
        if proposal is None:
            return None
        proposal.status = (
            AdaptationProposalStatus.promoted if passed else AdaptationProposalStatus.failed
        )
        proposal.completed_at = datetime.now(UTC)
        proposal.completion_note = (
            "ATE completed successfully; candidate revision promoted."
            if passed
            else "ATE did not pass; candidate revision was not promoted."
        )
        updated = await self.repository.update_adaptation(proposal)
        await self._record_governance(
            AgentOpsEventType.adaptation_completed.value,
            updated.agent_fqn,
            updated.workspace_id,
            payload={
                "proposal_id": str(updated.id),
                "ate_run_id": str(ate_run_id),
                "passed": passed,
                "status": str(updated.status),
            },
            actor=updated.reviewed_by,
            revision_id=updated.candidate_revision_id or updated.revision_id,
        )
        return updated

    async def _resolve_ate_config(self, workspace_id: UUID) -> UUID | None:
        resolver = getattr(self.eval_suite_service, "resolve_default_ate_config", None)
        if callable(resolver):
            return _coerce_uuid(await resolver(workspace_id))
        return None

    async def _record_governance(
        self,
        event_type: str,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        payload: dict[str, object],
        actor: UUID | None,
        revision_id: UUID | None,
    ) -> None:
        if self.governance_publisher is None:
            return
        await self.governance_publisher.record(
            event_type,
            agent_fqn,
            workspace_id,
            payload=payload,
            actor=actor,
            revision_id=revision_id,
        )


def _build_adjustment(signal: AdaptationSignal) -> dict[str, object]:
    mapping = _ADJUSTMENT_MAP.get(signal.rule_type, {})
    return {
        "rule_type": signal.rule_type,
        "target": mapping.get("target", "configuration"),
        "action": mapping.get("action", "review_configuration"),
        "summary": mapping.get("summary", signal.rationale),
        "metrics": deepcopy(signal.metrics),
        "rationale": signal.rationale,
    }


def _build_expected_improvement(
    signals: list[AdaptationSignal],
    observation_window_hours: int,
) -> dict[str, object] | None:
    if not signals:
        return None
    primary = signals[0]
    baseline = 0.0
    target = 0.1
    metric = "quality_score"
    if primary.rule_type == "quality_trend":
        metric = "quality_score"
        baseline = float(primary.metrics.get("latest_quality") or 0.0)
        target = baseline + 0.08
    elif primary.rule_type == "cost_quality":
        metric = "cost_quality_ratio"
        baseline = float(primary.metrics.get("agent_cost_quality_ratio") or 0.0)
        target = max(baseline * 0.8, 0.0)
    elif primary.rule_type == "failure_pattern":
        metric = "failure_rate"
        baseline = float(primary.metrics.get("failure_rate") or 0.0)
        target = max(baseline - 0.1, 0.0)
    elif primary.rule_type == "tool_utilization":
        metric = "tool_utilization_rate"
        baseline = float(primary.metrics.get("tool_utilization_rate") or 0.0)
        target = min(baseline + 0.15, 1.0)
    elif primary.rule_type == "convergence_regression":
        metric = "self_correction_loops"
        baseline = float(primary.metrics.get("recent_loops") or 0.0)
        target = max(float(primary.metrics.get("baseline_loops") or 0.0), baseline - 1.0)
    return {
        "metric": metric,
        "baseline_value": round(baseline, 4),
        "target_value": round(target, 4),
        "target_delta": round(target - baseline, 4),
        "observation_window_hours": observation_window_hours,
    }


def _coerce_adjustments(details: dict[str, object]) -> list[dict[str, object]]:
    raw = details.get("adjustments", [])
    if not isinstance(raw, list):
        return []
    adjustments: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, dict):
            adjustments.append(dict(item))
    return adjustments


def _coerce_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None
