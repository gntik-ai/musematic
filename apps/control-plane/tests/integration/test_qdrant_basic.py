from __future__ import annotations

import random

import pytest

from platform.common.clients.qdrant import PointStruct, workspace_filter
from platform.common.exceptions import QdrantError


pytestmark = pytest.mark.asyncio


def _vector(size: int = 768) -> list[float]:
    return [random.random() for _ in range(size)]


async def test_upsert_search_delete_workspace_isolation(qdrant_client, qdrant_test_collection) -> None:
    points = []
    for index in range(100):
        points.append(
            PointStruct(
                id=f"p-{index}",
                vector=_vector(),
                payload={
                    "workspace_id": "ws-A" if index < 34 else "ws-B" if index < 67 else "ws-C",
                    "lifecycle_state": "published",
                    "maturity_level": index % 5,
                },
            )
        )
    needle = PointStruct(
        id="needle",
        vector=_vector(),
        payload={"workspace_id": "ws-A", "lifecycle_state": "published", "maturity_level": 3},
    )
    points.append(needle)

    await qdrant_client.upsert_vectors(qdrant_test_collection, points)

    results = await qdrant_client.search_vectors(
        qdrant_test_collection,
        query_vector=needle.vector,
        filter=workspace_filter("ws-A"),
        limit=10,
    )
    assert results
    assert all(result.payload["workspace_id"] == "ws-A" for result in results)
    assert results == sorted(results, key=lambda item: item.score, reverse=True)
    assert results[0].score > 0.9999

    await qdrant_client.delete_vectors(qdrant_test_collection, ["needle"])
    after_delete = await qdrant_client.search_vectors(
        qdrant_test_collection,
        query_vector=needle.vector,
        filter=workspace_filter("ws-A"),
        limit=10,
    )
    assert all(result.id != "needle" for result in after_delete)


async def test_upsert_with_wrong_dimension_raises(qdrant_client, qdrant_test_collection) -> None:
    with pytest.raises(QdrantError):
        await qdrant_client.upsert_vectors(
            qdrant_test_collection,
            [PointStruct(id="bad", vector=[0.1, 0.2], payload={"workspace_id": "ws-A"})],
        )
