from __future__ import annotations

import hashlib
import hmac
import json
from platform.common.dependencies import get_current_user
from uuid import uuid4

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


def _slack_signature(secret: str, body: bytes, timestamp: str) -> str:
    base = f"v0:{timestamp}:".encode() + body
    return "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()


async def test_connector_inbound_routing_publishes_matching_messages(
    session_factory,
    migrated_database_url: str,
    redis_client,
    tmp_path,
) -> None:
    vault_file = tmp_path / "vault.json"
    secret = "slack-signing-secret"
    write_mock_vault(
        vault_file,
        {
            "workspaces/test/connectors/slack/bot_token": "xoxb-token",
            "workspaces/test/connectors/slack/signing_secret": secret,
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
        await seed_workspace(session, workspace_id=workspace_id, owner_id=user_id, name="Inbound")
        await session.commit()

    producer = RecordingProducer()
    app = build_app(settings=settings, redis_client=redis_client, producer=producer)

    async def _current_user() -> dict[str, str]:
        return {"sub": str(user_id)}

    app.dependency_overrides[get_current_user] = _current_user

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        connector = await client.post(
            f"/api/v1/workspaces/{workspace_id}/connectors",
            json={
                "connector_type_slug": "slack",
                "name": "Support Slack",
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
        route = await client.post(
            f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}/routes",
            json={
                "name": "Support route",
                "channel_pattern": "#support*",
                "target_agent_fqn": "support-ops:triage-agent",
                "priority": 10,
            },
        )
        matched_body = json.dumps(
            {
                "type": "event_callback",
                "event": {
                    "user": "U123",
                    "channel": "#support-general",
                    "text": "Need help",
                    "ts": "1712846400.000000",
                },
            }
        ).encode("utf-8")
        unmatched_body = json.dumps(
            {
                "type": "event_callback",
                "event": {
                    "user": "U123",
                    "channel": "#random",
                    "text": "Need help",
                    "ts": "1712846401.000000",
                },
            }
        ).encode("utf-8")
        headers = {
            "X-Slack-Request-Timestamp": "1712846400",
            "X-Slack-Signature": _slack_signature(secret, matched_body, "1712846400"),
            "Content-Type": "application/json",
        }
        matched = await client.post(
            f"/api/v1/inbound/slack/{connector_id}",
            headers=headers,
            content=matched_body,
        )
        unmatched = await client.post(
            f"/api/v1/inbound/slack/{connector_id}",
            headers={
                **headers,
                "X-Slack-Signature": _slack_signature(secret, unmatched_body, "1712846400"),
            },
            content=unmatched_body,
        )
        invalid_signature = await client.post(
            f"/api/v1/inbound/slack/{connector_id}",
            headers={**headers, "X-Slack-Signature": "v0=invalid"},
            content=matched_body,
        )
        await client.put(
            f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}",
            json={"status": "disabled"},
        )
        disabled = await client.post(
            f"/api/v1/inbound/slack/{connector_id}",
            headers=headers,
            content=matched_body,
        )

    assert route.status_code == 201
    assert matched.status_code == 200
    assert matched.json()["routed"] is True
    assert unmatched.status_code == 200
    assert unmatched.json()["routed"] is False
    assert invalid_signature.status_code == 401
    assert disabled.status_code == 400
    assert producer.events[-1]["event_type"] == "connector.ingress.received"
    assert producer.events[-1]["payload"]["target_agent_fqn"] == "support-ops:triage-agent"
