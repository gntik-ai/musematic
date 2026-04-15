from __future__ import annotations

from platform.agentops.adaptation.analyzer import AdaptationSignal
from platform.agentops.adaptation.pipeline import (
    AdaptationPipeline,
    _build_adjustment,
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


class _RegistryStub:
    def __init__(
        self,
        *,
        base_revision_id: UUID,
        candidate_revision_id: UUID | None = None,
    ) -> None:
        self.base_revision_id = base_revision_id
        self.candidate_revision_id = candidate_revision_id or uuid4()
        self.created_candidate = False

    async def get_agent_revision(self, agent_fqn: str, revision_id: UUID):
        assert agent_fqn == "finance:agent"
        assert revision_id == self.base_revision_id
        return SimpleNamespace(
            id=revision_id,
            agent_profile_id=uuid4(),
            version="1.0.0",
            sha256_digest="a" * 64,
            storage_key="agents/finance/package.tar.gz",
            manifest_snapshot={"version": "1.0.0"},
            uploaded_by=uuid4(),
        )

    async def create_candidate_revision(
        self,
        *,
        agent_fqn: str,
        base_revision_id: UUID,
        workspace_id: UUID,
        adjustments: list[dict[str, object]],
        actor_id: UUID,
    ):
        assert agent_fqn == "finance:agent"
        assert base_revision_id == self.base_revision_id
        assert adjustments
        assert actor_id.int != 0
        self.created_candidate = True
        return SimpleNamespace(id=self.candidate_revision_id)


class _EvalStub:
    def __init__(self) -> None:
        self.default_ate_config_id = uuid4()
        self.started_runs: list[dict[str, object]] = []

    async def resolve_default_ate_config(self, workspace_id: UUID) -> UUID:
        return self.default_ate_config_id

    async def start_ate_run(
        self,
        *,
        ate_config_id: UUID,
        workspace_id: UUID,
        agent_fqn: str,
        candidate_revision_id: UUID,
    ):
        self.started_runs.append(
            {
                "ate_config_id": ate_config_id,
                "workspace_id": workspace_id,
                "agent_fqn": agent_fqn,
                "candidate_revision_id": candidate_revision_id,
            }
        )
        return SimpleNamespace(id=uuid4(), status="pending")


def _signal(rule_type: str) -> AdaptationSignal:
    return AdaptationSignal(
        rule_type=rule_type,
        metrics={"score": 1.0},
        rationale=f"{rule_type} requires adaptation",
    )


@pytest.mark.asyncio
async def test_propose_creates_adaptation_proposal_when_signals_exist() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub()
    governance = _GovernancePublisherStub()
    pipeline = AdaptationPipeline(
        repository=repository,  # type: ignore[arg-type]
        analyzer=_AnalyzerStub([_signal("quality_trend"), _signal("cost_quality")]),
        governance_publisher=governance,  # type: ignore[arg-type]
        registry_service=None,
        eval_suite_service=None,
    )

    proposal = await pipeline.propose(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=uuid4(),
        triggered_by=uuid4(),
    )

    assert proposal.status == AdaptationProposalStatus.proposed
    assert len(proposal.signals) == 2
    assert proposal.proposal_details["adjustments"]
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


@pytest.mark.asyncio
async def test_review_approved_creates_candidate_and_starts_ate() -> None:
    workspace_id = uuid4()
    base_revision_id = uuid4()
    candidate_revision_id = uuid4()
    repository = _RepositoryStub()
    eval_stub = _EvalStub()
    registry_stub = _RegistryStub(
        base_revision_id=base_revision_id,
        candidate_revision_id=candidate_revision_id,
    )
    pipeline = AdaptationPipeline(
        repository=repository,  # type: ignore[arg-type]
        analyzer=_AnalyzerStub([_signal("quality_trend")]),
        governance_publisher=_GovernancePublisherStub(),  # type: ignore[arg-type]
        registry_service=registry_stub,
        eval_suite_service=eval_stub,
    )
    proposal = await pipeline.propose(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=base_revision_id,
        triggered_by=uuid4(),
    )

    reviewed = await pipeline.review(
        proposal.id,
        decision="approved",
        reason="Proceed with testing",
        reviewed_by=uuid4(),
    )

    assert reviewed.status == AdaptationProposalStatus.testing
    assert reviewed.candidate_revision_id == candidate_revision_id
    assert reviewed.evaluation_run_id is not None
    assert registry_stub.created_candidate is True
    assert eval_stub.started_runs[0]["candidate_revision_id"] == candidate_revision_id


@pytest.mark.asyncio
async def test_review_rejected_marks_proposal_rejected_without_candidate() -> None:
    repository = _RepositoryStub()
    pipeline = AdaptationPipeline(
        repository=repository,  # type: ignore[arg-type]
        analyzer=_AnalyzerStub([_signal("failure_pattern")]),
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


@pytest.mark.asyncio
async def test_handle_ate_result_marks_proposal_promoted_on_pass() -> None:
    workspace_id = uuid4()
    base_revision_id = uuid4()
    repository = _RepositoryStub()
    pipeline = AdaptationPipeline(
        repository=repository,  # type: ignore[arg-type]
        analyzer=_AnalyzerStub([_signal("tool_utilization")]),
        governance_publisher=_GovernancePublisherStub(),  # type: ignore[arg-type]
        registry_service=_RegistryStub(base_revision_id=base_revision_id),
        eval_suite_service=_EvalStub(),
    )
    proposal = await pipeline.propose(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=base_revision_id,
        triggered_by=uuid4(),
    )
    proposal = await pipeline.review(
        proposal.id,
        decision="approved",
        reason="Run ATE",
        reviewed_by=uuid4(),
    )

    completed = await pipeline.handle_ate_result(proposal.evaluation_run_id, passed=True)

    assert completed is not None
    assert completed.status == AdaptationProposalStatus.promoted
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_handle_ate_result_marks_proposal_failed_on_failed_run() -> None:
    workspace_id = uuid4()
    base_revision_id = uuid4()
    repository = _RepositoryStub()
    pipeline = AdaptationPipeline(
        repository=repository,  # type: ignore[arg-type]
        analyzer=_AnalyzerStub([_signal("cost_quality")]),
        governance_publisher=_GovernancePublisherStub(),  # type: ignore[arg-type]
        registry_service=_RegistryStub(base_revision_id=base_revision_id),
        eval_suite_service=_EvalStub(),
    )
    proposal = await pipeline.propose(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=base_revision_id,
        triggered_by=uuid4(),
    )
    proposal = await pipeline.review(
        proposal.id,
        decision="approved",
        reason="Run ATE",
        reviewed_by=uuid4(),
    )

    completed = await pipeline.handle_ate_result(proposal.evaluation_run_id, passed=False)

    assert completed is not None
    assert completed.status == AdaptationProposalStatus.failed
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_pipeline_review_validation_and_not_found_paths() -> None:
    repository = _RepositoryStub()
    pipeline = AdaptationPipeline(
        repository=repository,  # type: ignore[arg-type]
        analyzer=_AnalyzerStub([_signal("quality_trend")]),
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
            decision="approved",
            reason="needs revision",
            reviewed_by=uuid4(),
        )
    with pytest.raises(ValidationError):
        await pipeline.review(
            proposal.id,
            decision="invalid",
            reason="invalid",
            reviewed_by=uuid4(),
        )

    proposal.revision_id = uuid4()
    with pytest.raises(ValidationError):
        await pipeline.review(
            proposal.id,
            decision="approved",
            reason="registry missing",
            reviewed_by=uuid4(),
        )

    pipeline.registry_service = SimpleNamespace(get_agent_revision=lambda *args: _resolved(None))
    with pytest.raises(NotFoundError):
        await pipeline.review(
            proposal.id,
            decision="approved",
            reason="source missing",
            reviewed_by=uuid4(),
        )


@pytest.mark.asyncio
async def test_pipeline_fallback_submitter_and_helper_functions() -> None:
    workspace_id = uuid4()
    base_revision_id = uuid4()
    repository = _RepositoryStub()
    governance = _GovernancePublisherStub()
    registry = SimpleNamespace(
        get_agent_revision=lambda *args: _resolved(SimpleNamespace(id=base_revision_id))
    )
    eval_suite = SimpleNamespace(
        resolve_default_ate_config=lambda workspace_id: _resolved(uuid4()),
        submit_to_ate=lambda revision_id, eval_set_id, workspace_id: _resolved(
            SimpleNamespace(ate_run_id=str(uuid4()))
        ),
    )
    pipeline = AdaptationPipeline(
        repository=repository,  # type: ignore[arg-type]
        analyzer=_AnalyzerStub([_signal("tool_utilization")]),
        governance_publisher=governance,  # type: ignore[arg-type]
        registry_service=registry,
        eval_suite_service=eval_suite,
    )

    proposal = await pipeline.propose(
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        revision_id=base_revision_id,
        triggered_by=uuid4(),
    )
    reviewed = await pipeline.review(
        proposal.id,
        decision="approved",
        reason="fallback submitter",
        reviewed_by=uuid4(),
    )

    assert reviewed.status == AdaptationProposalStatus.testing
    assert reviewed.candidate_revision_id == base_revision_id
    assert reviewed.evaluation_run_id is not None
    assert await pipeline.handle_ate_result(None, passed=True) is None
    assert await pipeline.handle_ate_result(uuid4(), passed=True) is None
    assert _build_adjustment(_signal("unknown"))["target"] == "configuration"
    assert _coerce_adjustments({"adjustments": [1, {"a": 1}]}) == [{"a": 1}]
    assert _coerce_adjustments({"adjustments": "bad"}) == []
    assert _coerce_uuid(None) is None
    assert _coerce_uuid("bad") is None
    assert _coerce_uuid(base_revision_id) == base_revision_id


async def _resolved(value: object) -> object:
    return value
