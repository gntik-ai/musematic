from __future__ import annotations

import json
from uuid import uuid4

import httpx
import jwt
import pytest

from journeys.conftest import (
    _grant_required_consents,
    _mint_access_token,
    _oauth_provider_payload,
    _persona_email,
    _persona_roles,
    _persona_user_id,
)
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


@pytest.mark.asyncio
async def test_grant_required_consents_records_all_privacy_choices() -> None:
    workspace_id = uuid4()
    client = _FakeClient(
        {
            ("PUT", "/api/v1/me/consents"): _json_response(
                "PUT",
                "/api/v1/me/consents",
                {"items": []},
            )
        }
    )

    await _grant_required_consents(client, workspace_id=workspace_id)

    assert client.calls == [
        (
            "PUT",
            "/api/v1/me/consents",
            None,
            {
                "choices": {
                    "ai_interaction": True,
                    "data_collection": True,
                    "training_use": True,
                },
                "workspace_id": str(workspace_id),
            },
        )
    ]


class _FakeWebSocket:
    def __init__(self, inbound: list[dict[str, object] | str | BaseException]) -> None:
        self._inbound = [
            item if isinstance(item, (str, BaseException)) else json.dumps(item)
            for item in inbound
        ]
        self.sent_messages: list[dict[str, object]] = []
        self.closed = False

    async def recv(self) -> str:
        if not self._inbound:
            raise AssertionError("no websocket messages left to receive")
        item = self._inbound.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def send(self, payload: str) -> None:
        self.sent_messages.append(json.loads(payload))

    async def close(self) -> None:
        self.closed = True


class _FakeWsClient:
    def __init__(self, websocket: _FakeWebSocket) -> None:
        self.websocket = websocket

    async def connect(self) -> _FakeWebSocket:
        return self.websocket


class _SequenceWsClient:
    def __init__(self, *websockets: _FakeWebSocket) -> None:
        self.websockets = list(websockets)
        self.connect_count = 0

    async def connect(self) -> _FakeWebSocket:
        self.connect_count += 1
        if not self.websockets:
            raise AssertionError("no fake websocket connections left")
        return self.websockets.pop(0)


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


@pytest.mark.asyncio
async def test_subscribe_ws_retries_transient_handshake_failure() -> None:
    first = _FakeWebSocket([OSError("temporary handshake close")])
    second = _FakeWebSocket(
        [
            {"type": "connection_established", "connection_id": "conn-1", "user_id": str(uuid4())},
            {"type": "subscription_confirmed", "channel": "conversation", "resource_id": "conv-1"},
        ]
    )
    client = _SequenceWsClient(first, second)

    async with subscribe_ws(client, "conversation", "conv-1") as subscription:
        assert subscription.channel == "conversation"

    assert client.connect_count == 2
    assert first.closed is True
    assert second.closed is True


# UPD-054 (107) — every new SaaS-pass journey MUST carry the three
# pytestmarks documented in specs/107-saas-e2e-journeys/contracts/
# journey-template.md (.journey, .j{NN}, .timeout(480)). The check below
# walks tests/e2e/journeys/test_j*.py and fails the suite if any file
# is missing one of them.

import re  # noqa: E402
from pathlib import Path  # noqa: E402

_JOURNEY_PATH_RE = re.compile(r"test_j(\d{2})[^/]*\.py$")
# The UPD-054 journey-template marker contract applies to the SaaS-pass
# journeys (J22-J37) only. J01-J21 predate UPD-054 and own their own
# scaffolding conventions; enforcing the new contract on them is out of
# scope for this feature.
_SAAS_PASS_JOURNEY_RANGE = range(22, 38)


def _enumerate_saas_pass_journey_files() -> list[Path]:
    journeys_dir = Path(__file__).resolve().parent
    out: list[Path] = []
    for path in journeys_dir.glob("test_j*.py"):
        match = _JOURNEY_PATH_RE.search(str(path))
        if match is None:
            continue
        nn = int(match.group(1))
        if nn in _SAAS_PASS_JOURNEY_RANGE:
            out.append(path)
    return sorted(out)


def test_saas_journey_files_carry_required_pytestmarks() -> None:
    """Every J22-J37 file under tests/e2e/journeys/ MUST declare a
    module-level ``pytestmark`` block listing pytest.mark.journey,
    pytest.mark.j{NN} (matching the file's NN), and pytest.mark.timeout(480).
    The contract is documented in
    ``specs/107-saas-e2e-journeys/contracts/journey-template.md``.
    """
    failures: list[str] = []
    for path in _enumerate_saas_pass_journey_files():
        match = _JOURNEY_PATH_RE.search(str(path))
        assert match is not None, f"Could not parse journey number from {path}"
        nn = match.group(1)
        text = path.read_text(encoding="utf-8")
        if "pytestmark" not in text:
            failures.append(f"{path.name}: missing module-level pytestmark block")
            continue
        if "pytest.mark.journey" not in text:
            failures.append(f"{path.name}: missing pytest.mark.journey")
        if f"pytest.mark.j{nn}" not in text:
            failures.append(f"{path.name}: missing pytest.mark.j{nn}")
        if "pytest.mark.timeout" not in text:
            failures.append(f"{path.name}: missing pytest.mark.timeout(480)")
    assert not failures, "Journey-template marker violations:\n  " + "\n  ".join(failures)
