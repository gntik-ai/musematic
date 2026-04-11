from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.interactions.dependencies import get_interactions_service
from platform.interactions.router import router
from platform.workspaces.models import GoalStatus
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
async def test_interactions_goal_messages_post_list_and_internal_history() -> None:
    service, _repo, workspaces, producer = build_service()
    workspace_id = uuid4()
    user_id = uuid4()
    goal_id = uuid4()
    workspaces.add_member(workspace_id, user_id)
    workspaces.add_goal(workspace_id, goal_id, status=GoalStatus.open)
    app = _build_app(service, workspace_id, user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
            json={"content": "m1"},
        )
        second = await client.post(
            f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
            json={"content": "m2"},
        )
        listed = await client.get(f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages")

    history = await service.get_goal_messages(workspace_id, goal_id, limit=10)

    assert first.status_code == 201
    assert second.status_code == 201
    assert listed.json()["total"] == 2
    assert [item.content for item in history] == ["m1", "m2"]
    assert [event["event_type"] for event in producer.events] == [
        "goal.message.posted",
        "goal.message.posted",
    ]


@pytest.mark.asyncio
async def test_interactions_goal_messages_reject_completed_goal() -> None:
    service, _repo, workspaces, _producer = build_service()
    workspace_id = uuid4()
    user_id = uuid4()
    goal_id = uuid4()
    workspaces.add_member(workspace_id, user_id)
    workspaces.add_goal(workspace_id, goal_id, status=GoalStatus.completed)
    app = _build_app(service, workspace_id, user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
            json={"content": "blocked"},
        )

    assert response.status_code == 409
