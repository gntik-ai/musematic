from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.workspaces.exceptions import WorkspaceAuthorizationError, WorkspaceStateConflictError
from platform.workspaces.models import WorkspaceRole
from platform.workspaces.schemas import TransferOwnershipRequest
from platform.workspaces.service import WorkspacesService
from uuid import uuid4

import pytest
from tests.auth_support import RecordingProducer
from tests.workspaces_support import WorkspacesRepoStub, build_membership, build_workspace


class _TwoPA:
    def __init__(self) -> None:
        self.challenge_id = uuid4()
        self.calls: list[dict[str, object]] = []

    async def create_challenge(self, **kwargs):
        self.calls.append(dict(kwargs))
        return type(
            "Challenge",
            (),
            {
                "id": self.challenge_id,
                "action_type": kwargs["action_type"],
                "status": "pending",
                "expires_at": datetime.now(UTC) + timedelta(minutes=5),
            },
        )()


def _service(
    repo: WorkspacesRepoStub,
    producer: RecordingProducer | None = None,
) -> WorkspacesService:
    return WorkspacesService(
        repo=repo,
        settings=PlatformSettings(),
        kafka_producer=producer or RecordingProducer(),
    )


def _repo_with_owner_and_new_owner() -> tuple[WorkspacesRepoStub, object, object, object]:
    repo = WorkspacesRepoStub()
    owner_id = uuid4()
    new_owner_id = uuid4()
    workspace = build_workspace(owner_id=owner_id)
    repo.workspaces[workspace.id] = workspace
    repo.existing_users.update({owner_id, new_owner_id})
    repo.memberships[(workspace.id, owner_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=owner_id,
        role=WorkspaceRole.owner,
    )
    repo.memberships[(workspace.id, new_owner_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=new_owner_id,
        role=WorkspaceRole.member,
    )
    return repo, workspace, owner_id, new_owner_id


@pytest.mark.asyncio
async def test_initiate_transfer_creates_2pa_challenge_and_event() -> None:
    repo, workspace, owner_id, new_owner_id = _repo_with_owner_and_new_owner()
    producer = RecordingProducer()
    service = _service(repo, producer)
    two_pa = _TwoPA()
    service.two_person_approval_service = two_pa

    response = await service.initiate_ownership_transfer(
        workspace.id,
        owner_id,
        TransferOwnershipRequest(new_owner_id=new_owner_id),
    )

    assert response.challenge_id == two_pa.challenge_id
    assert two_pa.calls[0]["action_type"] == "workspace_transfer_ownership"
    assert two_pa.calls[0]["action_payload"] == {
        "workspace_id": str(workspace.id),
        "new_owner_id": str(new_owner_id),
    }
    assert any(
        event["event_type"] == "auth.workspace.transfer_initiated"
        for event in producer.events
    )


@pytest.mark.asyncio
async def test_commit_transfer_swaps_owner_and_downgrades_previous_owner() -> None:
    repo, workspace, owner_id, new_owner_id = _repo_with_owner_and_new_owner()
    producer = RecordingProducer()
    service = _service(repo, producer)

    response = await service.commit_ownership_transfer_payload(
        {"workspace_id": str(workspace.id), "new_owner_id": str(new_owner_id)},
        owner_id,
    )

    assert response.owner_id == new_owner_id
    assert repo.memberships[(workspace.id, owner_id)].role == WorkspaceRole.admin
    assert repo.memberships[(workspace.id, new_owner_id)].role == WorkspaceRole.owner
    assert any(
        event["event_type"] == "auth.workspace.transfer_committed"
        for event in producer.events
    )


@pytest.mark.asyncio
async def test_transfer_rejects_missing_2pa_or_non_owner_initiator() -> None:
    repo, workspace, owner_id, new_owner_id = _repo_with_owner_and_new_owner()
    service = _service(repo)

    with pytest.raises(WorkspaceStateConflictError):
        await service.initiate_ownership_transfer(
            workspace.id,
            owner_id,
            TransferOwnershipRequest(new_owner_id=new_owner_id),
        )

    with pytest.raises(WorkspaceAuthorizationError):
        await service.commit_ownership_transfer_payload(
            {"workspace_id": str(workspace.id), "new_owner_id": str(new_owner_id)},
            new_owner_id,
        )
