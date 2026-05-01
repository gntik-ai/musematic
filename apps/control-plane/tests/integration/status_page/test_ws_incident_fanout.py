from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.ws_hub.fanout import KafkaFanout
from platform.ws_hub.router import websocket_endpoint
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

pytestmark = pytest.mark.integration


class BlockingWebSocket(FakeWebSocket):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._disconnect = asyncio.Event()

    async def receive_text(self) -> str:
        await self._disconnect.wait()
        raise WebSocketDisconnect(code=1000)

    def disconnect(self) -> None:
        self._disconnect.set()


@pytest.mark.asyncio
async def test_platform_status_ws_fanout_for_incident_lifecycle() -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    token = "good-token"
    recording_fanout = RecordingFanout()
    state = build_state(
        auth_service=StaticAuthService({token: {"sub": str(user_id), "type": "access"}}),
        workspaces_service=StaticWorkspacesService(workspace_ids_by_user={user_id: [workspace_id]}),
        fanout=recording_fanout,
    )
    websocket = BlockingWebSocket(state, headers={"Authorization": f"Bearer {token}"})

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
        welcome = await _wait_for_message(websocket, message_type="connection_established")
        assert {
            (subscription["channel"], subscription["resource_id"], subscription["auto"])
            for subscription in welcome["auto_subscriptions"]
        } >= {
            ("platform-status", str(user_id), True),
        }

        fanout = KafkaFanout(
            state.connection_registry,
            state.subscription_registry,
            state.settings,
            state.visibility_filter,
        )
        incident_id = uuid4()

        await fanout._route_event(
            "incident_response.events",
            _incident_envelope("incident.triggered", incident_id).model_dump(mode="json"),
        )

        created = await _wait_for_message(
            websocket,
            message_type="event",
            event_type="platform.incident.created",
        )
        assert created["channel"] == "platform-status"
        assert created["resource_id"] == str(user_id)
        assert created["payload"]["source"] == "platform.ws_hub.platform_status"
        assert created["payload"]["payload"]["incident_id"] == str(incident_id)

        await fanout._route_event(
            "incident_response.events",
            _incident_envelope("incident.resolved", incident_id).model_dump(mode="json"),
        )

        resolved = await _wait_for_message(
            websocket,
            message_type="event",
            event_type="platform.incident.resolved",
        )
        assert resolved["channel"] == "platform-status"
        assert resolved["resource_id"] == str(user_id)
        assert resolved["payload"]["payload"]["incident_id"] == str(incident_id)
    finally:
        websocket.disconnect()
        await asyncio.wait_for(endpoint_task, timeout=1)


def _incident_envelope(event_type: str, incident_id) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        source="tests.status_page",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        occurred_at=datetime.now(UTC),
        payload={
            "incident_id": str(incident_id),
            "severity": "warning",
            "title": "Synthetic incident",
            "components_affected": ["control-plane-api"],
        },
    )


async def _wait_for_message(
    websocket: FakeWebSocket,
    *,
    message_type: str,
    event_type: str | None = None,
) -> dict:
    for _ in range(100):
        for message in websocket.decoded_messages():
            if message.get("type") != message_type:
                continue
            if (
                event_type is not None
                and message.get("payload", {}).get("event_type") != event_type
            ):
                continue
            return message
        await asyncio.sleep(0.01)
    raise AssertionError(f"Timed out waiting for {message_type}:{event_type or '*'}")
