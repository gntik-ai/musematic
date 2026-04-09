from __future__ import annotations

import random
from importlib import import_module

import pytest

from platform.common.clients.qdrant import PointStruct, workspace_filter


pytestmark = pytest.mark.asyncio


def _vector(size: int = 768) -> list[float]:
    return [random.random() for _ in range(size)]


async def test_compound_filters_and_threshold(qdrant_client, qdrant_test_collection) -> None:
    models = import_module("qdrant_client.models")
    points = []
    for index in range(100):
        points.append(
            PointStruct(
                id=f"p-{index}",
                vector=_vector(),
                payload={
                    "workspace_id": f"ws-{index % 10}",
                    "lifecycle_state": "published" if index % 2 == 0 else "draft",
                    "maturity_level": index % 5,
                },
            )
        )
    needle = PointStruct(
        id="published-needle",
        vector=_vector(),
        payload={"workspace_id": "ws-1", "lifecycle_state": "published", "maturity_level": 3},
    )
    points.append(needle)
    await qdrant_client.upsert_vectors(qdrant_test_collection, points)

    compound = workspace_filter(
        "ws-1",
        extra=models.Filter(
            must=[models.FieldCondition(key="lifecycle_state", match=models.MatchValue(value="published"))]
        ),
    )
    results = await qdrant_client.search_vectors(
        qdrant_test_collection,
        query_vector=needle.vector,
        filter=compound,
        limit=10,
        score_threshold=0.5,
    )

    assert results
    assert all(result.payload["workspace_id"] == "ws-1" for result in results)
    assert all(result.payload["lifecycle_state"] == "published" for result in results)
    assert all(result.score >= 0.5 for result in results)


async def test_small_collection_top1_recall_is_exact(qdrant_client, qdrant_test_collection) -> None:
    vectors = [
        PointStruct(
            id=f"known-{index}",
            vector=[float(index)] * 768,
            payload={"workspace_id": "ws-known"},
        )
        for index in range(100)
    ]
    await qdrant_client.upsert_vectors(qdrant_test_collection, vectors)

    for point in vectors[:10]:
        results = await qdrant_client.search_vectors(
            qdrant_test_collection,
            query_vector=point.vector,
            filter=workspace_filter("ws-known"),
            limit=1,
        )
        assert results[0].id == point.id
