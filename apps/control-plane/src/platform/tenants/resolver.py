from __future__ import annotations

import json
import time
from collections import OrderedDict
from collections.abc import Callable
from importlib import import_module
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.tenant_context import TenantContext
from platform.tenants.models import Tenant
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

DEFAULT_TENANT_SUBDOMAINS = frozenset({"app", "api", "grafana"})
TENANT_SURFACE_LABELS = frozenset({"api", "grafana"})
TENANT_INVALIDATION_CHANNEL = "tenants:invalidate"


class _LocalResolverCache:
    def __init__(self, *, maxsize: int, ttl_seconds: int) -> None:
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._entries: OrderedDict[str, tuple[float, TenantContext | None]] = OrderedDict()

    def get(self, key: str) -> TenantContext | None | object:
        entry = self._entries.get(key)
        if entry is None:
            return _MISSING
        expires_at, value = entry
        if expires_at <= time.monotonic():
            self._entries.pop(key, None)
            return _MISSING
        self._entries.move_to_end(key)
        return value

    def set(self, key: str, value: TenantContext | None, *, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds or self.ttl_seconds
        self._entries[key] = (time.monotonic() + ttl, value)
        self._entries.move_to_end(key)
        while len(self._entries) > self.maxsize:
            self._entries.popitem(last=False)

    def invalidate_tenant(self, tenant_id: str) -> None:
        stale = [
            key
            for key, (_, value) in self._entries.items()
            if value is not None and str(value.id) == tenant_id
        ]
        for key in stale:
            self._entries.pop(key, None)

    def invalidate_host(self, host: str) -> None:
        self._entries.pop(host, None)


_MISSING = object()


class TenantResolver:
    def __init__(
        self,
        *,
        settings: PlatformSettings,
        session_factory: async_sessionmaker[AsyncSession] | Callable[[], AsyncSession],
        redis_client: AsyncRedisClient | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.redis_client = redis_client
        self.ttl_seconds = settings.TENANT_RESOLVER_CACHE_TTL_SECONDS
        self._local_cache = _LocalResolverCache(maxsize=1024, ttl_seconds=self.ttl_seconds)
        self._metrics = _ResolverMetrics()

    async def resolve(self, host: str) -> TenantContext | None:
        started = time.perf_counter()
        normalized_host = self.normalize_host(host)
        if normalized_host is None:
            self._metrics.lookup("invalid_host")
            self._metrics.latency(time.perf_counter() - started)
            return None

        cached = self._local_cache.get(normalized_host)
        if cached is not _MISSING:
            self._metrics.cache_hit("local")
            self._metrics.lookup("hit" if cached is not None else "miss")
            self._metrics.latency(time.perf_counter() - started)
            return cached  # type: ignore[return-value]

        redis_cached = await self._get_redis_cached(normalized_host)
        if redis_cached is not _MISSING:
            self._metrics.cache_hit("redis")
            self._local_cache.set(normalized_host, redis_cached)  # type: ignore[arg-type]
            self._metrics.lookup("hit" if redis_cached is not None else "miss")
            self._metrics.latency(time.perf_counter() - started)
            return redis_cached  # type: ignore[return-value]

        lookup_subdomain = self._lookup_subdomain(normalized_host)
        if lookup_subdomain is None:
            await self._cache_miss(normalized_host)
            self._metrics.lookup("miss")
            self._metrics.latency(time.perf_counter() - started)
            return None

        tenant = await self._query_tenant(lookup_subdomain)
        context = self._to_context(tenant) if tenant is not None else None
        if context is None:
            await self._cache_miss(normalized_host)
            self._metrics.lookup("miss")
            self._metrics.latency(time.perf_counter() - started)
            return None

        self._local_cache.set(normalized_host, context)
        await self._set_redis_cached(normalized_host, context, ttl_seconds=self.ttl_seconds)
        self._metrics.lookup("hit")
        self._metrics.latency(time.perf_counter() - started)
        return context

    def normalize_host(self, host: str | None) -> str | None:
        if not host:
            return None
        normalized = host.strip().lower()
        if not normalized:
            return None
        if normalized.startswith("["):
            closing = normalized.find("]")
            if closing != -1:
                normalized = normalized[: closing + 1]
        else:
            normalized = normalized.split(":", 1)[0]
        domain = self.settings.PLATFORM_DOMAIN.strip().lower().rstrip(".")
        if normalized == domain or normalized.endswith(f".{domain}"):
            return normalized
        return None

    def invalidate_tenant(self, tenant_id: str) -> None:
        self._local_cache.invalidate_tenant(tenant_id)

    def invalidate_host(self, host: str) -> None:
        normalized_host = self.normalize_host(host)
        if normalized_host is not None:
            self._local_cache.invalidate_host(normalized_host)

    async def handle_invalidation_message(self, raw_message: bytes | str | dict[str, Any]) -> None:
        payload = _decode_invalidation_payload(raw_message)
        tenant_id = payload.get("tenant_id")
        if tenant_id is not None:
            self.invalidate_tenant(str(tenant_id))
        for host in payload.get("hosts", []):
            if isinstance(host, str):
                self.invalidate_host(host)

    async def listen_for_invalidations(self) -> None:
        if self.redis_client is None:
            return
        await self.redis_client.initialize()
        client = self.redis_client.client
        if client is None:
            return
        pubsub = cast(Any, client).pubsub()
        await pubsub.subscribe(TENANT_INVALIDATION_CHANNEL)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                await self.handle_invalidation_message(message.get("data", b"{}"))
        finally:
            await pubsub.unsubscribe(TENANT_INVALIDATION_CHANNEL)
            await pubsub.close()

    def _lookup_subdomain(self, normalized_host: str) -> str | None:
        domain = self.settings.PLATFORM_DOMAIN.strip().lower().rstrip(".")
        if normalized_host == domain:
            return "app"
        prefix = normalized_host[: -(len(domain) + 1)]
        labels = [label for label in prefix.split(".") if label]
        if not labels:
            return "app"
        if len(labels) == 1:
            label = labels[0]
            if label in DEFAULT_TENANT_SUBDOMAINS:
                return "app"
            return label
        if len(labels) == 2 and labels[1] in TENANT_SURFACE_LABELS:
            return labels[0]
        return None

    async def _query_tenant(self, subdomain: str) -> Tenant | None:
        async with self.session_factory() as session:
            result = await session.execute(select(Tenant).where(Tenant.subdomain == subdomain))
            return result.scalar_one_or_none()

    async def _get_redis_cached(self, host: str) -> TenantContext | None | object:
        if self.redis_client is None:
            return _MISSING
        try:
            raw = await self.redis_client.get(self._cache_key(host))
        except Exception:
            return _MISSING
        if raw is None:
            return _MISSING
        data = json.loads(raw.decode("utf-8"))
        if data.get("miss") is True:
            return None
        return self._context_from_payload(data["tenant"])

    async def _set_redis_cached(
        self,
        host: str,
        tenant: TenantContext,
        *,
        ttl_seconds: int,
    ) -> None:
        if self.redis_client is None:
            return
        payload = {"tenant": self._context_to_payload(tenant)}
        try:
            await self.redis_client.set(
                self._cache_key(host),
                json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                ttl=ttl_seconds,
            )
        except Exception:
            return

    async def _cache_miss(self, host: str) -> None:
        miss_ttl = max(1, self.ttl_seconds // 2)
        self._local_cache.set(host, None, ttl_seconds=miss_ttl)
        if self.redis_client is None:
            return
        try:
            await self.redis_client.set(
                self._cache_key(host),
                b'{"miss":true}',
                ttl=miss_ttl,
            )
        except Exception:
            return

    def _to_context(self, tenant: Tenant) -> TenantContext:
        return TenantContext(
            id=tenant.id,
            slug=tenant.slug,
            subdomain=tenant.subdomain,
            kind=tenant.kind,  # type: ignore[arg-type]
            status=tenant.status,  # type: ignore[arg-type]
            region=tenant.region,
            branding=dict(tenant.branding_config_json or {}),
            feature_flags=dict(tenant.feature_flags_json or {}),
        )

    def _context_to_payload(self, tenant: TenantContext) -> dict[str, Any]:
        return {
            "id": str(tenant.id),
            "slug": tenant.slug,
            "subdomain": tenant.subdomain,
            "kind": tenant.kind,
            "status": tenant.status,
            "region": tenant.region,
            "branding": dict(tenant.branding),
            "feature_flags": dict(tenant.feature_flags),
        }

    def _context_from_payload(self, payload: dict[str, Any]) -> TenantContext:
        return TenantContext(
            id=UUID(str(payload["id"])),
            slug=payload["slug"],
            subdomain=payload["subdomain"],
            kind=payload["kind"],
            status=payload["status"],
            region=payload["region"],
            branding=dict(payload.get("branding") or {}),
            feature_flags=dict(payload.get("feature_flags") or {}),
        )

    def _cache_key(self, host: str) -> str:
        return f"tenants:resolve:{host}"


def _decode_invalidation_payload(raw_message: bytes | str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_message, dict):
        return raw_message
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8")
    try:
        payload = json.loads(raw_message)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


class _ResolverMetrics:
    def __init__(self) -> None:
        try:
            metrics_module = import_module("opentelemetry.metrics")
            meter = metrics_module.get_meter(__name__)
            self._lookups = meter.create_counter("tenant_resolver_lookups_total")
            self._latency = meter.create_histogram("tenant_resolver_latency_seconds")
            self._cache_hits = meter.create_counter("tenant_resolver_cache_hits_total")
        except Exception:
            self._lookups = None
            self._latency = None
            self._cache_hits = None

    def lookup(self, result: str) -> None:
        if self._lookups is not None:
            self._lookups.add(1, {"result": result})

    def latency(self, duration_seconds: float) -> None:
        if self._latency is not None:
            self._latency.record(duration_seconds)

    def cache_hit(self, tier: str) -> None:
        if self._cache_hits is not None:
            self._cache_hits.add(1, {"tier": tier})
