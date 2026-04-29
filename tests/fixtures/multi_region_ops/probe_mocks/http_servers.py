from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import FastAPI


@dataclass
class ProbeMockState:
    lag_seconds: dict[str, int] = field(
        default_factory=lambda: {
            "kafka": 0,
            "s3": 0,
            "clickhouse": 0,
            "qdrant": 0,
            "neo4j": 0,
            "opensearch": 0,
        }
    )
    unhealthy: set[str] = field(default_factory=set)

    def set_lag(self, component: str, lag_seconds: int) -> None:
        self.lag_seconds[component] = lag_seconds
        self.unhealthy.discard(component)

    def mark_unhealthy(self, component: str) -> None:
        self.unhealthy.add(component)


def create_probe_mock_app(state: ProbeMockState | None = None) -> FastAPI:
    app = FastAPI()
    resolved = state or ProbeMockState()

    @app.post("/inject-lag/{component}")
    async def inject_lag(component: str, payload: dict[str, Any]) -> dict[str, Any]:
        resolved.set_lag(component, int(payload.get("lag_seconds", 0)))
        return {"component": component, "lag_seconds": resolved.lag_seconds[component]}

    @app.post("/mark-unhealthy/{component}")
    async def mark_unhealthy(component: str) -> dict[str, Any]:
        resolved.mark_unhealthy(component)
        return {"component": component, "health": "unhealthy"}

    @app.get("/kafka/consumer-groups/{group}")
    async def kafka_group(group: str) -> list[dict[str, Any]]:
        return [{"group": group, "lag_seconds": resolved.lag_seconds["kafka"]}]

    @app.get("/s3/buckets/{bucket}/replication")
    async def s3_replication(bucket: str) -> dict[str, Any]:
        return {
            "bucket": bucket,
            "ReplicationConfiguration": {"Status": "Enabled"},
            "Metrics": {"ReplicationLatency": resolved.lag_seconds["s3"]},
        }

    @app.get("/clickhouse/system/replication_queue")
    async def clickhouse_queue() -> list[dict[str, Any]]:
        return [{"lag_seconds": resolved.lag_seconds["clickhouse"], "queue_size": 1}]

    @app.get("/qdrant/cluster")
    async def qdrant_cluster() -> dict[str, Any]:
        return {"peers": {"replica-a": {"lag_seconds": resolved.lag_seconds["qdrant"]}}}

    @app.get("/neo4j/cluster")
    async def neo4j_cluster() -> list[dict[str, Any]]:
        latest = 100
        return [
            {"server": "primary", "last_committed_tx": latest},
            {"server": "secondary", "lastCommittedTx": latest - resolved.lag_seconds["neo4j"]},
        ]

    @app.get("/opensearch/_cluster/stats")
    async def opensearch_stats() -> dict[str, Any]:
        failed = resolved.lag_seconds["opensearch"]
        return {"shards": {"total": 10, "successful": max(0, 10 - failed)}}

    return app


def probe_mock_client(state: ProbeMockState | None = None) -> httpx.AsyncClient:
    app = create_probe_mock_app(state)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://probe-mock",
    )
