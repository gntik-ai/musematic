from __future__ import annotations

from platform.common.exceptions import ValidationError
from platform.common.tagging.exceptions import EntityTypeNotRegisteredError
from platform.common.tagging.visibility_resolver import VisibilityResolver
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_visibility_resolver_calls_registered_providers() -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    calls: list[str] = []

    async def workspaces(_requester: object) -> set[object]:
        calls.append("workspace")
        return {workspace_id}

    async def agents(_requester: object) -> set[object]:
        calls.append("agent")
        return {agent_id}

    resolver = VisibilityResolver(
        {
            "workspace": workspaces,
            "agent": agents,
        },
        max_visible_ids=10,
    )

    visible = await resolver.resolve_visible_entity_ids({}, ["workspace", "agent"])

    assert visible == {"workspace": {workspace_id}, "agent": {agent_id}}
    assert calls == ["workspace", "agent"]


@pytest.mark.asyncio
async def test_visibility_resolver_rejects_unknown_entity_type() -> None:
    resolver = VisibilityResolver()

    with pytest.raises(EntityTypeNotRegisteredError):
        await resolver.resolve_visible_entity_ids({}, ["unknown"])


@pytest.mark.asyncio
async def test_visibility_resolver_enforces_visible_id_bound() -> None:
    async def too_many(_requester: object) -> set[object]:
        return {uuid4(), uuid4()}

    resolver = VisibilityResolver({"agent": too_many}, max_visible_ids=1)

    with pytest.raises(ValidationError):
        await resolver.resolve_visible_entity_ids({}, ["agent"])

