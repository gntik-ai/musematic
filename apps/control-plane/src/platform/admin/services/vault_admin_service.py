from __future__ import annotations

import contextlib
import os
import time
import uuid
from dataclasses import dataclass, field
from platform.admin.schemas.vault import (
    CacheFlushRequest,
    CacheFlushResponse,
    ConnectivityTestResponse,
    TokenRotationRequest,
    TokenRotationResponse,
    VaultStatusResponse,
)
from platform.common.config import PlatformSettings
from platform.common.secret_provider import (
    REGISTRY,
    HealthStatus,
    SecretProvider,
    validate_secret_path,
)
from typing import Any, cast


@dataclass(slots=True)
class _VaultMetricSnapshot:
    read_counts_by_domain: dict[str, float] = field(default_factory=dict)
    auth_failure_counts_by_method: dict[str, float] = field(default_factory=dict)
    policy_denied_counts_by_path: dict[str, float] = field(default_factory=dict)
    serving_stale_total: float = 0.0
    renewal_success_total: float = 0.0
    renewal_failure_total: float = 0.0
    cache_hit_total: float = 0.0
    cache_miss_total: float = 0.0


class VaultAdminService:
    def __init__(self, secret_provider: SecretProvider, settings: PlatformSettings) -> None:
        self._secret_provider = secret_provider
        self._settings = settings

    async def status(self) -> VaultStatusResponse:
        health = await self._secret_provider.health_check()
        metrics = self._collect_metrics()
        return VaultStatusResponse(
            status=health.status,
            mode=str(getattr(self._settings.vault, "mode", "unknown")),
            auth_method=health.auth_method,
            token_expiry_at=health.token_expiry_at,
            lease_count=health.lease_count,
            recent_failures=health.recent_failures,
            cache_hit_rate=health.cache_hit_rate,
            error=health.error,
            read_counts_by_domain=metrics.read_counts_by_domain,
            auth_failure_counts_by_method=metrics.auth_failure_counts_by_method,
            policy_denied_counts_by_path=metrics.policy_denied_counts_by_path,
            serving_stale_total=metrics.serving_stale_total,
            renewal_success_total=metrics.renewal_success_total,
            renewal_failure_total=metrics.renewal_failure_total,
            cache_hit_total=metrics.cache_hit_total,
            cache_miss_total=metrics.cache_miss_total,
        )

    async def flush_cache(self, request: CacheFlushRequest) -> CacheFlushResponse:
        if request.path is not None:
            validate_secret_path(request.path)
        flushed_count = await self._secret_provider.flush_cache(request.path)
        return CacheFlushResponse(
            flushed_count=flushed_count,
            path=request.path,
            pod=request.pod,
            all_pods_requested=request.all_pods,
        )

    async def connectivity_test(self) -> ConnectivityTestResponse:
        path = (
            f"secret/data/musematic/{self._environment()}/"
            f"_internal/connectivity-test/{uuid.uuid4().hex}"
        )
        probe_value = uuid.uuid4().hex
        start = time.perf_counter()
        try:
            await self._secret_provider.put(path, {"value": probe_value})
            observed = await self._secret_provider.get(path, "value", critical=True)
            success = observed == probe_value
            error = None if success else "Connectivity probe read mismatch"
            await self._best_effort_delete_latest(path)
        except Exception as exc:
            success = False
            error = f"{type(exc).__name__}: {exc}"
        latency_ms = (time.perf_counter() - start) * 1000
        return ConnectivityTestResponse(
            success=success,
            latency_ms=round(latency_ms, 3),
            error=error,
        )

    async def rotate_token(self, request: TokenRotationRequest) -> TokenRotationResponse:
        renewal_task = getattr(self._secret_provider, "_renewal_task", None)
        if renewal_task is not None:
            with contextlib.suppress(Exception):
                renewal_task.cancel()
        if hasattr(self._secret_provider, "_authenticated"):
            provider_state = cast(Any, self._secret_provider)
            provider_state._authenticated = False
        health = await self._secret_provider.health_check()
        return TokenRotationResponse(
            success=health.status != "red",
            status=health.status,
            error=health.error,
            pod=request.pod,
        )

    async def _best_effort_delete_latest(self, path: str) -> None:
        with contextlib.suppress(Exception):
            versions = await self._secret_provider.list_versions(path)
            if versions:
                await self._secret_provider.delete_version(path, max(versions))

    def _environment(self) -> str:
        raw = (
            os.getenv("PLATFORM_ENVIRONMENT")
            or os.getenv("PLATFORM_ENV")
            or os.getenv("ENVIRONMENT")
            or os.getenv("ENV")
            or "dev"
        ).strip().lower()
        return raw if raw in {"production", "staging", "dev", "test", "ci"} else "dev"

    def _collect_metrics(self) -> _VaultMetricSnapshot:
        snapshot = _VaultMetricSnapshot()
        registry = REGISTRY
        if registry is None:
            return snapshot
        for metric in registry.collect():
            for sample in getattr(metric, "samples", []):
                self._apply_sample(snapshot, sample)
        return snapshot

    def _apply_sample(self, snapshot: _VaultMetricSnapshot, sample: Any) -> None:
        name = str(getattr(sample, "name", ""))
        labels = dict(getattr(sample, "labels", {}) or {})
        value = float(getattr(sample, "value", 0.0) or 0.0)
        if name == "vault_read_total":
            domain = str(labels.get("domain") or "unknown")
            snapshot.read_counts_by_domain[domain] = (
                snapshot.read_counts_by_domain.get(domain, 0.0) + value
            )
        elif name == "vault_auth_failure_total":
            method = str(labels.get("auth_method") or "unknown")
            snapshot.auth_failure_counts_by_method[method] = (
                snapshot.auth_failure_counts_by_method.get(method, 0.0) + value
            )
        elif name == "vault_policy_denied_total":
            path = str(labels.get("path") or "unknown")
            snapshot.policy_denied_counts_by_path[path] = (
                snapshot.policy_denied_counts_by_path.get(path, 0.0) + value
            )
        elif name == "vault_serving_stale_total":
            snapshot.serving_stale_total += value
        elif name == "vault_renewal_success_total":
            snapshot.renewal_success_total += value
        elif name == "vault_renewal_failure_total":
            snapshot.renewal_failure_total += value
        elif name == "vault_cache_hit_total":
            snapshot.cache_hit_total += value
        elif name == "vault_cache_miss_total":
            snapshot.cache_miss_total += value


def health_status_to_dict(health: HealthStatus) -> dict[str, Any]:
    return {
        "status": health.status,
        "auth_method": health.auth_method,
        "token_expiry_at": health.token_expiry_at,
        "lease_count": health.lease_count,
        "recent_failures": health.recent_failures,
        "cache_hit_rate": health.cache_hit_rate,
        "error": health.error,
    }
