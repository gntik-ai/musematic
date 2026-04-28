from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest


class WsClient:
    def __init__(
        self, base_url: str, *, token: str | None, http_client: Any | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.http_client = http_client
        self._seen: dict[tuple[str, str], int] = {}

    async def __aenter__(self) -> WsClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def subscribe(self, channel: str, topic: str) -> None:
        del topic
        self._seen.setdefault((channel, ""), 0)

    async def expect_event(
        self,
        channel: str,
        event: str,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout
        key = (channel, event)
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            assert remaining > 0, f"Timed out waiting for {channel}:{event}"
            assert self.http_client is not None
            response = await self.http_client.get(
                "/api/v1/_e2e/contract/ws-events",
                params={"channel": channel, "event": event},
            )
            assert response.status_code == 200, response.text
            items = response.json().get("items", [])
            start = self._seen.get(key, 0)
            if len(items) > start:
                self._seen[key] = start + 1
                return items[start]
            await asyncio.sleep(min(remaining, 0.2))

    async def drain(self, timeout: float = 0.1) -> list[dict[str, Any]]:
        await asyncio.sleep(timeout)
        return []


@pytest.fixture(scope="function")
async def ws_client(http_client, platform_ws_url: str) -> AsyncIterator[WsClient]:
    async with WsClient(
        platform_ws_url,
        token=http_client.access_token,
        http_client=http_client,
    ) as client:
        yield client
