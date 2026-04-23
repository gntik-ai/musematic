from __future__ import annotations

import json
from platform.a2a_gateway.exceptions import A2AUnsupportedCapabilityError
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
async def test_get_card_missing_endpoint_and_database_fallback() -> None:
    registry = ExternalAgentCardRegistry(
        repository=FakeA2ARepository(), redis_client=FakeRedisClient()
    )
    with pytest.raises(A2AUnsupportedCapabilityError):
        await registry.get_card("missing")

    endpoint = build_endpoint(
        cached_agent_card={"skills": [], "version": "1.0"}, card_is_stale=True
    )
    repo = FakeA2ARepository()
    repo.endpoints[endpoint.id] = endpoint
    registry = ExternalAgentCardRegistry(repository=repo, redis_client=FakeRedisClient())

    payload = await registry.get_card(endpoint.id)

    assert payload == {"card": endpoint.cached_agent_card, "is_stale": True}


@pytest.mark.asyncio
async def test_refresh_if_expired_prefers_cached_values_and_restores_redis() -> None:
    endpoint = build_endpoint(
        card_cached_at=expired_time(-5),
        cached_agent_card={"skills": [], "version": "1.0"},
    )
    repo = FakeA2ARepository()
    redis = FakeRedisClient()
    registry = ExternalAgentCardRegistry(repository=repo, redis_client=redis)

    payload = await registry.refresh_if_expired(endpoint)

    assert payload == {"card": {"skills": [], "version": "1.0"}, "is_stale": False}
    cache_key = registry._cache_key(endpoint.endpoint_url)
    assert json.loads(redis.store[cache_key].decode("utf-8"))["version"] == "1.0"


@pytest.mark.asyncio
async def test_refresh_if_expired_raises_without_cached_card_and_fetch_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = build_endpoint(card_cached_at=expired_time(120), cached_agent_card=None)
    repo = FakeA2ARepository()
    repo.endpoints[endpoint.id] = endpoint
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503, json={"error": "nope"}))
    )
    registry = ExternalAgentCardRegistry(
        repository=repo, redis_client=FakeRedisClient(), http_client=client
    )

    with pytest.raises(httpx.HTTPStatusError):
        await registry.refresh_if_expired(endpoint)
    await client.aclose()

    class AutoClient:
        def __init__(self, payload):
            self.payload = payload
            self.closed = False

        async def get(self, url: str):
            response = httpx.Response(200, json=self.payload)
            response.request = httpx.Request("GET", url)
            return response

        async def aclose(self) -> None:
            self.closed = True

    invalid_client = AutoClient({"version": "1.0"})
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=10.0: invalid_client)
    registry = ExternalAgentCardRegistry(repository=repo, redis_client=FakeRedisClient())
    with pytest.raises(A2AUnsupportedCapabilityError):
        await registry._fetch_card(endpoint.agent_card_url)
    assert invalid_client.closed is True


@pytest.mark.asyncio
async def test_invalidate_and_redis_helpers_cover_stable_version_and_non_dict() -> None:
    endpoint = build_endpoint(declared_version="1.0")
    redis = FakeRedisClient(store={"cache:a2a_card:deadbeef": json.dumps([1, 2]).encode("utf-8")})
    registry = ExternalAgentCardRegistry(repository=FakeA2ARepository(), redis_client=redis)
    registry._cache_hash = lambda endpoint_url: "deadbeef"  # type: ignore[method-assign]

    await registry.invalidate_if_version_changed(endpoint, {"version": "1.0", "skills": []})

    assert redis.store == {"cache:a2a_card:deadbeef": json.dumps([1, 2]).encode("utf-8")}
    assert await registry._redis_get_json("cache:a2a_card:deadbeef") is None


@pytest.mark.asyncio
async def test_get_card_fetches_when_cache_is_empty() -> None:
    endpoint = build_endpoint(card_cached_at=None, cached_agent_card=None)
    repo = FakeA2ARepository()
    repo.endpoints[endpoint.id] = endpoint
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"skills": [], "version": "1.1"})
        )
    )
    registry = ExternalAgentCardRegistry(
        repository=repo, redis_client=FakeRedisClient(), http_client=client
    )

    payload = await registry.get_card(endpoint.id)
    await client.aclose()

    assert payload == {"card": {"skills": [], "version": "1.1"}, "is_stale": False}
