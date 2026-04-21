from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass(slots=True)
class JourneySubscription:
    websocket: Any
    channel: str
    resource_id: str
    received_events: list[dict[str, Any]] = field(default_factory=list)

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            payload = json.loads(await self.websocket.recv())
            self.received_events.append(payload)
            yield payload


async def _expect_handshake_message(websocket: Any, *, expected_type: str) -> dict[str, Any]:
    payload = json.loads(await websocket.recv())
    if payload.get("type") != expected_type:
        raise AssertionError(
            f"expected websocket message type {expected_type!r}, got {payload.get('type')!r}"
        )
    return payload


@asynccontextmanager
async def subscribe_ws(ws_client, channel: str, topic: str) -> AsyncIterator[JourneySubscription]:
    websocket = await ws_client.connect()
    await _expect_handshake_message(websocket, expected_type="connection_established")
    await websocket.send(
        json.dumps(
            {
                "type": "subscribe",
                "channel": channel,
                "resource_id": topic,
            }
        )
    )
    confirmation = await websocket.recv()
    payload = json.loads(confirmation)
    if payload.get("type") == "subscription_error":
        raise AssertionError(
            f"websocket subscription failed for {channel}:{topic}: {payload.get('error')}"
        )
    if payload.get("type") != "subscription_confirmed":
        raise AssertionError(
            f"expected websocket subscription confirmation, got {payload.get('type')!r}"
        )
    subscription = JourneySubscription(websocket=websocket, channel=channel, resource_id=topic)
    try:
        yield subscription
    finally:
        await websocket.close()


def assert_event_order(events: list[dict[str, Any]], expected_types: list[str]) -> None:
    cursor = 0
    matched: list[str] = []
    for event in events:
        event_type = str(event.get("payload", {}).get("event_type") or event.get("type"))
        if cursor < len(expected_types) and event_type == expected_types[cursor]:
            matched.append(event_type)
            cursor += 1
    if cursor != len(expected_types):
        raise AssertionError(
            f"event order mismatch: expected {expected_types}, matched prefix {matched}"
        )
