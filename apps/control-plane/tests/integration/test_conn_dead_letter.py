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


async def test_connector_dead_letter_management_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    migrated_database_url: str,
    redis_client,
    object_storage_settings,
    object_storage_client,
    minio_admin_client,
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
        minio_endpoint=object_storage_settings.MINIO_ENDPOINT,
        minio_access_key=object_storage_settings.MINIO_ACCESS_KEY,
        minio_secret_key=object_storage_settings.MINIO_SECRET_KEY,
    )
    async with session_factory() as session:
        await seed_connector_types(session)
        await session.commit()

    producer = RecordingProducer()
    app = build_app(
        settings=settings,
        redis_client=redis_client,
        producer=producer,
        object_storage=object_storage_client,
    )
    workspace_id = uuid4()
    user_id = uuid4()

    async def _current_user() -> dict[str, str]:
        return {"sub": str(user_id)}

    app.dependency_overrides[get_current_user] = _current_user

    async def _deliver(self, request, config):
        del config
        raise DeliveryError(f"cannot reach {request.destination}")

    monkeypatch.setattr(SlackConnector, "deliver_outbound", _deliver)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        connector = await client.post(
            f"/api/v1/workspaces/{workspace_id}/connectors",
            json={
                "connector_type_slug": "slack",
                "name": "Dead-letter Slack",
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
        first = await client.post(
            f"/api/v1/workspaces/{workspace_id}/deliveries",
            json={
                "connector_instance_id": connector_id,
                "destination": "first",
                "content_text": "one",
            },
        )
        second = await client.post(
            f"/api/v1/workspaces/{workspace_id}/deliveries",
            json={
                "connector_instance_id": connector_id,
                "destination": "second",
                "content_text": "two",
            },
        )

    async def _dead_letter(delivery_id: str) -> None:
        async with session_factory() as session:
            service = build_connectors_service(
                session=session,
                settings=settings,
                producer=producer,
                redis_client=redis_client,
                object_storage=object_storage_client,
            )
            for _ in range(3):
                await service.execute_delivery(UUID(delivery_id))
            await session.commit()

    await _dead_letter(first.json()["id"])
    await _dead_letter(second.json()["id"])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        listed = await client.get(f"/api/v1/workspaces/{workspace_id}/dead-letter")
        pending_entries = listed.json()["items"]
        redeliver = await client.post(
            f"/api/v1/workspaces/{workspace_id}/dead-letter/{pending_entries[0]['id']}/redeliver",
            json={"resolution_note": "retry now"},
        )
        discard = await client.post(
            f"/api/v1/workspaces/{workspace_id}/dead-letter/{pending_entries[1]['id']}/discard",
            json={"resolution_note": "discard now"},
        )
        discard_again = await client.post(
            f"/api/v1/workspaces/{workspace_id}/dead-letter/{pending_entries[1]['id']}/discard",
            json={},
        )
        connector_state = await client.get(
            f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}"
        )

    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert redeliver.status_code == 200
    assert discard.status_code == 200
    assert discard.json()["resolution_status"] == "discarded"
    assert discard_again.status_code == 409
    assert connector_state.json()["messages_dead_lettered"] == 2
    archived = minio_admin_client.get_object(
        Bucket=settings.connectors.dead_letter_bucket,
        Key=discard.json()["archive_path"],
    )
    assert archived["ResponseMetadata"]["HTTPStatusCode"] == 200
