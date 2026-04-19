from __future__ import annotations

from platform.a2a_gateway.external_registry import ExternalAgentCardRegistry

import httpx
import pytest
from tests.a2a_gateway_support import (
    FakeA2ARepository,
    FakeRedisClient,
    build_endpoint,
    expired_time,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_external_registry_caches_refreshes_and_falls_back_to_stale() -> None:
    endpoint = build_endpoint(card_ttl_seconds=5)
    repo = FakeA2ARepository()
    repo.endpoints[endpoint.id] = endpoint
    redis = FakeRedisClient()
    calls = {"count": 0}

    def ok_handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"skills": [], "version": str(calls["count"])})

    client = httpx.AsyncClient(transport=httpx.MockTransport(ok_handler))
    registry = ExternalAgentCardRegistry(repository=repo, redis_client=redis, http_client=client)

    first = await registry.get_card(endpoint.id)
    second = await registry.get_card(endpoint.id)
    endpoint.card_cached_at = expired_time(10)
    refreshed = await registry.refresh_if_expired(endpoint)
    await client.aclose()

    stale_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503, json={"error": "down"}))
    )
    stale_registry = ExternalAgentCardRegistry(
        repository=repo, redis_client=redis, http_client=stale_client
    )
    endpoint.card_cached_at = expired_time(10)
    stale = await stale_registry.refresh_if_expired(endpoint)
    await stale_client.aclose()

    assert first["card"]["version"] == "1"
    assert second["card"]["version"] == "1"
    assert calls["count"] == 2
    assert refreshed["card"]["version"] == "2"
    assert stale["is_stale"] is True
