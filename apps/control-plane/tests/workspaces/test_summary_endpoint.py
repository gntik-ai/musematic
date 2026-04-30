from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.workspaces.exceptions import WorkspaceAuthorizationError, WorkspaceNotFoundError
from platform.workspaces.models import WorkspaceRole
from platform.workspaces.schemas import UpdateSettingsRequest
from platform.workspaces.service import WorkspacesService
from uuid import uuid4

import pytest
from tests.auth_support import RecordingProducer
from tests.workspaces_support import (
    WorkspacesRepoStub,
    build_goal,
    build_membership,
    build_settings,
    build_workspace,
)


class _Redis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        assert ttl == 30
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)


def _service(repo: WorkspacesRepoStub, redis: _Redis | None = None) -> WorkspacesService:
    return WorkspacesService(
        repo=repo,
        settings=PlatformSettings(),
        kafka_producer=RecordingProducer(),
        redis_client=redis,
    )


@pytest.mark.asyncio
async def test_summary_aggregates_workspace_cards_and_hits_cache() -> None:
    owner_id = uuid4()
    workspace = build_workspace(owner_id=owner_id)
    repo = WorkspacesRepoStub()
    repo.workspaces[workspace.id] = workspace
    repo.memberships[(workspace.id, owner_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=owner_id,
        role=WorkspaceRole.owner,
    )
    repo.settings_by_workspace[workspace.id] = build_settings(
        workspace_id=workspace.id,
        subscribed_agents=["agent.alpha", "agent.beta"],
        cost_budget={"amount": 10000, "currency": "USD"},
        quota_config={"agents": 5},
        dlp_rules={"enabled": True},
    )
    for index in range(3):
        goal = build_goal(workspace_id=workspace.id, created_by=owner_id, title=f"Goal {index}")
        repo.goals[(workspace.id, goal.id)] = goal
    redis = _Redis()
    service = _service(repo, redis)

    first = await service.get_summary(workspace.id, owner_id)
    second = await service.get_summary(workspace.id, owner_id)

    assert first.active_goals == 3
    assert first.agent_count == 2
    assert first.cards["budget"].metadata["currency"] == "USD"
    assert first.cached_until is not None
    assert second == first


@pytest.mark.asyncio
async def test_summary_cache_invalidates_on_settings_update() -> None:
    owner_id = uuid4()
    workspace = build_workspace(owner_id=owner_id)
    repo = WorkspacesRepoStub()
    repo.workspaces[workspace.id] = workspace
    repo.memberships[(workspace.id, owner_id)] = build_membership(
        workspace_id=workspace.id,
        user_id=owner_id,
        role=WorkspaceRole.owner,
    )
    repo.settings_by_workspace[workspace.id] = build_settings(workspace_id=workspace.id)
    redis = _Redis()
    service = _service(repo, redis)

    await service.get_summary(workspace.id, owner_id)
    await service.update_settings(
        workspace.id,
        owner_id,
        UpdateSettingsRequest(quota_config={"agents": 10}),
    )

    assert f"workspace:summary:{workspace.id}" in redis.deleted


@pytest.mark.asyncio
async def test_summary_requires_workspace_membership() -> None:
    workspace = build_workspace()
    repo = WorkspacesRepoStub()
    repo.workspaces[workspace.id] = workspace
    service = _service(repo)

    with pytest.raises((WorkspaceAuthorizationError, WorkspaceNotFoundError)) as exc:
        await service.get_summary(workspace.id, uuid4())

    assert getattr(exc.value, "code", "") in {"WORKSPACE_NOT_FOUND", "WORKSPACE_FORBIDDEN"}
