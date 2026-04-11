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
async def test_interactions_conversation_lifecycle_end_to_end() -> None:
    service, _repo, workspaces, producer = build_service()
    workspace_id = uuid4()
    user_id = uuid4()
    workspaces.add_member(workspace_id, user_id)
    app = _build_app(service, workspace_id, user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created_conversation = await client.post(
            "/api/v1/interactions/conversations",
            json={"title": "Q2 Report"},
        )
        conversation_id = created_conversation.json()["id"]
        first_interaction = await client.post(
            "/api/v1/interactions/",
            json={"conversation_id": conversation_id},
        )
        second_interaction = await client.post(
            "/api/v1/interactions/",
            json={"conversation_id": conversation_id},
        )

        for interaction_id in (
            first_interaction.json()["id"],
            second_interaction.json()["id"],
        ):
            await client.post(
                f"/api/v1/interactions/{interaction_id}/transition", json={"trigger": "ready"}
            )
            await client.post(
                f"/api/v1/interactions/{interaction_id}/transition", json={"trigger": "start"}
            )

        first_message = await client.post(
            f"/api/v1/interactions/{first_interaction.json()['id']}/messages",
            json={"content": "Analyze revenue"},
        )
        await client.post(
            f"/api/v1/interactions/{first_interaction.json()['id']}/messages",
            json={
                "content": "Agent response",
                "parent_message_id": first_message.json()["id"],
                "message_type": "agent",
            },
        )
        injected = await client.post(
            f"/api/v1/interactions/{first_interaction.json()['id']}/inject",
            json={"content": "Also include EU"},
        )
        second_message = await client.post(
            f"/api/v1/interactions/{second_interaction.json()['id']}/messages",
            json={"content": "Separate stream"},
        )
        listed_first = await client.get(
            f"/api/v1/interactions/{first_interaction.json()['id']}/messages"
        )
        listed_second = await client.get(
            f"/api/v1/interactions/{second_interaction.json()['id']}/messages"
        )
        participants = await client.get(
            f"/api/v1/interactions/{first_interaction.json()['id']}/participants"
        )
        completed = await client.post(
            f"/api/v1/interactions/{first_interaction.json()['id']}/transition",
            json={"trigger": "complete"},
        )
        await client.delete(f"/api/v1/interactions/conversations/{conversation_id}")
        missing = await client.get(f"/api/v1/interactions/conversations/{conversation_id}")

    assert created_conversation.status_code == 201
    assert first_interaction.status_code == 201
    assert second_interaction.status_code == 201
    assert injected.status_code == 201
    assert second_message.status_code == 201
    assert listed_first.json()["total"] == 3
    assert listed_second.json()["total"] == 1
    assert participants.status_code == 200
    assert completed.json()["state"] == "completed"
    assert missing.status_code == 404
    assert [event["event_type"] for event in producer.events] == [
        "interaction.started",
        "interaction.started",
        "message.received",
        "message.received",
        "message.received",
        "message.received",
        "interaction.completed",
    ]


@pytest.mark.asyncio
async def test_interactions_conversation_lifecycle_enforces_message_limit() -> None:
    from platform.common.config import PlatformSettings

    service, _repo, workspaces, _producer = build_service(
        settings=PlatformSettings(INTERACTIONS_MAX_MESSAGES_PER_CONVERSATION=1)
    )
    workspace_id = uuid4()
    user_id = uuid4()
    workspaces.add_member(workspace_id, user_id)
    app = _build_app(service, workspace_id, user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        conversation = await client.post(
            "/api/v1/interactions/conversations", json={"title": "Limit"}
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
            json={"content": "one"},
        )
        second = await client.post(
            f"/api/v1/interactions/{interaction.json()['id']}/messages",
            json={"content": "two"},
        )

    assert first.status_code == 201
    assert second.status_code == 429
