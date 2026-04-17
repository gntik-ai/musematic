"""Qdrant diagnostic check."""

from __future__ import annotations

from time import perf_counter

import httpx

from platform_cli.constants import ComponentCategory
from platform_cli.models import CheckStatus, DiagnosticCheck


class QdrantCheck:
    """Verify the Qdrant health endpoint."""

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self.name = "qdrant"

    async def run(self) -> DiagnosticCheck:
        started = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.url}/healthz")
            response.raise_for_status()
        except Exception as exc:
            return DiagnosticCheck(
                component="qdrant",
                display_name="Qdrant",
                category=ComponentCategory.DATA_STORE,
                status=CheckStatus.UNHEALTHY,
                error=str(exc),
                remediation="Check Qdrant HTTP health endpoint.",
            )
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return DiagnosticCheck(
            component="qdrant",
            display_name="Qdrant",
            category=ComponentCategory.DATA_STORE,
            status=CheckStatus.HEALTHY,
            latency_ms=latency_ms,
        )
