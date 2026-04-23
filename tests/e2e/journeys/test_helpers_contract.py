from __future__ import annotations

import json
from uuid import uuid4

import httpx
import jwt
import pytest

from journeys.conftest import _mint_access_token, _oauth_provider_payload, _persona_email, _persona_roles, _persona_user_id
from journeys.helpers.governance import create_governance_chain
from journeys.helpers.websockets import subscribe_ws


class _FakeClient:
    def __init__(self, responses: dict[tuple[str, str], httpx.Response]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict | None, dict | None]] = []

    async def get(self, url: str, **kwargs):
        self.calls.append(("GET", url, kwargs.get("headers"), None))
        return self.responses[("GET", url)]

    async def put(self, url: str, **kwargs):
        self.calls.append(("PUT", url, None, kwargs.get("json")))
        return self.responses[("PUT", url)]



def _json_response(method: str, url: str, payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request(method, f"http://testserver{url}"),
    )



def test_mint_access_token_includes_workspace_claims() -> None:
    workspace_id = uuid4()
    token = _mint_access_token(
        user_id=_persona_user_id("admin"),
        email=_persona_email("admin"),
        role_names=_persona_roles("admin"),
        workspace_id=workspace_id,
        permissions=["execution.rollback"],
    )

    payload = jwt.decode(token, "change-me", algorithms=["HS256"])

    assert payload["sub"] == str(_persona_user_id("admin"))
    assert payload["email"] == _persona_email("admin")
    assert payload["workspace_id"] == str(workspace_id)
    assert payload["permissions"] == ["execution.rollback"]
    assert payload["roles"] == [{"role": "platform_admin", "workspace_id": str(workspace_id)}]



def test_oauth_provider_payload_uses_expected_defaults() -> None:
    google = _oauth_provider_payload("google", "http://localhost:8081")
    github = _oauth_provider_payload("github", "http://localhost:8081")

    assert google["redirect_uri"].endswith("/api/v1/auth/oauth/google/callback")
    assert google["default_role"] == "workspace_member"
    assert google["scopes"] == ["openid", "email", "profile"]

    assert github["redirect_uri"].endswith("/api/v1/auth/oauth/github/callback")
    assert github["default_role"] == "workspace_admin"
    assert github["scopes"] == ["read:user", "user:email"]


@pytest.mark.asyncio
async def test_create_governance_chain_validates_roles_and_updates_workspace_chain() -> None:
    workspace_id = str(uuid4())
    observer_fqn = "journey:observer"
    judge_fqn = "journey:judge"
    enforcer_fqn = "journey:enforcer"
    chain_url = f"/api/v1/workspaces/{workspace_id}/governance-chain"

    client = _FakeClient(
        {
            ("GET", f"/api/v1/agents/resolve/{observer_fqn}"): _json_response(
                "GET", f"/api/v1/agents/resolve/{observer_fqn}", {"role_types": ["observer"]}
            ),
            ("GET", f"/api/v1/agents/resolve/{judge_fqn}"): _json_response(
                "GET", f"/api/v1/agents/resolve/{judge_fqn}", {"role_types": ["judge"]}
            ),
            ("GET", f"/api/v1/agents/resolve/{enforcer_fqn}"): _json_response(
                "GET", f"/api/v1/agents/resolve/{enforcer_fqn}", {"role_types": ["enforcer"]}
            ),
            ("PUT", chain_url): _json_response(
                "PUT",
                chain_url,
                {
                    "id": str(uuid4()),
                    "workspace_id": workspace_id,
                    "observer_fqns": [observer_fqn],
                    "judge_fqns": [judge_fqn],
                    "enforcer_fqns": [enforcer_fqn],
                    "policy_binding_ids": [],
                    "verdict_to_action_mapping": {},
                },
            ),
        }
    )

    result = await create_governance_chain(
        client,
        workspace_id,
        observer_fqn=observer_fqn,
        judge_fqn=judge_fqn,
        enforcer_fqn=enforcer_fqn,
    )

    assert result["workspace_id"] == workspace_id
    assert result["observer_fqn"] == observer_fqn
    assert result["judge_fqn"] == judge_fqn
    assert result["enforcer_fqn"] == enforcer_fqn
    assert client.calls[-1] == (
        "PUT",
        chain_url,
        None,
        {
            "observer_fqns": [observer_fqn],
            "judge_fqns": [judge_fqn],
            "enforcer_fqns": [enforcer_fqn],
            "policy_binding_ids": [],
            "verdict_to_action_mapping": {},
        },
    )


@pytest.mark.asyncio
async def test_create_governance_chain_rejects_wrong_agent_role() -> None:
    workspace_id = str(uuid4())
    client = _FakeClient(
        {
            ("GET", "/api/v1/agents/resolve/journey:observer"): _json_response(
                "GET",
                "/api/v1/agents/resolve/journey:observer",
                {"role_types": ["executor"]},
            )
        }
    )

    with pytest.raises(AssertionError, match="missing required role 'observer'"):
        await create_governance_chain(
            client,
            workspace_id,
            observer_fqn="journey:observer",
            judge_fqn="journey:judge",
            enforcer_fqn="journey:enforcer",
        )


class _FakeWebSocket:
    def __init__(self, inbound: list[dict[str, object] | str]) -> None:
        self._inbound = [item if isinstance(item, str) else json.dumps(item) for item in inbound]
        self.sent_messages: list[dict[str, object]] = []
        self.closed = False

    async def recv(self) -> str:
        if not self._inbound:
            raise AssertionError("no websocket messages left to receive")
        return self._inbound.pop(0)

    async def send(self, payload: str) -> None:
        self.sent_messages.append(json.loads(payload))

    async def close(self) -> None:
        self.closed = True


class _FakeWsClient:
    def __init__(self, websocket: _FakeWebSocket) -> None:
        self.websocket = websocket

    async def connect(self) -> _FakeWebSocket:
        return self.websocket


@pytest.mark.asyncio
async def test_subscribe_ws_uses_ws_hub_protocol_and_consumes_handshake() -> None:
    websocket = _FakeWebSocket(
        [
            {"type": "connection_established", "connection_id": "conn-1", "user_id": str(uuid4())},
            {"type": "subscription_confirmed", "channel": "conversation", "resource_id": str(uuid4())},
            "",
            {"type": "heartbeat", "server_time": "2026-04-22T00:00:00Z"},
            {"type": "event", "channel": "conversation", "resource_id": "conv-1", "payload": {"event_type": "interaction.completed"}},
        ]
    )

    async with subscribe_ws(_FakeWsClient(websocket), "conversation", "conv-1") as subscription:
        event = await anext(subscription.events())

    assert websocket.sent_messages == [
        {"type": "subscribe", "channel": "conversation", "resource_id": "conv-1"}
    ]
    assert subscription.channel == "conversation"
    assert subscription.resource_id == "conv-1"
    assert event["type"] == "event"
    assert subscription.received_events == [event]
    assert websocket.closed is True


@pytest.mark.asyncio
async def test_subscribe_ws_buffers_events_before_confirmation() -> None:
    early_event = {
        "type": "event",
        "channel": "conversation",
        "resource_id": "conv-1",
        "payload": {"event_type": "interaction.created"},
    }
    websocket = _FakeWebSocket(
        [
            {"type": "connection_established", "connection_id": "conn-1", "user_id": str(uuid4())},
            early_event,
            {"type": "subscription_confirmed", "channel": "conversation", "resource_id": "conv-1"},
        ]
    )

    async with subscribe_ws(_FakeWsClient(websocket), "conversation", "conv-1") as subscription:
        event = await anext(subscription.events())

    assert event == early_event
    assert subscription.received_events == [early_event]
    assert websocket.closed is True
