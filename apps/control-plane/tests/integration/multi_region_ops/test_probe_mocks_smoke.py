from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import pytest

ROOT_TESTS = Path(__file__).resolve().parents[5] / "tests"
if str(ROOT_TESTS) not in sys.path:
    sys.path.insert(0, str(ROOT_TESTS))

probe_mocks = import_module("fixtures.multi_region_ops.probe_mocks")
AsyncpgReplicationMock = probe_mocks.AsyncpgReplicationMock
probe_mock_client = probe_mocks.probe_mock_client

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_probe_mocks_return_documented_lag_shapes() -> None:
    async with probe_mock_client() as client:
        for component in ("kafka", "s3", "clickhouse", "qdrant", "neo4j", "opensearch"):
            response = await client.post(f"/inject-lag/{component}", json={"lag_seconds": 7})
            assert response.status_code == 200

        assert (await client.get("/kafka/consumer-groups/mirror")).json()[0]["lag_seconds"] == 7
        assert (
            await client.get("/s3/buckets/platform-replica/replication")
        ).json()["Metrics"]["ReplicationLatency"] == 7
        assert (
            await client.get("/clickhouse/system/replication_queue")
        ).json()[0]["lag_seconds"] == 7
        qdrant = (await client.get("/qdrant/cluster")).json()
        assert qdrant["peers"]["replica-a"]["lag_seconds"] == 7
        assert len((await client.get("/neo4j/cluster")).json()) == 2
        assert (await client.get("/opensearch/_cluster/stats")).json()["shards"]["successful"] == 3


async def test_asyncpg_probe_mock_accepts_arbitrary_credentials() -> None:
    state = AsyncpgReplicationMock(lag_seconds=9)
    connection = await state.connect("postgresql://any-user:any-password@example/db")
    rows = await connection.fetch("select replay_lag from pg_stat_replication")

    assert rows[0]["replay_lag"].total_seconds() == 9
