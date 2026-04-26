from __future__ import annotations

from importlib import import_module
from platform.common.clients.model_router import SecretProvider
from platform.multi_region_ops.models import RegionConfig
from platform.multi_region_ops.services.probes.base import ReplicationMeasurement
from typing import Any


class KafkaReplicationProbe:
    component = "kafka"

    def __init__(self, secret_provider: SecretProvider, *, timeout_seconds: float = 5.0) -> None:
        self.secret_provider = secret_provider
        self.timeout_seconds = timeout_seconds

    async def measure(
        self, *, source: RegionConfig, target: RegionConfig
    ) -> ReplicationMeasurement:
        del source
        group_id = target.endpoint_urls.get("mirrormaker_consumer_group")
        brokers_ref = target.endpoint_urls.get("kafka_admin_brokers_ref")
        if not isinstance(group_id, str) or not group_id:
            return ReplicationMeasurement(
                component=self.component,
                lag_seconds=None,
                health="unhealthy",
                error_detail="mirrormaker_consumer_group missing",
            )
        bootstrap_servers = (
            await self.secret_provider.get_current(brokers_ref)
            if isinstance(brokers_ref, str) and brokers_ref
            else target.endpoint_urls.get("kafka_admin_brokers")
        )
        if not isinstance(bootstrap_servers, str) or not bootstrap_servers:
            return ReplicationMeasurement(
                component=self.component,
                lag_seconds=None,
                health="unhealthy",
                error_detail="kafka admin bootstrap servers missing",
            )
        admin_cls = import_module("aiokafka.admin").AIOKafkaAdminClient
        admin = admin_cls(
            bootstrap_servers=bootstrap_servers, request_timeout_ms=int(self.timeout_seconds * 1000)
        )
        try:
            await admin.start()
            description = await admin.describe_consumer_groups([group_id])
        finally:
            stop = getattr(admin, "stop", None)
            if callable(stop):
                await stop()
        lag = _extract_lag(description)
        return ReplicationMeasurement(
            component=self.component,
            lag_seconds=lag,
            health="healthy" if lag == 0 else "degraded" if lag < 300 else "unhealthy",
        )


def _extract_lag(description: Any) -> int:
    if isinstance(description, dict):
        raw_lag = description.get("lag_seconds") or description.get("lag")
        if isinstance(raw_lag, (int, float)):
            return int(raw_lag)
    if isinstance(description, list):
        total = 0
        found = False
        for item in description:
            if isinstance(item, dict):
                raw_lag = item.get("lag_seconds") or item.get("lag")
                if isinstance(raw_lag, (int, float)):
                    total += int(raw_lag)
                    found = True
        if found:
            return total
    return 0
