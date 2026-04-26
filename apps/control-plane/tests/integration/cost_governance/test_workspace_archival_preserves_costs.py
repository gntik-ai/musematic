from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.workspaces.schemas import CreateWorkspaceRequest
from platform.workspaces.service import WorkspacesService
from uuid import UUID, uuid4

import pytest

from tests.workspaces_support import WorkspacesRepoStub, build_recording_producer


class CostGovernanceArchiveRecorder:
    def __init__(self) -> None:
        self.archived: list[UUID] = []

    async def handle_workspace_archived(self, workspace_id: UUID) -> None:
        self.archived.append(workspace_id)


@pytest.mark.asyncio
async def test_workspace_archival_calls_cost_governance_retention_hook() -> None:
    owner_id = uuid4()
    cost_service = CostGovernanceArchiveRecorder()
    service = WorkspacesService(
        repo=WorkspacesRepoStub(),
        settings=PlatformSettings(),
        kafka_producer=build_recording_producer(),
        cost_governance_service=cost_service,
    )
    workspace = await service.create_workspace(owner_id, CreateWorkspaceRequest(name="Finance"))

    archived = await service.archive_workspace(workspace.id, owner_id)

    assert archived.status.value == "archived"
    assert cost_service.archived == [workspace.id]
