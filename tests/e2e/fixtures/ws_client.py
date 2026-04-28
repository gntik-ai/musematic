from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
import websockets


class WsClient:
    def __init__(self, base_url: str, *, token: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.websocket: Any | None = None

    async def __aenter__(self) -> WsClient:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.websocket = await websockets.connect(
            f"{self.base_url}/api/v1/ws",
            additional_headers=headers,
        )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self.websocket is not None:
            await self.websocket.close()

    async def subscribe(self, channel: str, topic: str) -> None:
        assert self.websocket is not None
        await self.websocket.send(
            json.dumps({"type": "subscribe", "channel": channel, "topic": topic}),
        )

    async def expect_event(
        self,
        channel: str,
        event: str,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        assert self.websocket is not None
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            assert remaining > 0, f"Timed out waiting for {channel}:{event}"
            message = await asyncio.wait_for(self.websocket.recv(), remaining)
            payload = json.loads(message)
            if payload.get("channel") == channel and payload.get("event") == event:
                return payload

    async def drain(self, timeout: float = 0.1) -> list[dict[str, Any]]:
        assert self.websocket is not None
        drained: list[dict[str, Any]] = []
        while True:
            try:
                message = await asyncio.wait_for(self.websocket.recv(), timeout)
            except TimeoutError:
                return drained
            drained.append(json.loads(message))


@pytest.fixture(scope="function")
async def ws_client(http_client, platform_ws_url: str) -> AsyncIterator[WsClient]:
    async with WsClient(platform_ws_url, token=http_client.access_token) as client:
        yield client
