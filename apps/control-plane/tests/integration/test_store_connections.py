from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from platform.common.clients.reasoning_engine import ReasoningEngineClient
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.clients.sandbox_manager import SandboxManagerClient
from platform.common.clients.simulation_controller import SimulationControllerClient
from platform.common.config import PlatformSettings


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

USAGE_EVENT_COLUMNS = [
    "event_id",
    "workspace_id",
    "user_id",
    "agent_id",
    "workflow_id",
    "execution_id",
    "provider",
    "model",
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cached_tokens",
    "estimated_cost",
    "context_quality_score",
    "reasoning_depth",
    "event_time",
]


def _usage_event() -> dict[str, object]:
    return {
        "event_id": uuid4(),
        "workspace_id": uuid4(),
        "user_id": uuid4(),
        "agent_id": uuid4(),
        "workflow_id": None,
        "execution_id": None,
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "input_tokens": 100,
        "output_tokens": 50,
        "reasoning_tokens": 0,
        "cached_tokens": 0,
        "estimated_cost": 0.001,
        "context_quality_score": 0.95,
        "reasoning_depth": 1,
        "event_time": datetime.now(UTC),
    }


async def test_store_wrapper_health_checks(
    redis_client,
    qdrant_client,
    neo4j_client,
    clickhouse_client,
    opensearch_client,
    object_storage_client,
) -> None:
    assert await redis_client.health_check() is True
    assert await qdrant_client.health_check() is True
    assert await neo4j_client.health_check() is True
    assert await clickhouse_client.health_check() is True
    assert await opensearch_client.health_check() is True
    assert await object_storage_client.health_check() is True


async def test_store_wrapper_typed_operations(
    redis_client,
    qdrant_client,
    qdrant_test_collection,
    neo4j_client,
    clickhouse_client,
    opensearch_client,
    object_storage_client,
) -> None:
    await redis_client.set("smoke:key", b"value", ttl=30)
    assert await redis_client.get("smoke:key") == b"value"

    await qdrant_client.upsert_vectors(
        qdrant_test_collection,
        [{"id": "smoke-point", "vector": [0.1] * 768, "payload": {"workspace_id": "ws-smoke"}}],
    )
    qdrant_results = await qdrant_client.search_vectors(
        qdrant_test_collection,
        query_vector=[0.1] * 768,
        limit=1,
    )
    assert qdrant_results
    assert qdrant_results[0]["id"] == "smoke-point"

    assert await neo4j_client.run_cypher("RETURN 1 AS ok") == [{"ok": 1}]

    await clickhouse_client.insert("usage_events", [_usage_event()], USAGE_EVENT_COLUMNS)
    clickhouse_rows = await clickhouse_client.execute_query("SELECT count() AS cnt FROM usage_events")
    assert int(clickhouse_rows[0]["cnt"]) >= 1

    index_name = f"store-smoke-{uuid4().hex}"
    try:
        await opensearch_client.index(index_name, "doc-1", {"workspace_id": "ws-smoke", "name": "doc"})
        raw_client = await opensearch_client._ensure_client()
        await raw_client.indices.refresh(index=index_name)
        search_result = await opensearch_client.search(index_name, {"match_all": {}}, size=5)
        bulk_result = await opensearch_client.bulk(
            [
                {
                    "_op_type": "index",
                    "_index": index_name,
                    "_id": "doc-2",
                    "_source": {"workspace_id": "ws-smoke", "name": "doc-2"},
                }
            ]
        )
        assert search_result["hits"]["hits"] is not None
        assert bulk_result["success"] >= 1
    finally:
        raw_client = await opensearch_client._ensure_client()
        await raw_client.indices.delete(index=index_name, ignore=[404])

    bucket = f"store-smoke-{uuid4().hex}"
    await object_storage_client.create_bucket_if_not_exists(bucket)
    await object_storage_client.put_object(bucket, "artifact.bin", b"payload")
    assert await object_storage_client.get_object(bucket, "artifact.bin") == b"payload"
    assert "artifact.bin" in await object_storage_client.list_objects(bucket)


@pytest.mark.skipif(
    os.environ.get("CONTROL_PLANE_GRPC_INTEGRATION") != "1",
    reason="set CONTROL_PLANE_GRPC_INTEGRATION=1 to run live gRPC wrapper smoke tests",
)
@pytest.mark.parametrize(
    "wrapper_cls",
    [
        RuntimeControllerClient,
        ReasoningEngineClient,
        SandboxManagerClient,
        SimulationControllerClient,
    ],
)
async def test_grpc_wrapper_smoke(wrapper_cls) -> None:
    pytest.importorskip("grpc")

    client = wrapper_cls(settings=PlatformSettings())
    await client.connect()

    try:
        assert client.stub is not None
        assert await client.health_check() is True
    finally:
        await client.close()
