"""ClickHouse diagnostic check."""

from __future__ import annotations

import asyncio
from time import perf_counter

from platform_cli.constants import ComponentCategory
from platform_cli.models import CheckStatus, DiagnosticCheck


class ClickHouseCheck:
    """Verify ClickHouse connectivity with ``SELECT 1``."""

    def __init__(self, host: str) -> None:
        self.host = host
        self.name = "clickhouse"

    async def run(self) -> DiagnosticCheck:
        import clickhouse_connect

        started = perf_counter()

        def _query() -> None:
            client = clickhouse_connect.get_client(host=self.host)
            client.query("SELECT 1")
            client.close()

        try:
            await asyncio.to_thread(_query)
        except Exception as exc:
            return DiagnosticCheck(
                component="clickhouse",
                display_name="ClickHouse",
                category=ComponentCategory.DATA_STORE,
                status=CheckStatus.UNHEALTHY,
                error=str(exc),
                remediation="Check ClickHouse reachability and credentials.",
            )
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return DiagnosticCheck(
            component="clickhouse",
            display_name="ClickHouse",
            category=ComponentCategory.DATA_STORE,
            status=CheckStatus.HEALTHY,
            latency_ms=latency_ms,
        )
