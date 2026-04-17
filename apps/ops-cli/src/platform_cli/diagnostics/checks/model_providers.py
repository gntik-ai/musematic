"""External model provider health checks."""

from __future__ import annotations

from time import perf_counter

import httpx

from platform_cli.constants import ComponentCategory
from platform_cli.models import CheckStatus, DiagnosticCheck


class ModelProviderCheck:
    """Verify an external model provider endpoint."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.name = url

    async def run(self) -> DiagnosticCheck:
        started = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self.url)
            response.raise_for_status()
        except Exception as exc:
            return DiagnosticCheck(
                component=self.url,
                display_name=self.url,
                category=ComponentCategory.SATELLITE_SERVICE,
                status=CheckStatus.UNHEALTHY,
                error=str(exc),
                remediation="Check outbound connectivity to the model provider.",
            )
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return DiagnosticCheck(
            component=self.url,
            display_name=self.url,
            category=ComponentCategory.SATELLITE_SERVICE,
            status=CheckStatus.HEALTHY,
            latency_ms=latency_ms,
        )
