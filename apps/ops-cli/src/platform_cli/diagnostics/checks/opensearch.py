"""OpenSearch diagnostic check."""

from __future__ import annotations

from time import perf_counter

import httpx

from platform_cli.constants import ComponentCategory
from platform_cli.models import CheckStatus, DiagnosticCheck


class OpenSearchCheck:
    """Verify OpenSearch cluster health."""

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self.name = "opensearch"

    async def run(self) -> DiagnosticCheck:
        started = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.url}/_cluster/health")
            response.raise_for_status()
        except Exception as exc:
            return DiagnosticCheck(
                component="opensearch",
                display_name="OpenSearch",
                category=ComponentCategory.DATA_STORE,
                status=CheckStatus.UNHEALTHY,
                error=str(exc),
                remediation="Check OpenSearch cluster health and auth.",
            )
        payload = response.json()
        cluster_status = str(payload.get("status", "unknown"))
        status = {
            "green": CheckStatus.HEALTHY,
            "yellow": CheckStatus.DEGRADED,
            "red": CheckStatus.UNHEALTHY,
        }.get(cluster_status, CheckStatus.UNKNOWN)
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return DiagnosticCheck(
            component="opensearch",
            display_name="OpenSearch",
            category=ComponentCategory.DATA_STORE,
            status=status,
            latency_ms=latency_ms,
            remediation=None
            if status == CheckStatus.HEALTHY
            else "Review shard allocation and cluster status.",
        )
