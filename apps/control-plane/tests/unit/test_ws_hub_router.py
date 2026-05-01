from __future__ import annotations

import json
from platform.ws_hub.router import websocket_endpoint
from uuid import uuid4

import pytest

from tests.ws_hub_support import (
    FakeWebSocket,
    RecordingFanout,
    StaticAuthService,
    StaticWorkspacesService,
    build_state,
)


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
    assert fanout.ensured[0] == ["auth.events"]
    assert fanout.ensured[1] == ["monitor.alerts", "notifications.alerts"]
    assert fanout.ensured[2] == ["interaction.attention"]
    assert fanout.ensured[3] == [
        "incident_response.events",
        "multi_region_ops.events",
        "platform.status.derived",
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
