from __future__ import annotations

from copy import deepcopy
from platform.agentops.adaptation.apply_service import (
    AdaptationApplyService,
    append_note,
    apply_adjustments,
    coerce_uuid,
    configuration_hash,
    is_missing,
    is_stale,
    state_to_snapshot,
)
from platform.agentops.exceptions import StaleProposalError
from platform.agentops.models import AdaptationProposalStatus
from platform.common.exceptions import NotFoundError, ValidationError
from uuid import UUID, uuid4

import pytest
from tests.agentops_support import build_adaptation_proposal


class _RepositoryStub:
    def __init__(self, proposal):
        self.proposal = proposal
        self.snapshots = []

    async def get_adaptation(self, proposal_id):
        return self.proposal if proposal_id == self.proposal.id else None

    async def create_snapshot(self, snapshot):
        snapshot.created_at = snapshot.retention_expires_at
        snapshot.updated_at = snapshot.retention_expires_at
        self.snapshots.append(snapshot)
        return snapshot

    async def update_adaptation(self, proposal):
        self.proposal = proposal
        return proposal


class _RegistryStub:
    def __init__(self, state: dict[str, object] | None) -> None:
        self.state = deepcopy(state)
        self.update_calls: list[dict[str, object]] = []
        self.fail_after_update = False
        self.return_none_after_update = False

    async def get_profile_state(self, agent_fqn: str, workspace_id: UUID):
        del agent_fqn, workspace_id
        return deepcopy(self.state)

    async def update_profile_fields(
        self, agent_fqn: str, workspace_id: UUID, fields: dict[str, object]
    ):
        del agent_fqn, workspace_id
        self.update_calls.append(deepcopy(fields))
        if self.state is not None:
            self.state.update(deepcopy(fields))
        if self.fail_after_update and len(self.update_calls) == 1:
            raise RuntimeError("partial apply")
        if self.return_none_after_update:
            return None
        return deepcopy(self.state)


class _GovernancePublisherStub:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def record(self, event_type: str, agent_fqn: str, workspace_id: UUID, payload, **kwargs):
        self.events.append(
            {
                "event_type": event_type,
                "agent_fqn": agent_fqn,
                "workspace_id": workspace_id,
                "payload": payload,
                **kwargs,
            }
        )


def _profile_state(workspace_id: UUID, revision_id: UUID | None = None) -> dict[str, object]:
    return {
        "workspace_id": workspace_id,
        "revision_id": revision_id or uuid4(),
        "display_name": "Finance Agent",
        "purpose": "Handle billing",
        "approach": "Baseline approach",
        "role_types": ["executor"],
        "custom_role_description": None,
        "tags": ["finance"],
        "visibility_agents": ["finance:*"],
        "visibility_tools": ["search"],
        "mcp_server_refs": ["mcp://finance"],
    }


@pytest.mark.asyncio
async def test_apply_creates_snapshots_mutates_profile_and_emits_event() -> None:
    workspace_id = uuid4()
    proposal = build_adaptation_proposal(
        workspace_id=workspace_id,
        revision_id=uuid4(),
        status=AdaptationProposalStatus.approved,
        proposal_details={
            "adjustments": [{"target": "context_profile", "action": "refresh_context_profile"}],
        },
    )
    registry = _RegistryStub(_profile_state(workspace_id, proposal.revision_id))
    governance = _GovernancePublisherStub()
    service = AdaptationApplyService(
        repository=_RepositoryStub(proposal),  # type: ignore[arg-type]
        registry_service=registry,
        governance_publisher=governance,  # type: ignore[arg-type]
        rollback_retention_days=30,
        observation_window_hours=72,
    )

    response = await service.apply(proposal.id, actor=uuid4(), reason="ship it")

    assert response.proposal.status == AdaptationProposalStatus.applied
    assert response.pre_apply_configuration_hash.startswith("sha256:")
    assert response.proposal.pre_apply_snapshot_key is not None
    assert len(service.repository.snapshots) == 2
    assert "context-refresh" in registry.state["tags"]
    assert governance.events[0]["event_type"] == "agentops.adaptation.applied"


@pytest.mark.asyncio
async def test_apply_marks_stale_when_target_fields_are_missing() -> None:
    workspace_id = uuid4()
    proposal = build_adaptation_proposal(
        workspace_id=workspace_id,
        revision_id=uuid4(),
        status=AdaptationProposalStatus.approved,
        proposal_details={
            "adjustments": [{"target": "tool_selection", "action": "rebalance_tool_selection"}],
        },
    )
    state = _profile_state(workspace_id, proposal.revision_id)
    state["visibility_tools"] = []
    state["mcp_server_refs"] = []
    repository = _RepositoryStub(proposal)
    service = AdaptationApplyService(
        repository=repository,  # type: ignore[arg-type]
        registry_service=_RegistryStub(state),
        governance_publisher=_GovernancePublisherStub(),  # type: ignore[arg-type]
        rollback_retention_days=30,
        observation_window_hours=72,
    )

    with pytest.raises(StaleProposalError):
        await service.apply(proposal.id, actor=uuid4())

    assert repository.proposal.status == AdaptationProposalStatus.stale


@pytest.mark.asyncio
async def test_apply_attempts_auto_recovery_on_partial_failure() -> None:
    workspace_id = uuid4()
    proposal = build_adaptation_proposal(
        workspace_id=workspace_id,
        revision_id=uuid4(),
        status=AdaptationProposalStatus.approved,
        proposal_details={
            "adjustments": [{"target": "approach_text", "action": "revise_approach_text"}],
        },
    )
    initial_state = _profile_state(workspace_id, proposal.revision_id)
    registry = _RegistryStub(initial_state)
    registry.fail_after_update = True
    repository = _RepositoryStub(proposal)
    service = AdaptationApplyService(
        repository=repository,  # type: ignore[arg-type]
        registry_service=registry,
        governance_publisher=None,
        rollback_retention_days=30,
        observation_window_hours=72,
    )

    with pytest.raises(RuntimeError):
        await service.apply(proposal.id, actor=uuid4())

    assert registry.state["approach"] == initial_state["approach"]
    assert repository.proposal.proposal_details["recovery_path"] == "auto_rollback"
    assert len(registry.update_calls) == 2


@pytest.mark.asyncio
async def test_apply_rejects_missing_and_non_approved_proposals() -> None:
    workspace_id = uuid4()
    proposal = build_adaptation_proposal(
        workspace_id=workspace_id,
        status=AdaptationProposalStatus.proposed,
    )
    service = AdaptationApplyService(
        repository=_RepositoryStub(proposal),  # type: ignore[arg-type]
        registry_service=_RegistryStub(_profile_state(workspace_id, proposal.revision_id)),
        governance_publisher=None,
        rollback_retention_days=30,
        observation_window_hours=72,
    )

    with pytest.raises(NotFoundError):
        await service.apply(UUID(int=0), actor=uuid4())

    with pytest.raises(ValidationError) as excinfo:
        await service.apply(proposal.id, actor=uuid4())

    assert excinfo.value.code == "AGENTOPS_ADAPTATION_NOT_APPROVED"


@pytest.mark.asyncio
async def test_apply_marks_orphaned_or_failed_when_registry_state_is_missing() -> None:
    workspace_id = uuid4()
    orphaned = build_adaptation_proposal(
        workspace_id=workspace_id,
        status=AdaptationProposalStatus.approved,
    )
    orphaned_repository = _RepositoryStub(orphaned)
    orphaned_service = AdaptationApplyService(
        repository=orphaned_repository,  # type: ignore[arg-type]
        registry_service=_RegistryStub(None),
        governance_publisher=None,
        rollback_retention_days=30,
        observation_window_hours=72,
    )

    with pytest.raises(ValidationError) as excinfo:
        await orphaned_service.apply(orphaned.id, actor=uuid4())

    assert excinfo.value.code == "AGENTOPS_ADAPTATION_ORPHANED"
    assert orphaned_repository.proposal.status == AdaptationProposalStatus.orphaned

    missing_update = build_adaptation_proposal(
        workspace_id=workspace_id,
        status=AdaptationProposalStatus.approved,
    )
    registry = _RegistryStub(_profile_state(workspace_id, missing_update.revision_id))
    registry.return_none_after_update = True
    failing_service = AdaptationApplyService(
        repository=_RepositoryStub(missing_update),  # type: ignore[arg-type]
        registry_service=registry,
        governance_publisher=None,
        rollback_retention_days=30,
        observation_window_hours=72,
    )

    with pytest.raises(ValidationError) as failed_excinfo:
        await failing_service.apply(missing_update.id, actor=uuid4())

    assert failed_excinfo.value.code == "AGENTOPS_ADAPTATION_APPLY_FAILED"


def test_apply_service_helper_functions_cover_remaining_branches() -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    snapshot = state_to_snapshot(_profile_state(workspace_id, revision_id))

    assert snapshot["active_revision_id"] == str(revision_id)
    assert configuration_hash(snapshot).startswith("sha256:")
    assert coerce_uuid(None) is None
    assert coerce_uuid(revision_id) == revision_id
    assert coerce_uuid("bad-value") is None
    assert is_missing(None) is True
    assert is_missing("") is True
    assert is_missing([]) is True
    assert is_missing({}) is True
    assert is_missing("ok") is False
    assert append_note(None, "fresh") == "fresh"
    assert append_note("base", "fresh") == "base\n\nfresh"
    assert append_note("base\n\nfresh", "fresh") == "base\n\nfresh"

    updated = apply_adjustments(
        snapshot["profile_fields"],
        {
            "adjustments": [
                {"action": "optimize_model_params"},
                {"action": "rebalance_tool_selection"},
                {"action": "stabilize_convergence_strategy"},
                "skip-me",
            ]
        },
    )

    assert "Cost profile tuned by agent adaptation." in updated["approach"]
    assert "Self-correction convergence guidance stabilized." in updated["approach"]
    assert "balanced-tool" in updated["visibility_tools"]
    assert (
        is_stale(
            snapshot["profile_fields"],
            {"adjustments": ["skip-me", {"target": "unknown"}]},
        )
        is False
    )
