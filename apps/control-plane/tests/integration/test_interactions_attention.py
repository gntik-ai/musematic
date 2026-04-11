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
async def test_interactions_attention_create_list_acknowledge_and_resolve() -> None:
    service, _repo, workspaces, producer = build_service()
    workspace_id = uuid4()
    user_id = uuid4()
    workspaces.add_member(workspace_id, user_id)
    app = _build_app(service, workspace_id, user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/interactions/attention",
            json={
                "target_identity": str(user_id),
                "urgency": "critical",
                "context_summary": "Need human approval",
            },
        )
        listed = await client.get("/api/v1/interactions/attention")
        acknowledged = await client.post(
            f"/api/v1/interactions/attention/{created.json()['id']}/resolve",
            json={"action": "acknowledge"},
        )
        resolved = await client.post(
            f"/api/v1/interactions/attention/{created.json()['id']}/resolve",
            json={"action": "resolve"},
        )

    assert created.status_code == 201
    assert listed.json()["total"] == 1
    assert acknowledged.json()["status"] == "acknowledged"
    assert resolved.json()["status"] == "resolved"
    assert [event["event_type"] for event in producer.events] == ["attention.requested"]


@pytest.mark.asyncio
async def test_interactions_attention_dismiss_and_enforce_target_authorization() -> None:
    service, _repo, workspaces, _producer = build_service()
    workspace_id = uuid4()
    target_user_id = uuid4()
    other_user_id = uuid4()
    workspaces.add_member(workspace_id, target_user_id)
    workspaces.add_member(workspace_id, other_user_id)
    app = _build_app(service, workspace_id, target_user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/interactions/attention",
            json={
                "target_identity": str(target_user_id),
                "urgency": "high",
                "context_summary": "Please review",
            },
        )

    app_other = _build_app(service, workspace_id, other_user_id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_other),
        base_url="http://testserver",
    ) as client:
        forbidden = await client.post(
            f"/api/v1/interactions/attention/{created.json()['id']}/resolve",
            json={"action": "dismiss"},
        )

    app_target = _build_app(service, workspace_id, target_user_id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_target),
        base_url="http://testserver",
    ) as client:
        dismissed = await client.post(
            f"/api/v1/interactions/attention/{created.json()['id']}/resolve",
            json={"action": "dismiss"},
        )

    assert forbidden.status_code == 403
    assert dismissed.json()["status"] == "dismissed"
