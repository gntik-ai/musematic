from __future__ import annotations

from platform.common.clients.model_router import SecretProvider
from platform.multi_region_ops.models import RegionConfig
from platform.multi_region_ops.services.probes.base import ReplicationMeasurement
from typing import Any


class Neo4jReplicationProbe:
    component = "neo4j"

    def __init__(self, secret_provider: SecretProvider) -> None:
        self.secret_provider = secret_provider

    async def measure(
        self, *, source: RegionConfig, target: RegionConfig
    ) -> ReplicationMeasurement:
        del source
        uri_ref = target.endpoint_urls.get("neo4j_uri_ref")
        user_ref = target.endpoint_urls.get("neo4j_user_ref")
        password_ref = target.endpoint_urls.get("neo4j_password_ref")
        uri = await _secret_or_value(
            self.secret_provider, uri_ref, target.endpoint_urls.get("neo4j_uri")
        )
        user = await _secret_or_value(
            self.secret_provider, user_ref, target.endpoint_urls.get("neo4j_user")
        )
        password = await _secret_or_value(
            self.secret_provider, password_ref, target.endpoint_urls.get("neo4j_password")
        )
        if not uri:
            return ReplicationMeasurement(
                component=self.component,
                lag_seconds=None,
                health="unhealthy",
                error_detail="neo4j_uri missing",
            )
        neo4j = __import__("neo4j")
        driver = neo4j.AsyncGraphDatabase.driver(uri, auth=(user, password))
        try:
            async with driver.session() as session:
                result = await session.run("CALL dbms.cluster.overview()")
                rows = [record async for record in result]
        finally:
            await driver.close()
        lag = _extract_tx_lag(rows)
        return ReplicationMeasurement(
            component=self.component,
            lag_seconds=lag,
            health="healthy" if lag == 0 else "degraded" if lag < 300 else "unhealthy",
        )


async def _secret_or_value(secret_provider: SecretProvider, ref: Any, value: Any) -> str | None:
    if isinstance(ref, str) and ref:
        return await secret_provider.get_current(ref)
    return str(value) if value is not None else None


def _extract_tx_lag(rows: list[Any]) -> int:
    tx_values: list[int] = []
    for row in rows:
        data = dict(row)
        tx = data.get("last_committed_tx") or data.get("lastCommittedTx")
        if isinstance(tx, (int, float)):
            tx_values.append(int(tx))
    if len(tx_values) < 2:
        return 0
    return max(tx_values) - min(tx_values)
