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
    write_mock_vault,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_connector_credential_isolation_and_rotation(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    migrated_database_url: str,
    redis_client,
    tmp_path,
) -> None:
    vault_file = tmp_path / "vault.json"
    first_secret = "xoxb-old"
    second_secret = "xoxb-new"
    write_mock_vault(
        vault_file,
        {
            "workspaces/test/connectors/slack/bot_token": first_secret,
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
        await session.commit()

    producer = RecordingProducer()
    app = build_app(settings=settings, redis_client=redis_client, producer=producer)
    workspace_id = uuid4()
    other_workspace_id = uuid4()
    user_id = uuid4()
    seen_tokens: list[str] = []

    async def _current_user() -> dict[str, str]:
        return {"sub": str(user_id)}

    app.dependency_overrides[get_current_user] = _current_user

    async def _deliver(self, request, config):
        seen_tokens.append(config["bot_token"])
        if request.destination == "fails":
            raise DeliveryError(f"token leaked {config['bot_token']}")

    monkeypatch.setattr(SlackConnector, "deliver_outbound", _deliver)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        connector = await client.post(
            f"/api/v1/workspaces/{workspace_id}/connectors",
            json={
                "connector_type_slug": "slack",
                "name": "Secure Slack",
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
        fetched = await client.get(f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}")
        cross_workspace = await client.get(
            f"/api/v1/workspaces/{other_workspace_id}/connectors/{connector_id}"
        )
        first_delivery = await client.post(
            f"/api/v1/workspaces/{workspace_id}/deliveries",
            json={
                "connector_instance_id": connector_id,
                "destination": "ok",
                "content_text": "one",
            },
        )

    async with session_factory() as session:
        service = build_connectors_service(
            session=session,
            settings=settings,
            producer=producer,
            redis_client=redis_client,
            object_storage=app.state.clients["minio"],
        )
        await service.execute_delivery(UUID(first_delivery.json()["id"]))
        await session.commit()

    write_mock_vault(
        vault_file,
        {
            "workspaces/test/connectors/slack/bot_token": second_secret,
            "workspaces/test/connectors/slack/signing_secret": "signing-secret",
        },
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        second_delivery = await client.post(
            f"/api/v1/workspaces/{workspace_id}/deliveries",
            json={
                "connector_instance_id": connector_id,
                "destination": "fails",
                "content_text": "two",
            },
        )

    async with session_factory() as session:
        service = build_connectors_service(
            session=session,
            settings=settings,
            producer=producer,
            redis_client=redis_client,
            object_storage=app.state.clients["minio"],
        )
        failed = await service.execute_delivery(UUID(second_delivery.json()["id"]))
        await session.commit()

    assert fetched.status_code == 200
    assert fetched.json()["config"]["bot_token"] == {"$ref": "bot_token"}
    assert "vault_path" not in fetched.text
    assert cross_workspace.status_code == 404
    assert seen_tokens == [first_secret, second_secret]
    assert second_secret not in str(failed.error_history)
    assert second_secret not in str(producer.events)
