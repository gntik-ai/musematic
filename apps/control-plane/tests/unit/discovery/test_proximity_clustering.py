from __future__ import annotations

import sys
from platform.common.config import PlatformSettings
from platform.discovery.proximity.clustering import (
    ProximityClustering,
    _average_similarity,
    _cosine_distance,
    _fallback_labels_and_distances,
    proximity_clustering_task,
)
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_compute_returns_low_data_without_scipy_calls() -> None:
    clustering = ProximityClustering(
        settings=PlatformSettings(),
        repository=SimpleNamespace(
            replace_clusters=AsyncMock(), update_hypothesis_cluster=AsyncMock()
        ),
        embedder=SimpleNamespace(fetch_session_embeddings=AsyncMock(return_value=[])),
        publisher=SimpleNamespace(proximity_computed=AsyncMock()),
    )

    result = await clustering.compute(uuid4(), uuid4())

    assert result.status == "low_data"
    assert result.clusters == []


@pytest.mark.asyncio
async def test_compute_clusters_and_marks_over_explored() -> None:
    session_id = uuid4()
    workspace_id = uuid4()
    ids = [uuid4() for _ in range(5)]
    embeddings = [
        {
            "id": str(item),
            "vector": [1.0, 0.01 * index],
            "payload": {"hypothesis_id": str(item), "title": f"H{index}"},
        }
        for index, item in enumerate(ids)
    ]
    settings = PlatformSettings.model_validate(
        {
            "DISCOVERY_PROXIMITY_OVER_EXPLORED_MIN_SIZE": 5,
            "DISCOVERY_PROXIMITY_OVER_EXPLORED_SIMILARITY": 0.8,
        }
    )
    repo = SimpleNamespace(
        replace_clusters=AsyncMock(side_effect=lambda *_, **__: []),
        update_hypothesis_cluster=AsyncMock(),
    )
    publisher = SimpleNamespace(proximity_computed=AsyncMock())
    clustering = ProximityClustering(
        settings=settings,
        repository=repo,
        embedder=SimpleNamespace(fetch_session_embeddings=AsyncMock(return_value=embeddings)),
        publisher=publisher,
    )

    result = await clustering.compute(session_id, workspace_id)

    assert result.status == "saturated"
    assert result.clusters[0].classification == "over_explored"
    repo.replace_clusters.assert_awaited_once()
    publisher.proximity_computed.assert_awaited_once_with(
        session_id, workspace_id, len(result.clusters)
    )


def test_fallback_distance_helpers_cover_zero_and_clusters() -> None:
    labels, distances = _fallback_labels_and_distances([[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]], 0.2)

    assert labels[:2] == [1, 1]
    assert labels[2] == 2
    assert distances[0][0] == pytest.approx(0.0)
    assert _cosine_distance([0.0], [1.0]) == 1.0


@pytest.mark.asyncio
async def test_compute_uses_scipy_path_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = uuid4()
    workspace_id = uuid4()
    ids = [uuid4(), uuid4(), uuid4()]
    embeddings = [
        {
            "id": str(item),
            "vector": [1.0, float(index)],
            "payload": {"hypothesis_id": str(item), "title": str(index)},
        }
        for index, item in enumerate(ids)
    ]
    monkeypatch.setitem(
        sys.modules, "numpy", SimpleNamespace(array=lambda value, dtype=None: value)
    )
    monkeypatch.setitem(sys.modules, "scipy", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "scipy.cluster", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "scipy.cluster.hierarchy",
        SimpleNamespace(fclusterdata=lambda *_, **__: [1, 1, 2]),
    )
    monkeypatch.setitem(sys.modules, "scipy.spatial", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "scipy.spatial.distance",
        SimpleNamespace(cdist=lambda *_, **__: [[0.0, 0.1, 0.9], [0.1, 0.0, 0.8], [0.9, 0.8, 0.0]]),
    )
    monkeypatch.setattr(
        "platform.discovery.proximity.clustering._average_similarity",
        lambda *_: 0.5,
    )
    repo = SimpleNamespace(
        replace_clusters=AsyncMock(side_effect=lambda *args: args[-1]),
        update_hypothesis_cluster=AsyncMock(),
    )
    clustering = ProximityClustering(
        settings=PlatformSettings(),
        repository=repo,
        embedder=SimpleNamespace(fetch_session_embeddings=AsyncMock(return_value=embeddings)),
        publisher=SimpleNamespace(proximity_computed=AsyncMock()),
    )

    result = await clustering.compute(session_id, workspace_id)

    assert result.status == "normal"
    assert len(result.clusters) >= 2


@pytest.mark.asyncio
async def test_compute_uses_fallback_when_optional_deps_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = uuid4()
    workspace_id = uuid4()
    ids = [uuid4(), uuid4(), uuid4()]
    embeddings = [
        {
            "id": str(item),
            "vector": [1.0, float(index)],
            "payload": {"hypothesis_id": str(item), "title": f"H{index}"},
        }
        for index, item in enumerate(ids)
    ]
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name in {"numpy", "scipy.cluster.hierarchy", "scipy.spatial.distance"}:
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    repo = SimpleNamespace(
        replace_clusters=AsyncMock(side_effect=lambda *args: args[-1]),
        update_hypothesis_cluster=AsyncMock(),
    )
    clustering = ProximityClustering(
        settings=PlatformSettings(),
        repository=repo,
        embedder=SimpleNamespace(fetch_session_embeddings=AsyncMock(return_value=embeddings)),
        publisher=SimpleNamespace(proximity_computed=AsyncMock()),
    )

    result = await clustering.compute(session_id, workspace_id)

    assert result.status in {"normal", "saturated"}
    assert result.clusters


@pytest.mark.asyncio
async def test_proximity_clustering_task_wrapper_delegates() -> None:
    session_id = uuid4()
    workspace_id = uuid4()
    expected = SimpleNamespace(status="normal", clusters=[])
    clustering = SimpleNamespace(compute=AsyncMock(return_value=expected))

    result = await proximity_clustering_task(clustering, session_id, workspace_id)

    assert result is expected
    clustering.compute.assert_awaited_once_with(session_id, workspace_id)


def test_average_similarity_fallback_and_small_cluster_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "numpy":
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    assert _average_similarity([[0.0]], [0]) == 1.0
    assert _average_similarity([[0.0, 0.25], [0.25, 0.0]], [0, 1]) == pytest.approx(0.75)


def test_average_similarity_returns_one_for_singleton_cluster() -> None:
    assert _average_similarity([[0.0]], [0]) == 1.0
