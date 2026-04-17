"""Kafka diagnostic check."""

from __future__ import annotations

from time import perf_counter

from platform_cli.constants import ComponentCategory
from platform_cli.models import CheckStatus, DiagnosticCheck


class KafkaCheck:
    """Verify Kafka broker availability."""

    def __init__(self, bootstrap_servers: str) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.name = "kafka"

    async def run(self) -> DiagnosticCheck:
        from aiokafka.admin import AIOKafkaAdminClient

        started = perf_counter()
        client = AIOKafkaAdminClient(bootstrap_servers=self.bootstrap_servers)
        try:
            await client.start()
            await client.list_topics()
        except Exception as exc:
            return DiagnosticCheck(
                component="kafka",
                display_name="Kafka",
                category=ComponentCategory.DATA_STORE,
                status=CheckStatus.UNHEALTHY,
                error=str(exc),
                remediation="Check Kafka brokers and listener configuration.",
            )
        finally:
            await client.close()
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return DiagnosticCheck(
            component="kafka",
            display_name="Kafka",
            category=ComponentCategory.DATA_STORE,
            status=CheckStatus.HEALTHY,
            latency_ms=latency_ms,
        )
