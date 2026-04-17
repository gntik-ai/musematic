"""Neo4j diagnostic check."""

from __future__ import annotations

from time import perf_counter

from platform_cli.constants import ComponentCategory
from platform_cli.models import CheckStatus, DiagnosticCheck


class Neo4jCheck:
    """Verify Neo4j connectivity using a trivial Cypher query."""

    def __init__(self, uri: str, password: str) -> None:
        self.uri = uri
        self.password = password
        self.name = "neo4j"

    async def run(self) -> DiagnosticCheck:
        from neo4j import AsyncGraphDatabase

        started = perf_counter()
        driver = AsyncGraphDatabase.driver(self.uri, auth=("neo4j", self.password))
        try:
            async with driver.session() as session:
                await session.run("RETURN 1")
        except Exception as exc:
            return DiagnosticCheck(
                component="neo4j",
                display_name="Neo4j",
                category=ComponentCategory.DATA_STORE,
                status=CheckStatus.UNHEALTHY,
                error=str(exc),
                remediation="Check Neo4j connectivity and credentials.",
            )
        finally:
            await driver.close()
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return DiagnosticCheck(
            component="neo4j",
            display_name="Neo4j",
            category=ComponentCategory.DATA_STORE,
            status=CheckStatus.HEALTHY,
            latency_ms=latency_ms,
        )
