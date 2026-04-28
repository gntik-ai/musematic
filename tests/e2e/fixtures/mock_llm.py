from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import pytest


class MockLLMController:
    def __init__(self, http_client) -> None:
        self.http_client = http_client

    async def set_response(
        self,
        prompt_pattern: str,
        response: str,
        streaming_chunks: list[str] | None = None,
    ) -> dict[str, int]:
        api_response = await self.http_client.post(
            "/api/v1/_e2e/mock-llm/set-response",
            json={
                "prompt_pattern": prompt_pattern,
                "response": response,
                "streaming_chunks": streaming_chunks,
            },
        )
        assert api_response.status_code == 200, api_response.text
        return api_response.json()["queue_depth"]

    async def set_responses(self, pattern_to_responses: dict[str, list[str]]) -> None:
        for pattern, responses in pattern_to_responses.items():
            for response in responses:
                await self.set_response(pattern, response)

    async def get_calls(
        self,
        pattern: str | None = None,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if pattern:
            params["pattern"] = pattern
        if since:
            params["since"] = since.isoformat()
        response = await self.http_client.get("/api/v1/_e2e/mock-llm/calls", params=params)
        if response.status_code == 404:
            return []
        assert response.status_code == 200, response.text
        payload = response.json()
        return payload.get("calls", payload if isinstance(payload, list) else [])

    async def clear_queue(self) -> None:
        response = await self.http_client.post(
            "/api/v1/_e2e/mock-llm/clear",
            json={},
        )
        assert response.status_code in {200, 202, 204, 404}, response.text


@pytest.fixture(scope="function")
async def mock_llm(http_client) -> AsyncIterator[MockLLMController]:
    controller = MockLLMController(http_client)
    try:
        yield controller
    finally:
        await controller.clear_queue()
