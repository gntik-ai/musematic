from __future__ import annotations

import asyncio
import json
from platform.common.tenant_context import TenantContext, current_tenant
from platform.ws_hub import router as ws_router
from platform.ws_hub.router import _workspace_ids_from_payload, websocket_endpoint
from typing import Any
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.ws_hub_support import (
    FakeWebSocket,
    RecordingFanout,
    StaticAuthService,
    StaticWorkspacesService,
    build_state,
)


class BlockingReceiveWebSocket(FakeWebSocket):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.disconnect_requested = asyncio.Event()

    async def receive_text(self) -> str:
        await self.disconnect_requested.wait()
        raise WebSocketDisconnect(code=1000)


class BlockingFirstEnsureFanout(RecordingFanout):
    def __init__(self) -> None:
        super().__init__()
        self.block_started = asyncio.Event()
        self.release_block = asyncio.Event()
        self._blocked_once = False

    async def ensure_consuming(self, topics: list[str]) -> None:
        self.ensured.append(sorted(topics))
        if not self._blocked_once:
            self._blocked_once = True
            self.block_started.set()
            await self.release_block.wait()


class StaticTenantResolver:
    def __init__(self, tenant: TenantContext | None) -> None:
        self.tenant = tenant
        self.hosts: list[str] = []

    async def resolve(self, host: str) -> TenantContext | None:
        self.hosts.append(host)
        return self.tenant


class TenantAwareAuthService(StaticAuthService):
    def __init__(self, tenant: TenantContext, token_payloads: dict[str, dict[str, Any]]) -> None:
        super().__init__(token_payloads)
        self.tenant = tenant

    async def validate_token(self, token: str) -> dict[str, Any]:
        assert current_tenant.get(None) == self.tenant
        return await super().validate_token(token)


def test_workspace_ids_from_payload_reads_top_level_and_role_scoped_claims() -> None:
    top_level_workspace_id = uuid4()
    role_workspace_id = uuid4()

    assert _workspace_ids_from_payload(
        {
            "workspace_id": str(top_level_workspace_id),
            "roles": [
                {"role": "workspace_member", "workspace_id": str(role_workspace_id)},
                {"role": "platform_admin", "workspace_id": None},
                {"role": "bad", "workspace_id": "not-a-uuid"},
            ],
        }
    ) == {top_level_workspace_id, role_workspace_id}


@pytest.mark.asyncio
async def test_websocket_endpoint_denies_missing_or_invalid_token() -> None:
    state = build_state()
    missing_token = FakeWebSocket(state)

    await websocket_endpoint(
        missing_token,
        state.connection_registry,
        state.subscription_registry,
        state.fanout,
        state.visibility_filter,
    )

    assert missing_token.denial_status_code == 401

    invalid_token = FakeWebSocket(state, headers={"Authorization": "Bearer bad-token"})
    await websocket_endpoint(
        invalid_token,
        state.connection_registry,
        state.subscription_registry,
        state.fanout,
        state.visibility_filter,
    )

    assert invalid_token.denial_status_code == 401


@pytest.mark.asyncio
async def test_websocket_endpoint_binds_tenant_before_auth_validation() -> None:
    tenant = TenantContext(
        id=uuid4(),
        slug="acme",
        subdomain="acme",
        kind="enterprise",
        status="active",
        region="eu",
    )
    user_id = uuid4()
    workspace_id = uuid4()
    token = "tenant-token"
    resolver = StaticTenantResolver(tenant)
    state = build_state(
        auth_service=TenantAwareAuthService(
            tenant,
            {token: {"sub": str(user_id), "type": "access"}},
        ),
        workspaces_service=StaticWorkspacesService(workspace_ids_by_user={user_id: [workspace_id]}),
    )
    state.tenant_resolver = resolver
    websocket = FakeWebSocket(
        state,
        headers={"Authorization": f"Bearer {token}", "host": "acme.localhost"},
    )

    await websocket_endpoint(
        websocket,
        state.connection_registry,
        state.subscription_registry,
        state.fanout,
        state.visibility_filter,
    )

    assert websocket.accepted is True
    assert resolver.hosts == ["acme.localhost"]
    assert current_tenant.get(None) is None


@pytest.mark.asyncio
async def test_websocket_endpoint_sends_welcome_and_cleans_up_last_connection() -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    token = "good-token"
    fanout = RecordingFanout()
    state = build_state(
        auth_service=StaticAuthService({token: {"sub": str(user_id), "type": "access"}}),
        workspaces_service=StaticWorkspacesService(workspace_ids_by_user={user_id: [workspace_id]}),
        fanout=fanout,
    )
    websocket = FakeWebSocket(state, headers={"Authorization": f"Bearer {token}"})

    await websocket_endpoint(
        websocket,
        state.connection_registry,
        state.subscription_registry,
        state.fanout,
        state.visibility_filter,
    )

    messages = websocket.decoded_messages()
    assert websocket.accepted is True
    assert messages[0]["type"] == "connection_established"
    assert [item["channel"] for item in messages[0]["auto_subscriptions"]] == [
        "alerts",
        "attention",
        "platform-status",
    ]
    assert fanout.released[-1] == [
        "auth.events",
        "incident_response.events",
        "interaction.attention",
        "monitor.alerts",
        "multi_region_ops.events",
        "notifications.alerts",
        "platform.status.derived",
    ]


@pytest.mark.asyncio
async def test_websocket_endpoint_sends_welcome_before_fanout_startup(monkeypatch) -> None:
    monkeypatch.setattr(ws_router, "_INITIAL_FANOUT_START_DELAY_SECONDS", 0)
    user_id = uuid4()
    workspace_id = uuid4()
    token = "good-token"
    fanout = BlockingFirstEnsureFanout()
    state = build_state(
        auth_service=StaticAuthService({token: {"sub": str(user_id), "type": "access"}}),
        workspaces_service=StaticWorkspacesService(workspace_ids_by_user={user_id: [workspace_id]}),
        fanout=fanout,
    )
    websocket = BlockingReceiveWebSocket(state, headers={"Authorization": f"Bearer {token}"})

    endpoint_task = asyncio.create_task(
        websocket_endpoint(
            websocket,
            state.connection_registry,
            state.subscription_registry,
            state.fanout,
            state.visibility_filter,
        )
    )

    try:
        await asyncio.wait_for(fanout.block_started.wait(), timeout=1)
        messages = websocket.decoded_messages()
        assert messages[0]["type"] == "connection_established"
        assert [item["channel"] for item in messages[0]["auto_subscriptions"]] == [
            "alerts",
            "attention",
            "platform-status",
        ]
    finally:
        fanout.release_block.set()
        websocket.disconnect_requested.set()
        await asyncio.wait_for(endpoint_task, timeout=1)


@pytest.mark.asyncio
async def test_websocket_endpoint_handles_subscribe_list_and_unsubscribe() -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    token = "good-token"
    resource_id = uuid4()
    fanout = RecordingFanout()
    state = build_state(
        auth_service=StaticAuthService({token: {"sub": str(user_id), "type": "access"}}),
        workspaces_service=StaticWorkspacesService(
            workspace_ids_by_user={user_id: [workspace_id]},
            resource_workspace_map={("workspace", resource_id): workspace_id},
        ),
        fanout=fanout,
    )
    websocket = FakeWebSocket(
        state,
        headers={"Authorization": f"Bearer {token}"},
        incoming=[
            json.dumps(
                {"type": "subscribe", "channel": "workspace", "resource_id": str(resource_id)}
            ),
            json.dumps({"type": "list_subscriptions"}),
            json.dumps(
                {
                    "type": "unsubscribe",
                    "channel": "attention",
                    "resource_id": str(user_id),
                }
            ),
            json.dumps(
                {"type": "unsubscribe", "channel": "workspace", "resource_id": str(resource_id)}
            ),
        ],
    )

    await websocket_endpoint(
        websocket,
        state.connection_registry,
        state.subscription_registry,
        state.fanout,
        state.visibility_filter,
    )

    messages = websocket.decoded_messages()
    assert [message["type"] for message in messages] == [
        "connection_established",
        "subscription_confirmed",
        "subscription_list",
        "subscription_error",
        "subscription_removed",
    ]
    assert [subscription["channel"] for subscription in messages[2]["subscriptions"]] == [
        "alerts",
        "attention",
        "platform-status",
        "workspace",
    ]
    assert messages[3]["code"] == "cannot_unsubscribe_auto"
    assert fanout.ensured[-1] == ["workspaces.events"]


@pytest.mark.asyncio
async def test_websocket_endpoint_handles_invalid_channel_and_protocol_violation_threshold() -> (
    None
):
    user_id = uuid4()
    token = "good-token"
    state = build_state(
        auth_service=StaticAuthService({token: {"sub": str(user_id), "type": "access"}}),
        workspaces_service=StaticWorkspacesService(workspace_ids_by_user={user_id: [uuid4()]}),
    )
    websocket = FakeWebSocket(
        state,
        headers={"Authorization": f"Bearer {token}"},
        incoming=[
            json.dumps({"type": "subscribe", "channel": "bad", "resource_id": str(uuid4())}),
            "not-json",
            "still-not-json",
        ],
    )

    await websocket_endpoint(
        websocket,
        state.connection_registry,
        state.subscription_registry,
        state.fanout,
        state.visibility_filter,
    )

    messages = websocket.decoded_messages()
    assert messages[1]["type"] == "subscription_error"
    assert messages[1]["code"] == "invalid_channel"
    assert messages[2]["type"] == "error"
    assert websocket.close_calls[-1][0] == 4400
