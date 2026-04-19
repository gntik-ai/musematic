from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from platform.agentops.adaptation.rollback_service import (
    AdaptationRollbackService,
    configuration_hash,
    snapshot_payload,
)
from platform.agentops.exceptions import RollbackIntegrityError, RollbackWindowExpiredError
from platform.agentops.models import AdaptationProposalStatus, SnapshotType
from uuid import UUID, uuid4

import pytest
from tests.agentops_support import (
    build_adaptation_proposal,
    build_adaptation_snapshot,
    utcnow,
)


class _RepositoryStub:
    def __init__(self, proposal, snapshots):
        self.proposal = proposal
        self.snapshots = snapshots

    async def get_adaptation(self, proposal_id):
        return self.proposal if proposal_id == self.proposal.id else None

    async def list_snapshots_by_proposal(self, proposal_id):
        assert proposal_id == self.proposal.id
        return list(self.snapshots)

    async def update_adaptation(self, proposal):
        self.proposal = proposal
        return proposal


class _RegistryStub:
    def __init__(self, state: dict[str, object]) -> None:
        self.state = deepcopy(state)

    async def update_profile_fields(
        self, agent_fqn: str, workspace_id: UUID, fields: dict[str, object]
    ):
        del agent_fqn, workspace_id
        self.state.update(deepcopy(fields))
        return deepcopy(self.state)

    async def get_profile_state(self, agent_fqn: str, workspace_id: UUID):
        del agent_fqn, workspace_id
        return deepcopy(self.state)


class _GovernancePublisherStub:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def record(self, event_type: str, agent_fqn: str, workspace_id: UUID, payload, **kwargs):
        del agent_fqn, workspace_id, payload, kwargs
        self.events.append(event_type)


@pytest.mark.asyncio
async def test_rollback_restores_pre_apply_snapshot_and_emits_event() -> None:
    workspace_id = uuid4()
    proposal = build_adaptation_proposal(
        workspace_id=workspace_id,
        revision_id=uuid4(),
        status=AdaptationProposalStatus.applied,
        applied_at=utcnow(),
    )
    pre_config = {
        "profile_fields": {"approach": "stable", "tags": ["finance"]},
        "active_revision_id": str(proposal.revision_id),
    }
    restored_state = {**pre_config["profile_fields"], "revision_id": proposal.revision_id}
    pre_snapshot = build_adaptation_snapshot(
        proposal_id=proposal.id,
        snapshot_type=SnapshotType.pre_apply,
        configuration=pre_config,
        configuration_hash=configuration_hash(snapshot_payload(restored_state)),
        retention_expires_at=utcnow() + timedelta(days=1),
        revision_id=proposal.revision_id,
    )
    repository = _RepositoryStub(proposal, [pre_snapshot])
    registry = _RegistryStub(
        {"approach": "changed", "tags": ["context-refresh"], "revision_id": proposal.revision_id}
    )
    governance = _GovernancePublisherStub()
    service = AdaptationRollbackService(
        repository=repository,  # type: ignore[arg-type]
        registry_service=registry,
        governance_publisher=governance,  # type: ignore[arg-type]
    )

    # match expected configuration hash after restore
    response = await service.rollback(proposal.id, actor=uuid4(), reason="undo")

    assert response.proposal.status == AdaptationProposalStatus.rolled_back
    assert response.byte_identical_to_pre_apply is True
    assert governance.events == ["agentops.adaptation.rolled_back"]


@pytest.mark.asyncio
async def test_rollback_rejects_expired_window() -> None:
    proposal = build_adaptation_proposal(
        status=AdaptationProposalStatus.applied, applied_at=utcnow()
    )
    pre_snapshot = build_adaptation_snapshot(
        proposal_id=proposal.id,
        snapshot_type=SnapshotType.pre_apply,
        retention_expires_at=utcnow() - timedelta(minutes=1),
    )
    service = AdaptationRollbackService(
        repository=_RepositoryStub(proposal, [pre_snapshot]),  # type: ignore[arg-type]
        registry_service=_RegistryStub({"revision_id": proposal.revision_id}),
        governance_publisher=None,
    )

    with pytest.raises(RollbackWindowExpiredError):
        await service.rollback(proposal.id, actor=uuid4(), reason="late")


@pytest.mark.asyncio
async def test_rollback_raises_integrity_error_when_hash_mismatches() -> None:
    proposal = build_adaptation_proposal(
        status=AdaptationProposalStatus.applied, applied_at=utcnow()
    )
    pre_snapshot = build_adaptation_snapshot(
        proposal_id=proposal.id,
        snapshot_type=SnapshotType.pre_apply,
        configuration={"profile_fields": {"approach": "stable"}, "active_revision_id": None},
        configuration_hash="sha256:expected",
        retention_expires_at=utcnow() + timedelta(days=1),
    )
    service = AdaptationRollbackService(
        repository=_RepositoryStub(proposal, [pre_snapshot]),  # type: ignore[arg-type]
        registry_service=_RegistryStub(
            {"approach": "different", "revision_id": proposal.revision_id}
        ),
        governance_publisher=None,
    )

    with pytest.raises(RollbackIntegrityError):
        await service.rollback(proposal.id, actor=uuid4(), reason="bad")
