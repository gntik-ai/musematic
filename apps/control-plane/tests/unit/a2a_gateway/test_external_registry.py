from __future__ import annotations

import json
from platform.a2a_gateway.external_registry import ExternalAgentCardRegistry

import httpx
import pytest
from tests.a2a_gateway_support import (
    FakeA2ARepository,
    FakeRedisClient,
    build_endpoint,
    expired_time,
)


@pytest.mark.asyncio
async def test_get_card_prefers_redis_cache_and_reports_stale_flag() -> None:
    endpoint = build_endpoint()
    repo = FakeA2ARepository()
    repo.endpoints[endpoint.id] = endpoint
    redis = FakeRedisClient(
        store={
            f"cache:a2a_card:{endpoint.endpoint_url.encode().hex()[:16]}": b"{}",
        }
    )
    cache_key = f"cache:a2a_card:{repo.endpoints[endpoint.id].endpoint_url.encode().hex()[:16]}"
    redis.store = {
        cache_key: json.dumps({"skills": [], "version": "1.0"}).encode("utf-8"),
        f"cache:a2a_card_stale:{endpoint.endpoint_url.encode().hex()[:16]}": b"1",
    }
    registry = ExternalAgentCardRegistry(repository=repo, redis_client=redis)
    registry._cache_hash = lambda endpoint_url: endpoint.endpoint_url.encode().hex()[:16]  # type: ignore[method-assign]

    payload = await registry.get_card(endpoint.id)

    assert payload == {"card": {"skills": [], "version": "1.0"}, "is_stale": True}


@pytest.mark.asyncio
async def test_refresh_if_expired_fetches_and_caches_fresh_card() -> None:
    endpoint = build_endpoint(card_cached_at=expired_time(120), cached_agent_card={"skills": []})
    repo = FakeA2ARepository()
    repo.endpoints[endpoint.id] = endpoint
    redis = FakeRedisClient()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == endpoint.agent_card_url
        return httpx.Response(200, json={"skills": [], "version": "2.0"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    registry = ExternalAgentCardRegistry(repository=repo, redis_client=redis, http_client=client)

    payload = await registry.refresh_if_expired(endpoint)
    await client.aclose()

    assert payload == {"card": {"skills": [], "version": "2.0"}, "is_stale": False}
    assert endpoint.cached_agent_card == {"skills": [], "version": "2.0"}
    assert endpoint.declared_version == "2.0"


@pytest.mark.asyncio
async def test_refresh_if_expired_falls_back_to_stale_cached_card_on_fetch_failure() -> None:
    cached = {"skills": [], "version": "1.0"}
    endpoint = build_endpoint(card_cached_at=expired_time(120), cached_agent_card=cached)
    repo = FakeA2ARepository()
    repo.endpoints[endpoint.id] = endpoint
    redis = FakeRedisClient()

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, json={"error": "unavailable"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    registry = ExternalAgentCardRegistry(repository=repo, redis_client=redis, http_client=client)

    payload = await registry.refresh_if_expired(endpoint)
    await client.aclose()

    assert payload == {"card": cached, "is_stale": True}
    assert endpoint.card_is_stale is True


@pytest.mark.asyncio
async def test_invalidate_if_version_changed_clears_cached_keys() -> None:
    endpoint = build_endpoint(declared_version="1.0")
    repo = FakeA2ARepository()
    redis = FakeRedisClient(
        store={
            "cache:a2a_card:deadbeef": b"x",
            "cache:a2a_card_stale:deadbeef": b"1",
        }
    )
    registry = ExternalAgentCardRegistry(repository=repo, redis_client=redis)
    registry._cache_hash = lambda endpoint_url: "deadbeef"  # type: ignore[method-assign]

    await registry.invalidate_if_version_changed(endpoint, {"version": "2.0", "skills": []})

    assert redis.store == {}
