from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from platform.agentops.adaptation.analyzer import AdaptationSignal, BehavioralAnalyzer
from platform.agentops.events import AgentOpsEventType, GovernanceEventPublisher
from platform.agentops.models import AdaptationProposal, AdaptationProposalStatus
from platform.agentops.repository import AgentOpsRepository
from platform.common.exceptions import NotFoundError, ValidationError
from typing import Any
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
    ) -> None:
        self.repository = repository
        self.analyzer = analyzer
        self.governance_publisher = governance_publisher
        self.registry_service = registry_service
        self.eval_suite_service = eval_suite_service

    async def propose(
        self,
        *,
        agent_fqn: str,
        workspace_id: UUID,
        revision_id: UUID | None,
        triggered_by: UUID | None,
    ) -> AdaptationProposal:
        signals = await self.analyzer.analyze(agent_fqn, workspace_id)
        adjustments = [_build_adjustment(signal) for signal in signals]
        ate_config_id = await self._resolve_ate_config(workspace_id)
        status = (
            AdaptationProposalStatus.proposed
            if signals
            else AdaptationProposalStatus.no_opportunities
        )
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
            completion_note=(
                None if signals else "No adaptation opportunities detected."
            ),
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

        proposal.review_reason = reason
        proposal.reviewed_by = reviewed_by
        proposal.reviewed_at = datetime.now(UTC)

        if decision == "rejected":
            proposal.status = AdaptationProposalStatus.rejected
            proposal.completed_at = datetime.now(UTC)
            proposal.completion_note = "Adaptation proposal rejected by human review."
            updated = await self.repository.update_adaptation(proposal)
            await self._record_governance(
                AgentOpsEventType.adaptation_reviewed.value,
                updated.agent_fqn,
                updated.workspace_id,
                payload={
                    "proposal_id": str(updated.id),
                    "decision": decision,
                    "reason": reason,
                },
                actor=reviewed_by,
                revision_id=updated.revision_id,
            )
            return updated

        if decision != "approved":
            raise ValidationError(
                "AGENTOPS_ADAPTATION_DECISION_INVALID",
                "Invalid adaptation decision",
            )

        if proposal.revision_id is None:
            raise ValidationError(
                "AGENTOPS_ADAPTATION_REVISION_REQUIRED",
                "Approved adaptation proposals require a source revision.",
            )
        if self.registry_service is None:
            raise ValidationError(
                "AGENTOPS_ADAPTATION_REGISTRY_UNAVAILABLE",
                "Registry service is required to approve adaptation proposals.",
            )

        base_revision = await self.registry_service.get_agent_revision(
            proposal.agent_fqn,
            proposal.revision_id,
        )
        if base_revision is None:
            raise NotFoundError("AGENTOPS_SOURCE_REVISION_NOT_FOUND", "Source revision not found")

        adjustments = _coerce_adjustments(proposal.proposal_details)
        candidate_revision_id = proposal.revision_id
        creator = getattr(self.registry_service, "create_candidate_revision", None)
        if callable(creator):
            candidate = await creator(
                agent_fqn=proposal.agent_fqn,
                base_revision_id=proposal.revision_id,
                workspace_id=proposal.workspace_id,
                adjustments=adjustments,
                actor_id=reviewed_by,
            )
            candidate_revision_id = (
                _coerce_uuid(getattr(candidate, "id", candidate_revision_id))
                or candidate_revision_id
            )

        evaluation_run_id: UUID | None = None
        ate_config_id = _coerce_uuid(proposal.proposal_details.get("ate_config_id"))
        starter = getattr(self.eval_suite_service, "start_ate_run", None)
        if callable(starter) and ate_config_id is not None:
            run = await starter(
                ate_config_id=ate_config_id,
                workspace_id=proposal.workspace_id,
                agent_fqn=proposal.agent_fqn,
                candidate_revision_id=candidate_revision_id,
            )
            evaluation_run_id = _coerce_uuid(getattr(run, "id", None))
        else:
            submitter = getattr(self.eval_suite_service, "submit_to_ate", None)
            if callable(submitter) and ate_config_id is not None:
                run = await submitter(candidate_revision_id, ate_config_id, proposal.workspace_id)
                evaluation_run_id = _coerce_uuid(
                    getattr(run, "id", None) or getattr(run, "ate_run_id", None)
                )

        proposal.status = AdaptationProposalStatus.testing
        proposal.candidate_revision_id = candidate_revision_id
        proposal.evaluation_run_id = evaluation_run_id
        proposal.completion_note = "Candidate revision approved and queued for ATE."
        updated = await self.repository.update_adaptation(proposal)
        await self._record_governance(
            AgentOpsEventType.adaptation_reviewed.value,
            updated.agent_fqn,
            updated.workspace_id,
            payload={
                "proposal_id": str(updated.id),
                "decision": decision,
                "candidate_revision_id": str(candidate_revision_id),
                "evaluation_run_id": (
                    str(evaluation_run_id) if evaluation_run_id is not None else None
                ),
            },
            actor=reviewed_by,
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
