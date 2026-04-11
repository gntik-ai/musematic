from __future__ import annotations

from platform.common.auth_middleware import AuthMiddleware
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.interactions.dependencies import get_interactions_service
from platform.interactions.router import router
from platform.interactions.schemas import ConversationCreate, InteractionCreate
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from tests.interactions_support import build_service


def _settings() -> PlatformSettings:
    return PlatformSettings(AUTH_JWT_SECRET_KEY="interactions-secret", AUTH_JWT_ALGORITHM="HS256")


@pytest.mark.asyncio
async def test_interactions_router_requires_auth_for_real_app() -> None:
    service, _repo, _workspaces, _producer = build_service()
    app = FastAPI()
    app.state.settings = _settings()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.add_middleware(AuthMiddleware)
    app.dependency_overrides[get_interactions_service] = lambda: service
    app.include_router(router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/interactions/conversations")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_interactions_router_dependency_override_serves_real_service() -> None:
    service, _repo, workspaces, _producer = build_service()
    workspace_id = uuid4()
    user_id = uuid4()
    workspaces.add_member(workspace_id, user_id)

    app = FastAPI()
    app.state.settings = _settings()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)

    async def _current_user() -> dict[str, str]:
        return {"sub": str(user_id), "workspace_id": str(workspace_id)}

    async def _service():
        return service

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_interactions_service] = _service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        conversation = await client.post(
            "/api/v1/interactions/conversations",
            json=ConversationCreate(title="Router").model_dump(mode="json"),
        )
        interaction = await client.post(
            "/api/v1/interactions/",
            json=InteractionCreate(conversation_id=conversation.json()["id"]).model_dump(
                mode="json"
            ),
        )

    assert conversation.status_code == 201
    assert interaction.status_code == 201


@pytest.mark.asyncio
async def test_interactions_router_exposes_listing_update_lookup_and_participant_endpoints(
) -> None:
    service, _repo, workspaces, _producer = build_service()
    workspace_id = uuid4()
    user_id = uuid4()
    workspaces.add_member(workspace_id, user_id)

    app = FastAPI()
    app.state.settings = _settings()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)

    async def _current_user() -> dict[str, str]:
        return {"sub": str(user_id), "workspace_id": str(workspace_id)}

    async def _service():
        return service

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_interactions_service] = _service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        conversation = await client.post(
            "/api/v1/interactions/conversations",
            json=ConversationCreate(title="Router Detail").model_dump(mode="json"),
        )
        listed_conversations = await client.get("/api/v1/interactions/conversations")
        updated_conversation = await client.patch(
            f"/api/v1/interactions/conversations/{conversation.json()['id']}",
            json={"title": "Router Updated"},
        )
        interaction = await client.post(
            "/api/v1/interactions/",
            json=InteractionCreate(conversation_id=conversation.json()["id"]).model_dump(
                mode="json"
            ),
        )
        fetched_interaction = await client.get(
            f"/api/v1/interactions/{interaction.json()['id']}"
        )
        listed_interactions = await client.get(
            f"/api/v1/interactions/conversations/{conversation.json()['id']}/interactions"
        )
        participant = await client.post(
            f"/api/v1/interactions/{interaction.json()['id']}/participants",
            json={"identity": "observer", "role": "observer"},
        )
        removed = await client.delete(
            f"/api/v1/interactions/{interaction.json()['id']}/participants/observer"
        )

    assert listed_conversations.status_code == 200
    assert listed_conversations.json()["total"] == 1
    assert updated_conversation.status_code == 200
    assert updated_conversation.json()["title"] == "Router Updated"
    assert fetched_interaction.status_code == 200
    assert listed_interactions.status_code == 200
    assert listed_interactions.json()["total"] == 1
    assert participant.status_code == 201
    assert participant.json()["identity"] == "observer"
    assert removed.status_code == 204
