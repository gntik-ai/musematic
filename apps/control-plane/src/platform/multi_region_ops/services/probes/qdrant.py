from __future__ import annotations

from platform.common.clients.model_router import SecretProvider
from platform.multi_region_ops.models import RegionConfig
from platform.multi_region_ops.services.probes.base import ReplicationMeasurement
from typing import Any

import httpx


class QdrantReplicationProbe:
    component = "qdrant"

    def __init__(self, secret_provider: SecretProvider, *, timeout_seconds: float = 5.0) -> None:
        self.secret_provider = secret_provider
        self.timeout_seconds = timeout_seconds

    async def measure(
        self, *, source: RegionConfig, target: RegionConfig
    ) -> ReplicationMeasurement:
        del source
        cluster_url = target.endpoint_urls.get("qdrant_cluster_url")
        api_key_ref = target.endpoint_urls.get("qdrant_api_key_ref")
        if not isinstance(cluster_url, str) or not cluster_url:
            return ReplicationMeasurement(
                component=self.component,
                lag_seconds=None,
                health="unhealthy",
                error_detail="qdrant_cluster_url missing",
            )
        headers = {}
        if isinstance(api_key_ref, str) and api_key_ref:
            headers["api-key"] = await self.secret_provider.get_current(api_key_ref)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(cluster_url.rstrip("/") + "/cluster", headers=headers)
            response.raise_for_status()
            payload = response.json()
        lag = _extract_lag(payload)
        return ReplicationMeasurement(
            component=self.component,
            lag_seconds=lag,
            health="healthy" if lag == 0 else "degraded" if lag < 300 else "unhealthy",
        )


def _extract_lag(payload: Any) -> int:
    if isinstance(payload, dict):
        for key in ("lag_seconds", "replication_lag_seconds", "follower_lag"):
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return int(value)
        peers = payload.get("peers")
        if isinstance(peers, dict):
            lags = [
                int(peer.get("lag_seconds", 0)) for peer in peers.values() if isinstance(peer, dict)
            ]
            return max(lags, default=0)
    return 0
