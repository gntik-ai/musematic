from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.interactions.dependencies import get_interactions_service
from platform.interactions.router import router
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from tests.interactions_support import build_service


def _build_app(service, workspace_id, user_id) -> FastAPI:
    app = FastAPI()
    app.state.settings = service.settings
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)

    async def _current_user() -> dict[str, str]:
        return {"sub": str(user_id), "workspace_id": str(workspace_id)}

    async def _service():
        return service

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_interactions_service] = _service
    return app


@pytest.mark.asyncio
async def test_interactions_branching_merging_pipeline_end_to_end() -> None:
    service, _repo, workspaces, producer = build_service()
    workspace_id = uuid4()
    user_id = uuid4()
    workspaces.add_member(workspace_id, user_id)
    app = _build_app(service, workspace_id, user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        conversation = await client.post(
            "/api/v1/interactions/conversations", json={"title": "Branching"}
        )
        interaction = await client.post(
            "/api/v1/interactions/",
            json={"conversation_id": conversation.json()["id"]},
        )
        await client.post(
            f"/api/v1/interactions/{interaction.json()['id']}/transition", json={"trigger": "ready"}
        )
        await client.post(
            f"/api/v1/interactions/{interaction.json()['id']}/transition", json={"trigger": "start"}
        )
        first = await client.post(
            f"/api/v1/interactions/{interaction.json()['id']}/messages",
            json={"content": "m1"},
        )
        second = await client.post(
            f"/api/v1/interactions/{interaction.json()['id']}/messages",
            json={"content": "m2", "parent_message_id": first.json()["id"]},
        )
        branch = await client.post(
            "/api/v1/interactions/branches",
            json={
                "parent_interaction_id": interaction.json()["id"],
                "branch_point_message_id": second.json()["id"],
            },
        )
        branch_messages = await client.get(
            f"/api/v1/interactions/{branch.json()['branch_interaction_id']}/messages"
        )
        await client.post(
            f"/api/v1/interactions/{branch.json()['branch_interaction_id']}/messages",
            json={
                "content": "branch-msg",
                "parent_message_id": branch_messages.json()["items"][-1]["id"],
            },
        )
        merged = await client.post(
            f"/api/v1/interactions/branches/{branch.json()['id']}/merge",
            json={"conflict_resolution": "accept"},
        )
        abandoned = await client.post(
            "/api/v1/interactions/branches",
            json={
                "parent_interaction_id": interaction.json()["id"],
                "branch_point_message_id": second.json()["id"],
            },
        )
        abandoned_result = await client.post(
            f"/api/v1/interactions/branches/{abandoned.json()['id']}/abandon",
            json={},
        )
        branches = await client.get(
            f"/api/v1/interactions/conversations/{conversation.json()['id']}/branches"
        )

    assert branch.status_code == 201
    assert merged.json()["messages_merged_count"] == 1
    assert abandoned_result.json()["status"] == "abandoned"
    assert len(branches.json()) == 2
    assert [
        event["event_type"] for event in producer.events if event["event_type"] == "branch.merged"
    ] == ["branch.merged"]
