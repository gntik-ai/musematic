from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.connectors.implementations.slack import SlackConnector
from platform.connectors.models import ConnectorHealthStatus
from platform.connectors.plugin import HealthCheckResult
from uuid import uuid4

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


async def test_connector_instance_lifecycle_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    migrated_database_url: str,
    redis_client,
    object_storage_settings,
    object_storage_client,
    tmp_path,
) -> None:
    vault_file = tmp_path / "vault.json"
    write_mock_vault(
        vault_file,
        {
            "workspaces/test/connectors/slack/bot_token": "xoxb-valid",
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
    other_workspace_id = uuid4()
    user_id = uuid4()

    async def _current_user() -> dict[str, str]:
        return {"sub": str(user_id)}

    app.dependency_overrides[get_current_user] = _current_user

    async def _healthy(self, config):
        assert config["bot_token"] == "xoxb-valid"
        return HealthCheckResult(status=ConnectorHealthStatus.healthy, latency_ms=12.5)

    monkeypatch.setattr(SlackConnector, "health_check", _healthy)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            f"/api/v1/workspaces/{workspace_id}/connectors",
            json={
                "connector_type_slug": "slack",
                "name": "Engineering Slack",
                "config": {
                    "team_id": "T123",
                    "default_channel": "C999",
                    "bot_token": {"$ref": "bot_token"},
                    "signing_secret": {"$ref": "signing_secret"},
                },
                "credential_refs": {
                    "bot_token": "workspaces/test/connectors/slack/bot_token",
                    "signing_secret": "workspaces/test/connectors/slack/signing_secret",
                },
            },
        )
        invalid = await client.post(
            f"/api/v1/workspaces/{workspace_id}/connectors",
            json={
                "connector_type_slug": "slack",
                "name": "Broken Slack",
                "config": {"bot_token": {"$ref": "bot_token"}},
                "credential_refs": {"bot_token": "workspaces/test/connectors/slack/bot_token"},
            },
        )
        connector_id = created.json()["id"]
        listed = await client.get(f"/api/v1/workspaces/{workspace_id}/connectors")
        fetched = await client.get(f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}")
        health = await client.post(
            f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}/health-check"
        )
        updated = await client.put(
            f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}",
            json={"name": "Support Slack", "status": "disabled"},
        )
        cross_workspace = await client.get(
            f"/api/v1/workspaces/{other_workspace_id}/connectors/{connector_id}"
        )
        deleted = await client.delete(
            f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}"
        )
        missing = await client.get(f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}")

    assert created.status_code == 201
    assert invalid.status_code == 400
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert fetched.json()["config"]["bot_token"] == {"$ref": "bot_token"}
    assert "vault_path" not in created.text
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    assert updated.status_code == 200
    assert updated.json()["status"] == "disabled"
    assert cross_workspace.status_code == 404
    assert deleted.status_code == 204
    assert missing.status_code == 404
