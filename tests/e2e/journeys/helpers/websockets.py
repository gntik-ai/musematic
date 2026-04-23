from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


async def _read_json_message(websocket: Any) -> dict[str, Any]:
    while True:
        raw = await websocket.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if raw == "":
            continue
        payload = json.loads(raw)
        if payload.get("type") == "heartbeat":
            continue
        return payload


@dataclass(slots=True)
class JourneySubscription:
    websocket: Any
    channel: str
    resource_id: str
    received_events: list[dict[str, Any]] = field(default_factory=list)
    pending_events: list[dict[str, Any]] = field(default_factory=list)

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        while self.pending_events:
            payload = self.pending_events.pop(0)
            self.received_events.append(payload)
            yield payload
        while True:
            payload = await _read_json_message(self.websocket)
            self.received_events.append(payload)
            yield payload


async def _expect_handshake_message(websocket: Any, *, expected_type: str) -> dict[str, Any]:
    payload = await _read_json_message(websocket)
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
    pending_events: list[dict[str, Any]] = []
    while True:
        payload = await _read_json_message(websocket)
        if payload.get("type") == "subscription_error":
            raise AssertionError(
                f"websocket subscription failed for {channel}:{topic}: {payload.get('error')}"
            )
        if payload.get("type") == "subscription_confirmed":
            break
        if payload.get("type") == "event":
            pending_events.append(payload)
            continue
        raise AssertionError(
            f"expected websocket subscription confirmation, got {payload.get('type')!r}"
        )
    subscription = JourneySubscription(
        websocket=websocket,
        channel=channel,
        resource_id=topic,
        pending_events=pending_events,
    )
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
