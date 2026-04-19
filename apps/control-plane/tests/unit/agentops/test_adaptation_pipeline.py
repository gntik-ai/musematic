from __future__ import annotations

from platform.agentops.adaptation.analyzer import AdaptationSignal
from platform.agentops.adaptation.pipeline import (
    AdaptationPipeline,
    _build_adjustment,
    _build_expected_improvement,
    _coerce_adjustments,
    _coerce_uuid,
)
from platform.agentops.models import AdaptationProposal, AdaptationProposalStatus
from platform.common.exceptions import NotFoundError, ValidationError
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class _RepositoryStub:
    def __init__(self) -> None:
        self.proposals: dict[UUID, AdaptationProposal] = {}

    async def create_adaptation(self, proposal: AdaptationProposal) -> AdaptationProposal:
        self.proposals[proposal.id] = proposal
        return proposal

    async def get_adaptation(self, proposal_id: UUID) -> AdaptationProposal | None:
        return self.proposals.get(proposal_id)

    async def get_open_adaptation(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> AdaptationProposal | None:
        for proposal in self.proposals.values():
            if proposal.agent_fqn != agent_fqn or proposal.workspace_id != workspace_id:
                continue
            if proposal.status in {
                AdaptationProposalStatus.proposed,
                AdaptationProposalStatus.approved,
                AdaptationProposalStatus.applied,
            }:
                return proposal
        return None

    async def update_adaptation(self, proposal: AdaptationProposal) -> AdaptationProposal:
        self.proposals[proposal.id] = proposal
        return proposal

    async def get_adaptation_by_evaluation_run_id(
        self,
        ate_run_id: UUID,
    ) -> AdaptationProposal | None:
        for proposal in self.proposals.values():
            if proposal.evaluation_run_id == ate_run_id:
                return proposal
        return None


class _AnalyzerStub:
    def __init__(self, signals: list[AdaptationSignal]) -> None:
        self.signals = signals
        self.calls: list[tuple[str, UUID]] = []

    async def analyze(self, agent_fqn: str, workspace_id: UUID) -> list[AdaptationSignal]:
        self.calls.append((agent_fqn, workspace_id))
        return list(self.signals)


class _GovernancePublisherStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def record(self, event_type: str, agent_fqn: str, workspace_id: UUID, payload, **kwargs):
        self.calls.append(
            {
                "event_type": event_type,
                "agent_fqn": agent_fqn,
                "workspace_id": workspace_id,
                "payload": payload,
                **kwargs,
            }
        )


class _EvalStub:
    def __init__(self) -> None:
        self.default_ate_config_id = uuid4()

    async def resolve_default_ate_config(self, workspace_id: UUID) -> UUID:
        return self.default_ate_config_id


def _signal(rule_type: str, **metrics: float | int | str | None) -> AdaptationSignal:
    return AdaptationSignal(
        rule_type=rule_type,
        metrics={"score": 1.0, **metrics},
        rationale=f"{rule_type} requires adaptation",
    )


@pytest.mark.asyncio
async def test_propose_creates_adaptation_proposal_when_signals_exist() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub()
    governance = _GovernancePublisherStub()
    pipeline = AdaptationPipeline(
        repository=repository,  # type: ignore[arg-type]
        analyzer=_AnalyzerStub(
            [
                _signal("quality_trend", latest_quality=0.58),
                _signal("cost_quality", agent_cost_quality_ratio=2.0),
            ]
        ),
        governance_publisher=governance,  # type: ignore[arg-type]
        registry_service=None,
        eval_suite_service=_EvalStub(),
    )

    proposal = await pipeline.propose(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=uuid4(),
        triggered_by=uuid4(),
    )
    duplicate = await pipeline.propose(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=uuid4(),
        triggered_by=uuid4(),
    )

    assert proposal.status == AdaptationProposalStatus.proposed
    assert duplicate.id == proposal.id
    assert len(proposal.signals) == 2
    assert proposal.proposal_details["adjustments"]
    assert proposal.expected_improvement is not None
    assert proposal.expected_improvement["metric"] == "quality_score"
    assert proposal.signal_source == "manual"
    assert proposal.expires_at is not None
    assert governance.calls[0]["event_type"] == "agentops.adaptation.proposed"


@pytest.mark.asyncio
async def test_propose_marks_no_opportunities_when_no_signals_are_found() -> None:
    pipeline = AdaptationPipeline(
        repository=_RepositoryStub(),  # type: ignore[arg-type]
        analyzer=_AnalyzerStub([]),
        governance_publisher=_GovernancePublisherStub(),  # type: ignore[arg-type]
        registry_service=None,
        eval_suite_service=None,
    )

    proposal = await pipeline.propose(
        agent_fqn="finance:agent",
        workspace_id=uuid4(),
        revision_id=uuid4(),
        triggered_by=uuid4(),
    )

    assert proposal.status == AdaptationProposalStatus.no_opportunities
    assert proposal.completion_note == "No adaptation opportunities detected."
    assert proposal.expected_improvement is None


@pytest.mark.asyncio
async def test_review_approved_sets_approved_only_without_candidate_or_ate() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub()
    pipeline = AdaptationPipeline(
        repository=repository,  # type: ignore[arg-type]
        analyzer=_AnalyzerStub([_signal("quality_trend", latest_quality=0.61)]),
        governance_publisher=_GovernancePublisherStub(),  # type: ignore[arg-type]
        registry_service=SimpleNamespace(),
        eval_suite_service=_EvalStub(),
    )
    proposal = await pipeline.propose(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=uuid4(),
        triggered_by=uuid4(),
    )

    reviewed = await pipeline.review(
        proposal.id,
        decision="approved",
        reason="Proceed with explicit apply",
        reviewed_by=uuid4(),
    )

    assert reviewed.status == AdaptationProposalStatus.approved
    assert reviewed.candidate_revision_id is None
    assert reviewed.evaluation_run_id is None
    assert reviewed.completed_at is None
    assert reviewed.reviewed_at is not None


@pytest.mark.asyncio
async def test_revoke_approval_returns_proposal_to_proposed() -> None:
    repository = _RepositoryStub()
    pipeline = AdaptationPipeline(
        repository=repository,  # type: ignore[arg-type]
        analyzer=_AnalyzerStub([_signal("failure_pattern", failure_rate=0.4)]),
        governance_publisher=_GovernancePublisherStub(),  # type: ignore[arg-type]
        registry_service=None,
        eval_suite_service=None,
    )
    proposal = await pipeline.propose(
        agent_fqn="finance:agent",
        workspace_id=uuid4(),
        revision_id=uuid4(),
        triggered_by=uuid4(),
    )
    approved = await pipeline.review(
        proposal.id,
        decision="approved",
        reason="ready",
        reviewed_by=uuid4(),
    )

    revoked = await pipeline.revoke_approval(approved.id, reason="hold", actor=uuid4())

    assert revoked.status == AdaptationProposalStatus.proposed
    assert revoked.revoked_at is not None
    assert revoked.revoke_reason == "hold"


@pytest.mark.asyncio
async def test_review_rejected_marks_proposal_rejected_without_candidate() -> None:
    repository = _RepositoryStub()
    pipeline = AdaptationPipeline(
        repository=repository,  # type: ignore[arg-type]
        analyzer=_AnalyzerStub([_signal("failure_pattern", failure_rate=0.5)]),
        governance_publisher=_GovernancePublisherStub(),  # type: ignore[arg-type]
        registry_service=None,
        eval_suite_service=None,
    )
    proposal = await pipeline.propose(
        agent_fqn="finance:agent",
        workspace_id=uuid4(),
        revision_id=uuid4(),
        triggered_by=uuid4(),
    )

    reviewed = await pipeline.review(
        proposal.id,
        decision="rejected",
        reason="Human rejected the proposal",
        reviewed_by=uuid4(),
    )

    assert reviewed.status == AdaptationProposalStatus.rejected
    assert reviewed.candidate_revision_id is None
    assert reviewed.evaluation_run_id is None
    assert reviewed.completed_at is not None


@pytest.mark.asyncio
async def test_handle_ate_result_marks_historical_proposal_promoted_or_failed() -> None:
    repository = _RepositoryStub()
    governance = _GovernancePublisherStub()
    proposal = AdaptationProposal(
        id=uuid4(),
        workspace_id=uuid4(),
        agent_fqn="finance:agent",
        revision_id=uuid4(),
        status=AdaptationProposalStatus.testing,
        proposal_details={"adjustments": []},
        signals=[],
        evaluation_run_id=uuid4(),
        reviewed_by=uuid4(),
    )
    await repository.create_adaptation(proposal)
    pipeline = AdaptationPipeline(
        repository=repository,  # type: ignore[arg-type]
        analyzer=_AnalyzerStub([]),
        governance_publisher=governance,  # type: ignore[arg-type]
        registry_service=None,
        eval_suite_service=None,
    )

    promoted = await pipeline.handle_ate_result(proposal.evaluation_run_id, passed=True)
    failed = await pipeline.handle_ate_result(uuid4(), passed=False)

    assert promoted is not None
    assert promoted.status == AdaptationProposalStatus.promoted
    assert promoted.completed_at is not None
    assert failed is None


@pytest.mark.asyncio
async def test_pipeline_review_validation_and_not_found_paths() -> None:
    repository = _RepositoryStub()
    pipeline = AdaptationPipeline(
        repository=repository,  # type: ignore[arg-type]
        analyzer=_AnalyzerStub([_signal("quality_trend", latest_quality=0.4)]),
        governance_publisher=None,
        registry_service=None,
        eval_suite_service=None,
    )

    with pytest.raises(NotFoundError):
        await pipeline.review(uuid4(), decision="approved", reason="missing", reviewed_by=uuid4())

    proposal = await pipeline.propose(
        agent_fqn="finance:agent",
        workspace_id=uuid4(),
        revision_id=None,
        triggered_by=uuid4(),
    )
    with pytest.raises(ValidationError):
        await pipeline.review(
            proposal.id,
            decision="invalid",
            reason="invalid",
            reviewed_by=uuid4(),
        )

    proposal.status = AdaptationProposalStatus.expired
    with pytest.raises(ValidationError):
        await pipeline.review(
            proposal.id,
            decision="approved",
            reason="expired",
            reviewed_by=uuid4(),
        )

    proposal.status = AdaptationProposalStatus.orphaned
    with pytest.raises(ValidationError):
        await pipeline.review(
            proposal.id,
            decision="approved",
            reason="orphaned",
            reviewed_by=uuid4(),
        )

    proposal.status = AdaptationProposalStatus.proposed
    with pytest.raises(ValidationError):
        await pipeline.revoke_approval(proposal.id, reason="not-approved", actor=uuid4())


@pytest.mark.asyncio
async def test_pipeline_helper_functions_cover_expected_improvement_and_legacy_helpers() -> None:
    convergence = _build_expected_improvement(
        [_signal("convergence_regression", baseline_loops=2.0, recent_loops=5.0)],
        48,
    )

    assert convergence == {
        "metric": "self_correction_loops",
        "baseline_value": 5.0,
        "target_value": 4.0,
        "target_delta": -1.0,
        "observation_window_hours": 48,
    }
    assert _build_adjustment(_signal("unknown"))["target"] == "configuration"
    assert _coerce_adjustments({"adjustments": [1, {"a": 1}]}) == [{"a": 1}]
    assert _coerce_adjustments({"adjustments": "bad"}) == []
    assert _coerce_uuid(None) is None
    assert _coerce_uuid("bad") is None
    token = uuid4()
    assert _coerce_uuid(token) == token
