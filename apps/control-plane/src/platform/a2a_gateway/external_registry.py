from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from platform.a2a_gateway.exceptions import A2AUnsupportedCapabilityError
from platform.a2a_gateway.models import A2AExternalEndpoint
from platform.a2a_gateway.repository import A2AGatewayRepository
from typing import Any

import httpx


class ExternalAgentCardRegistry:
    def __init__(
        self,
        *,
        repository: A2AGatewayRepository,
        redis_client: Any,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.repository = repository
        self.redis_client = redis_client
        self.http_client = http_client

    def _cache_hash(self, endpoint_url: str) -> str:
        return hashlib.sha256(endpoint_url.encode("utf-8")).hexdigest()[:16]

    def _cache_key(self, endpoint_url: str) -> str:
        return f"cache:a2a_card:{self._cache_hash(endpoint_url)}"

    def _stale_key(self, endpoint_url: str) -> str:
        return f"cache:a2a_card_stale:{self._cache_hash(endpoint_url)}"

    async def get_card(self, endpoint_id: Any, session: Any | None = None) -> dict[str, Any]:
        del session
        endpoint = await self.repository.get_external_endpoint(endpoint_id, include_deleted=True)
        if endpoint is None:
            raise A2AUnsupportedCapabilityError("external_endpoint_missing")
        payload = await self._redis_get_json(self._cache_key(endpoint.endpoint_url))
        if payload is not None:
            stale = await self.redis_client.get(self._stale_key(endpoint.endpoint_url))
            return {"card": payload, "is_stale": bool(stale)}
        if endpoint.cached_agent_card is not None:
            return {"card": endpoint.cached_agent_card, "is_stale": endpoint.card_is_stale}
        return await self.fetch_and_cache(endpoint)

    async def fetch_and_cache(
        self,
        endpoint: A2AExternalEndpoint,
        session: Any | None = None,
    ) -> dict[str, Any]:
        del session
        card = await self._fetch_card(endpoint.agent_card_url)
        await self.invalidate_if_version_changed(endpoint, card)
        await self.repository.update_external_endpoint_cache(
            endpoint,
            cached_agent_card=card,
            card_cached_at=datetime.now(UTC),
            card_is_stale=False,
            declared_version=str(card.get("version") or ""),
        )
        await self._redis_set_json(
            self._cache_key(endpoint.endpoint_url),
            card,
            ttl=max(endpoint.card_ttl_seconds, 1),
        )
        await self.redis_client.delete(self._stale_key(endpoint.endpoint_url))
        return {"card": card, "is_stale": False}

    async def refresh_if_expired(
        self,
        endpoint: A2AExternalEndpoint,
        session: Any | None = None,
    ) -> dict[str, Any]:
        del session
        now = datetime.now(UTC)
        expired = endpoint.card_cached_at is None
        if endpoint.card_cached_at is not None:
            expired = endpoint.card_cached_at + timedelta(seconds=endpoint.card_ttl_seconds) <= now
        if not expired and endpoint.cached_agent_card is not None:
            cached = await self._redis_get_json(self._cache_key(endpoint.endpoint_url))
            if cached is not None:
                stale = await self.redis_client.get(self._stale_key(endpoint.endpoint_url))
                return {"card": cached, "is_stale": bool(stale)}
            await self._redis_set_json(
                self._cache_key(endpoint.endpoint_url),
                endpoint.cached_agent_card,
                ttl=max(endpoint.card_ttl_seconds, 1),
            )
            return {"card": endpoint.cached_agent_card, "is_stale": endpoint.card_is_stale}
        try:
            return await self.fetch_and_cache(endpoint)
        except Exception:
            if endpoint.cached_agent_card is None:
                raise
            await self.repository.update_external_endpoint_cache(endpoint, card_is_stale=True)
            await self.redis_client.set(
                self._stale_key(endpoint.endpoint_url),
                b"1",
                ttl=max(endpoint.card_ttl_seconds * 2, 1),
            )
            return {"card": endpoint.cached_agent_card, "is_stale": True}

    async def invalidate_if_version_changed(
        self,
        endpoint: A2AExternalEndpoint,
        new_card: dict[str, Any],
        session: Any | None = None,
    ) -> None:
        del session
        new_version = str(new_card.get("version") or "") or None
        if endpoint.declared_version != new_version:
            await self.redis_client.delete(self._cache_key(endpoint.endpoint_url))
            await self.redis_client.delete(self._stale_key(endpoint.endpoint_url))

    async def _fetch_card(self, url: str) -> dict[str, Any]:
        client = self.http_client
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)
            should_close = True
        try:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or "skills" not in payload:
                raise A2AUnsupportedCapabilityError("invalid_agent_card")
            return payload
        finally:
            if should_close:
                await client.aclose()

    async def _redis_get_json(self, key: str) -> dict[str, Any] | None:
        raw = await self.redis_client.get(key)
        if raw is None:
            return None
        decoded = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        payload = json.loads(decoded)
        return payload if isinstance(payload, dict) else None

    async def _redis_set_json(self, key: str, payload: dict[str, Any], *, ttl: int) -> None:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        await self.redis_client.set(key, encoded, ttl=ttl)
