from __future__ import annotations

from platform.common import database
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.logging import get_logger
from platform.incident_response.trigger_interface import get_incident_trigger
from platform.multi_region_ops.repository import MultiRegionOpsRepository
from platform.multi_region_ops.services.probes.base import ReplicationProbeRegistry
from platform.multi_region_ops.services.probes.clickhouse import ClickHouseReplicationProbe
from platform.multi_region_ops.services.probes.kafka import KafkaReplicationProbe
from platform.multi_region_ops.services.probes.neo4j import Neo4jReplicationProbe
from platform.multi_region_ops.services.probes.opensearch import OpenSearchReplicationProbe
from platform.multi_region_ops.services.probes.postgres import PostgresReplicationProbe
from platform.multi_region_ops.services.probes.qdrant import QdrantReplicationProbe
from platform.multi_region_ops.services.probes.s3 import S3ReplicationProbe
from platform.multi_region_ops.services.replication_monitor import ReplicationMonitor
from platform.security_compliance.providers.rotatable_secret_provider import RotatableSecretProvider
from typing import Any

LOGGER = get_logger(__name__)


def build_replication_probe_scheduler(app: Any) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio", fromlist=["AsyncIOScheduler"]
        )
    except Exception:
        return None
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        settings = app.state.settings
        if not settings.feature_multi_region:
            return
        secret_provider = RotatableSecretProvider(
            settings=settings,
            redis_client=app.state.clients.get("redis"),
        )
        registry = ReplicationProbeRegistry()
        registry.register(PostgresReplicationProbe(secret_provider))
        registry.register(
            KafkaReplicationProbe(
                secret_provider,
                timeout_seconds=settings.multi_region_ops.replication_probe_request_timeout_seconds,
            )
        )
        registry.register(S3ReplicationProbe(secret_provider))
        clickhouse = app.state.clients.get("clickhouse")
        registry.register(
            ClickHouseReplicationProbe(
                clickhouse if isinstance(clickhouse, AsyncClickHouseClient) else None
            )
        )
        registry.register(
            QdrantReplicationProbe(
                secret_provider,
                timeout_seconds=settings.multi_region_ops.replication_probe_request_timeout_seconds,
            )
        )
        registry.register(Neo4jReplicationProbe(secret_provider))
        registry.register(
            OpenSearchReplicationProbe(
                secret_provider,
                timeout_seconds=settings.multi_region_ops.replication_probe_request_timeout_seconds,
            )
        )
        async with database.AsyncSessionLocal() as session:
            monitor = ReplicationMonitor(
                repository=MultiRegionOpsRepository(session),
                settings=settings,
                probe_registry=registry,
                incident_trigger=get_incident_trigger(),
                producer=app.state.clients.get("kafka"),
            )
            await monitor.probe_all()
            await session.commit()

    scheduler.add_job(
        _run,
        "interval",
        seconds=app.state.settings.multi_region_ops.replication_probe_interval_seconds,
        id="multi-region-replication-probe",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
