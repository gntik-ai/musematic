from __future__ import annotations

import asyncio

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_network_partition_fails_fast_then_recovers(http_client) -> None:
    partition = await post_json(
        http_client,
        "/api/v1/_e2e/chaos/partition-network",
        {
            "from_namespace": "platform-execution",
            "to_namespace": "platform-data",
            "ttl_seconds": 30,
        },
    )
    try:
        failed = await http_client.post(
            "/api/v1/executions",
            json={
                "agent_fqn": "default:seeded-executor",
                "input": "needs data",
            },
        )
        assert failed.status_code == 503
        assert failed.elapsed.total_seconds() < 15
    finally:
        await http_client.delete(
            f"/api/v1/_e2e/chaos/partition-network/{partition['network_policy_name']}",
        )
    await asyncio.sleep(35)
    recovered = await http_client.get("/api/v1/healthz")
    assert recovered.status_code == 200
