from __future__ import annotations

from platform.common.clients.model_router import SecretProvider
from platform.multi_region_ops.models import RegionConfig
from platform.multi_region_ops.services.probes.base import ReplicationMeasurement
from typing import Any

import httpx


class OpenSearchReplicationProbe:
    component = "opensearch"

    def __init__(self, secret_provider: SecretProvider, *, timeout_seconds: float = 5.0) -> None:
        self.secret_provider = secret_provider
        self.timeout_seconds = timeout_seconds

    async def measure(
        self, *, source: RegionConfig, target: RegionConfig
    ) -> ReplicationMeasurement:
        del source
        url = target.endpoint_urls.get("opensearch_url")
        api_key_ref = target.endpoint_urls.get("opensearch_api_key_ref")
        if not isinstance(url, str) or not url:
            return ReplicationMeasurement(
                component=self.component,
                lag_seconds=None,
                health="unhealthy",
                error_detail="opensearch_url missing",
            )
        headers = {}
        if isinstance(api_key_ref, str) and api_key_ref:
            headers["Authorization"] = (
                f"ApiKey {await self.secret_provider.get_current(api_key_ref)}"
            )
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url.rstrip("/") + "/_cluster/stats", headers=headers)
            response.raise_for_status()
            payload = response.json()
        lag = _extract_shard_lag(payload)
        return ReplicationMeasurement(
            component=self.component,
            lag_seconds=lag,
            health="healthy" if lag == 0 else "degraded" if lag < 100 else "unhealthy",
        )


def _extract_shard_lag(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    shards = payload.get("shards")
    if not isinstance(shards, dict):
        return 0
    total = shards.get("total")
    successful = shards.get("successful")
    if isinstance(total, (int, float)) and isinstance(successful, (int, float)):
        return max(0, int(total) - int(successful))
    return 0
