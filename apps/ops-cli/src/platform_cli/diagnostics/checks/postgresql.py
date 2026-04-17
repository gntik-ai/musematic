"""PostgreSQL diagnostic check."""

from __future__ import annotations

from time import perf_counter

from platform_cli.constants import ComponentCategory
from platform_cli.models import CheckStatus, DiagnosticCheck


class PostgreSQLCheck:
    """Verify PostgreSQL connectivity with a trivial query."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.name = "postgresql"

    async def run(self) -> DiagnosticCheck:
        import asyncpg

        started = perf_counter()
        try:
            connection = await asyncpg.connect(self.dsn)
            try:
                await connection.execute("SELECT 1")
            finally:
                await connection.close()
        except Exception as exc:
            return DiagnosticCheck(
                component="postgresql",
                display_name="PostgreSQL",
                category=ComponentCategory.DATA_STORE,
                status=CheckStatus.UNHEALTHY,
                error=str(exc),
                remediation="Check PostgreSQL connectivity and credentials.",
            )
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return DiagnosticCheck(
            component="postgresql",
            display_name="PostgreSQL",
            category=ComponentCategory.DATA_STORE,
            status=CheckStatus.HEALTHY,
            latency_ms=latency_ms,
        )
