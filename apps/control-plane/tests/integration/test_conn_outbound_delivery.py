from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.connectors.dependencies import build_connectors_service
from platform.connectors.exceptions import DeliveryError
from platform.connectors.implementations.slack import SlackConnector
from uuid import UUID, uuid4

import httpx
import pytest

from tests.auth_support import RecordingProducer
from tests.connectors_support import (
    build_app,
    build_connectors_settings,
    seed_connector_types,
    seed_workspace,
    write_mock_vault,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_connector_outbound_delivery_retries_and_dead_letters(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    migrated_database_url: str,
    redis_client,
    tmp_path,
) -> None:
    vault_file = tmp_path / "vault.json"
    write_mock_vault(
        vault_file,
        {
            "workspaces/test/connectors/slack/bot_token": "xoxb-token",
            "workspaces/test/connectors/slack/signing_secret": "signing-secret",
        },
    )
    settings = build_connectors_settings(
        database_url=migrated_database_url,
        redis_url=redis_client._url or "redis://localhost:6379",
        vault_file=vault_file,
    )
    async with session_factory() as session:
        await seed_connector_types(session)
        workspace_id = uuid4()
        user_id = uuid4()
        await seed_workspace(session, workspace_id=workspace_id, owner_id=user_id, name="Outbound")
        await session.commit()

    producer = RecordingProducer()
    app = build_app(settings=settings, redis_client=redis_client, producer=producer)

    async def _current_user() -> dict[str, str]:
        return {"sub": str(user_id)}

    app.dependency_overrides[get_current_user] = _current_user

    attempts: dict[str, int] = {}

    async def _deliver(self, request, config):
        key = f"{request.destination}:{request.connector_instance_id}"
        attempts[key] = attempts.get(key, 0) + 1
        assert config["bot_token"] == "xoxb-token"
        if request.destination == "retry-channel" and attempts[key] < 2:
            raise DeliveryError("temporary outage")
        if request.destination == "dead-channel":
            raise DeliveryError("still failing")

    monkeypatch.setattr(SlackConnector, "deliver_outbound", _deliver)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        connector = await client.post(
            f"/api/v1/workspaces/{workspace_id}/connectors",
            json={
                "connector_type_slug": "slack",
                "name": "Outbound Slack",
                "config": {
                    "team_id": "T123",
                    "bot_token": {"$ref": "bot_token"},
                    "signing_secret": {"$ref": "signing_secret"},
                },
                "credential_refs": {
                    "bot_token": "workspaces/test/connectors/slack/bot_token",
                    "signing_secret": "workspaces/test/connectors/slack/signing_secret",
                },
            },
        )
        connector_id = connector.json()["id"]
        success = await client.post(
            f"/api/v1/workspaces/{workspace_id}/deliveries",
            json={
                "connector_instance_id": connector_id,
                "destination": "ok-channel",
                "content_text": "ok",
            },
        )
        retrying = await client.post(
            f"/api/v1/workspaces/{workspace_id}/deliveries",
            json={
                "connector_instance_id": connector_id,
                "destination": "retry-channel",
                "content_text": "retry",
            },
        )
        dead = await client.post(
            f"/api/v1/workspaces/{workspace_id}/deliveries",
            json={
                "connector_instance_id": connector_id,
                "destination": "dead-channel",
                "content_text": "dead",
            },
        )

    async def _execute(delivery_id: str):
        async with session_factory() as session:
            service = build_connectors_service(
                session=session,
                settings=settings,
                producer=producer,
                redis_client=redis_client,
                object_storage=app.state.clients["object_storage"],
            )
            response = await service.execute_delivery(UUID(delivery_id))
            await session.commit()
            return response

    success_result = await _execute(success.json()["id"])
    retry_first = await _execute(retrying.json()["id"])
    retry_second = await _execute(retrying.json()["id"])
    dead_first = await _execute(dead.json()["id"])
    dead_second = await _execute(dead.json()["id"])
    dead_third = await _execute(dead.json()["id"])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        dead_letter = await client.get(f"/api/v1/workspaces/{workspace_id}/dead-letter")

    assert success.status_code == 201
    assert retrying.status_code == 201
    assert dead.status_code == 201
    assert success_result.status == "delivered"
    assert retry_first.status == "failed"
    assert retry_first.next_retry_at is not None
    assert retry_second.status == "delivered"
    assert len(retry_second.error_history) == 1
    assert dead_first.status == "failed"
    assert dead_second.status == "failed"
    assert dead_third.status == "dead_lettered"
    assert dead_letter.status_code == 200
    assert dead_letter.json()["total"] == 1
