from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.discovery.models import DiscoveryWorkspaceSettings, Hypothesis, HypothesisCluster
from platform.discovery.proximity.clustering import ProximityComputationResult
from platform.discovery.proximity.graph import ProximityGraphService
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest


class RepositoryStub:
    def __init__(self) -> None:
        self.session = SimpleNamespace(flush=AsyncMock())
        self.workspace_settings = None
        self.hypotheses: list[Hypothesis] = []
        self.workspace_clusters: list[HypothesisCluster] = []
        self.session_clusters: list[HypothesisCluster] = []
        self.replaced: list[HypothesisCluster] = []
        self.get_hypothesis_any = AsyncMock(side_effect=self._get_hypothesis_any)
        self.list_hypotheses_for_workspace = AsyncMock(
            side_effect=self._list_hypotheses_for_workspace
        )
        self.get_workspace_settings = AsyncMock(
            side_effect=lambda workspace_id: self.workspace_settings
        )
        self.upsert_workspace_settings = AsyncMock(side_effect=self._upsert_workspace_settings)
        self.list_workspace_clusters = AsyncMock(
            side_effect=lambda workspace_id: list(self.workspace_clusters)
        )
        self.list_clusters = AsyncMock(
            side_effect=lambda session_id, workspace_id: list(self.session_clusters)
        )
        self.replace_workspace_clusters = AsyncMock(side_effect=self._replace_workspace_clusters)

    async def _get_hypothesis_any(self, hypothesis_id):
        return next((item for item in self.hypotheses if item.id == hypothesis_id), None)

    async def _list_hypotheses_for_workspace(
        self, workspace_id, session_id=None, embedding_status=None
    ):
        items = [
            item
            for item in self.hypotheses
            if item.workspace_id == workspace_id and item.status == "active"
        ]
        if session_id is not None:
            items = [item for item in items if item.session_id == session_id]
        if isinstance(embedding_status, list):
            items = [item for item in items if item.embedding_status in embedding_status]
        elif embedding_status is not None:
            items = [item for item in items if item.embedding_status == embedding_status]
        return items

    async def _upsert_workspace_settings(self, workspace_id, **fields):
        base = self.workspace_settings or DiscoveryWorkspaceSettings(
            workspace_id=workspace_id,
            bias_enabled=True,
            recompute_interval_minutes=15,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        for key, value in fields.items():
            setattr(base, key, value)
        self.workspace_settings = base
        return base

    async def _replace_workspace_clusters(self, workspace_id, cluster_entries):
        self.replaced = list(cluster_entries)
        self.workspace_clusters = list(cluster_entries)
        return cluster_entries


def _hypothesis(workspace_id, session_id, *, indexed=True, created_at=None):
    return Hypothesis(
        id=uuid4(),
        workspace_id=workspace_id,
        session_id=session_id,
        title="hypothesis",
        description="description",
        reasoning="reasoning",
        confidence=0.7,
        generating_agent_fqn="discovery.generator",
        status="active",
        embedding_status="indexed" if indexed else "pending",
        qdrant_point_id="p" if indexed else None,
        created_at=created_at or datetime.now(UTC),
        updated_at=created_at or datetime.now(UTC),
    )


def _settings():
    return SimpleNamespace(
        min_hypotheses=3,
        proximity_bias_default_enabled=True,
        proximity_graph_recompute_interval_minutes=15,
        proximity_graph_staleness_warning_minutes=60,
        proximity_graph_max_neighbors_per_node=8,
        qdrant_collection="discovery_hypotheses",
    )


def _cluster(workspace_id, label, *, classification="normal", density=0.7, hypothesis_ids=None):
    return HypothesisCluster(
        id=uuid4(),
        workspace_id=workspace_id,
        session_id=None,
        cluster_label=label,
        centroid_description=label,
        hypothesis_count=len(hypothesis_ids or []),
        density_metric=density,
        classification=classification,
        hypothesis_ids=[str(item) for item in (hypothesis_ids or [])],
        computed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_compute_workspace_graph_returns_pre_proximity_and_creates_defaults() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    repo = RepositoryStub()
    repo.hypotheses = [_hypothesis(workspace_id, session_id, indexed=False) for _ in range(2)]
    service = ProximityGraphService(
        embedder=SimpleNamespace(fetch_workspace_embeddings=AsyncMock(), qdrant=None),
        clustering=SimpleNamespace(),
        repository=repo,
        event_publisher=SimpleNamespace(),
        settings=SimpleNamespace(
            min_hypotheses=3,
            proximity_bias_default_enabled=True,
            proximity_graph_recompute_interval_minutes=15,
            proximity_graph_staleness_warning_minutes=60,
            proximity_graph_max_neighbors_per_node=8,
            qdrant_collection="discovery_hypotheses",
        ),
    )

    response = await service.compute_workspace_graph(workspace_id)

    assert response.status == "pre_proximity"
    assert response.current_embedded_count == 0
    assert response.pending_embedding_count == 2
    repo.upsert_workspace_settings.assert_awaited_once()


@pytest.mark.asyncio
async def test_compute_workspace_graph_builds_edges_truncates_and_marks_stale() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    repo = RepositoryStub()
    created_at = datetime.now(UTC) - timedelta(hours=2)
    first = _hypothesis(workspace_id, session_id, indexed=True, created_at=created_at)
    second = _hypothesis(workspace_id, session_id, indexed=True, created_at=created_at)
    third = _hypothesis(workspace_id, session_id, indexed=True, created_at=created_at)
    repo.hypotheses = [first, second, third]
    repo.workspace_settings = DiscoveryWorkspaceSettings(
        workspace_id=workspace_id,
        bias_enabled=True,
        recompute_interval_minutes=15,
        last_recomputed_at=datetime.now(UTC) - timedelta(minutes=90),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.workspace_clusters = [
        _cluster(
            workspace_id,
            "cluster-a",
            classification="over_explored",
            density=0.9,
            hypothesis_ids=[first.id, second.id],
        ),
        _cluster(
            workspace_id,
            f"Potential gap near {third.id}",
            classification="gap",
            density=0.0,
            hypothesis_ids=[third.id],
        ),
    ]
    qdrant = SimpleNamespace(
        search_vectors=AsyncMock(
            side_effect=[
                [{"payload": {"hypothesis_id": str(second.id)}, "score": 0.91}],
                [{"payload": {"hypothesis_id": str(first.id)}, "score": 0.91}],
            ]
        )
    )
    service = ProximityGraphService(
        embedder=SimpleNamespace(
            fetch_workspace_embeddings=AsyncMock(
                return_value=[
                    {"payload": {"hypothesis_id": str(first.id)}, "vector": [1.0, 0.0]},
                    {"payload": {"hypothesis_id": str(second.id)}, "vector": [0.9, 0.1]},
                    {"payload": {"hypothesis_id": str(third.id)}, "vector": [0.8, 0.2]},
                ]
            ),
            qdrant=qdrant,
        ),
        clustering=SimpleNamespace(),
        repository=repo,
        event_publisher=SimpleNamespace(),
        settings=SimpleNamespace(
            min_hypotheses=3,
            proximity_bias_default_enabled=True,
            proximity_graph_recompute_interval_minutes=15,
            proximity_graph_staleness_warning_minutes=60,
            proximity_graph_max_neighbors_per_node=2,
            qdrant_collection="discovery_hypotheses",
        ),
    )

    response = await service.compute_workspace_graph(workspace_id, include_edges=True, max_nodes=2)

    assert response.status == "computed"
    assert response.truncated is True
    assert response.saturation_indicator == "saturated"
    assert response.staleness_warning is not None
    assert len(response.nodes) == 2
    assert len(response.edges) == 1
    assert response.gap_regions[0].center_hypothesis_id == third.id


@pytest.mark.asyncio
async def test_compute_workspace_graph_skips_edges_when_disabled() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    repo = RepositoryStub()
    repo.workspace_settings = DiscoveryWorkspaceSettings(
        workspace_id=workspace_id,
        bias_enabled=True,
        recompute_interval_minutes=15,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.hypotheses = [_hypothesis(workspace_id, session_id, indexed=True) for _ in range(3)]
    qdrant = SimpleNamespace(search_vectors=AsyncMock())
    service = ProximityGraphService(
        embedder=SimpleNamespace(
            fetch_workspace_embeddings=AsyncMock(return_value=[]), qdrant=qdrant
        ),
        clustering=SimpleNamespace(),
        repository=repo,
        event_publisher=SimpleNamespace(),
        settings=SimpleNamespace(
            min_hypotheses=3,
            proximity_bias_default_enabled=True,
            proximity_graph_recompute_interval_minutes=15,
            proximity_graph_staleness_warning_minutes=60,
            proximity_graph_max_neighbors_per_node=8,
            qdrant_collection="discovery_hypotheses",
        ),
    )

    response = await service.compute_workspace_graph(workspace_id, include_edges=False)

    assert response.edges == []
    qdrant.search_vectors.assert_not_awaited()


@pytest.mark.asyncio
async def test_derive_bias_signal_covers_disabled_insufficient_and_happy_path() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    repo = RepositoryStub()
    repo.workspace_settings = DiscoveryWorkspaceSettings(
        workspace_id=workspace_id,
        bias_enabled=False,
        recompute_interval_minutes=15,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    service = ProximityGraphService(
        embedder=SimpleNamespace(qdrant=None),
        clustering=SimpleNamespace(),
        repository=repo,
        event_publisher=SimpleNamespace(),
        settings=SimpleNamespace(
            min_hypotheses=3,
            proximity_bias_default_enabled=True,
            proximity_graph_recompute_interval_minutes=15,
            proximity_graph_staleness_warning_minutes=60,
            proximity_graph_max_neighbors_per_node=8,
            qdrant_collection="discovery_hypotheses",
        ),
    )

    disabled = await service.derive_bias_signal(workspace_id, session_id)
    assert disabled.skipped is True
    assert disabled.skip_reason == "bias_disabled"

    repo.workspace_settings.bias_enabled = True
    repo.hypotheses = [_hypothesis(workspace_id, session_id, indexed=True) for _ in range(2)]
    insufficient = await service.derive_bias_signal(workspace_id, session_id)
    assert insufficient.skip_reason == "insufficient_data"

    third = _hypothesis(workspace_id, session_id, indexed=True)
    repo.hypotheses.append(third)
    repo.session_clusters = [
        _cluster(
            workspace_id, "gap region", classification="gap", density=0.0, hypothesis_ids=[third.id]
        ),
        _cluster(
            workspace_id,
            "cluster-full",
            classification="over_explored",
            density=0.91,
            hypothesis_ids=[third.id],
        ),
    ]
    happy = await service.derive_bias_signal(workspace_id, session_id)
    assert happy.skipped is False
    assert happy.explore_hints == ["gap region"]
    assert happy.avoid_hints == ["cluster-full"]


@pytest.mark.asyncio
async def test_index_hypothesis_handles_success_pending_and_failed() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    repo = RepositoryStub()
    success = _hypothesis(workspace_id, session_id, indexed=False)
    pending = _hypothesis(workspace_id, session_id, indexed=False)
    failed = _hypothesis(workspace_id, session_id, indexed=False)
    repo.hypotheses = [success, pending, failed]
    response = httpx.Response(503, request=httpx.Request("POST", "http://embedding"))
    service = ProximityGraphService(
        embedder=SimpleNamespace(
            embed_hypothesis=AsyncMock(
                side_effect=[
                    [0.1, 0.2],
                    httpx.HTTPStatusError("down", request=response.request, response=response),
                    ValueError("bad content"),
                ]
            ),
            qdrant=None,
        ),
        clustering=SimpleNamespace(),
        repository=repo,
        event_publisher=SimpleNamespace(),
        settings=SimpleNamespace(
            min_hypotheses=3,
            proximity_bias_default_enabled=True,
            proximity_graph_recompute_interval_minutes=15,
            proximity_graph_staleness_warning_minutes=60,
            proximity_graph_max_neighbors_per_node=8,
            qdrant_collection="discovery_hypotheses",
        ),
    )

    success_result = await service.index_hypothesis(success.id)
    pending_result = await service.index_hypothesis(pending.id)
    failed_result = await service.index_hypothesis(failed.id)

    assert success_result.status == "indexed"
    assert pending_result.status == "pending"
    assert failed_result.status == "failed"


@pytest.mark.asyncio
async def test_recompute_workspace_graph_emits_transition_events_and_replaces_clusters() -> None:
    workspace_id = uuid4()
    anchor = uuid4()
    repo = RepositoryStub()
    repo.workspace_settings = DiscoveryWorkspaceSettings(
        workspace_id=workspace_id,
        bias_enabled=True,
        recompute_interval_minutes=15,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.workspace_clusters = [
        _cluster(
            workspace_id,
            "cluster-1",
            classification="normal",
            density=0.70,
            hypothesis_ids=[anchor],
        ),
        _cluster(
            workspace_id,
            f"Potential gap near {anchor}",
            classification="gap",
            density=0.0,
            hypothesis_ids=[anchor],
        ),
    ]
    publisher = SimpleNamespace(
        cluster_saturated=AsyncMock(),
        gap_filled=AsyncMock(),
        proximity_computed=AsyncMock(),
    )
    clustering = SimpleNamespace(
        compute_embeddings=lambda embeddings, **kwargs: ProximityComputationResult(
            status="saturated",
            clusters=[
                _cluster(
                    workspace_id,
                    "cluster-1",
                    classification="over_explored",
                    density=0.85,
                    hypothesis_ids=[anchor],
                )
            ],
            landscape_context={},
        )
    )
    service = ProximityGraphService(
        embedder=SimpleNamespace(
            fetch_workspace_embeddings=AsyncMock(
                return_value=[{"payload": {"hypothesis_id": str(anchor)}, "vector": [1.0, 0.0]}]
            ),
            qdrant=None,
        ),
        clustering=clustering,
        repository=repo,
        event_publisher=publisher,
        settings=SimpleNamespace(
            min_hypotheses=3,
            proximity_bias_default_enabled=True,
            proximity_graph_recompute_interval_minutes=15,
            proximity_graph_staleness_warning_minutes=60,
            proximity_graph_max_neighbors_per_node=8,
            qdrant_collection="discovery_hypotheses",
        ),
    )

    result = await service.recompute_workspace_graph(workspace_id)

    assert result.transition_summary["clusters_newly_saturated"] == ["cluster-1"]
    assert result.transition_summary["gaps_filled"] == [f"Potential gap near {anchor}"]
    publisher.cluster_saturated.assert_awaited_once()
    publisher.gap_filled.assert_awaited_once()
    publisher.proximity_computed.assert_awaited_once()
    assert repo.replaced[0].classification == "over_explored"


@pytest.mark.asyncio
async def test_recompute_workspace_graph_tolerance_band_suppresses_flapping() -> None:
    workspace_id = uuid4()
    anchor = uuid4()
    repo = RepositoryStub()
    repo.workspace_settings = DiscoveryWorkspaceSettings(
        workspace_id=workspace_id,
        bias_enabled=True,
        recompute_interval_minutes=15,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.workspace_clusters = [
        _cluster(
            workspace_id,
            "cluster-1",
            classification="normal",
            density=0.84,
            hypothesis_ids=[anchor],
        )
    ]
    publisher = SimpleNamespace(
        cluster_saturated=AsyncMock(),
        gap_filled=AsyncMock(),
        proximity_computed=AsyncMock(),
    )
    clustering = SimpleNamespace(
        compute_embeddings=lambda embeddings, **kwargs: ProximityComputationResult(
            status="saturated",
            clusters=[
                _cluster(
                    workspace_id,
                    "cluster-1",
                    classification="over_explored",
                    density=0.85,
                    hypothesis_ids=[anchor],
                )
            ],
            landscape_context={},
        )
    )
    service = ProximityGraphService(
        embedder=SimpleNamespace(
            fetch_workspace_embeddings=AsyncMock(
                return_value=[{"payload": {"hypothesis_id": str(anchor)}, "vector": [1.0, 0.0]}]
            ),
            qdrant=None,
        ),
        clustering=clustering,
        repository=repo,
        event_publisher=publisher,
        settings=SimpleNamespace(
            min_hypotheses=3,
            proximity_bias_default_enabled=True,
            proximity_graph_recompute_interval_minutes=15,
            proximity_graph_staleness_warning_minutes=60,
            proximity_graph_max_neighbors_per_node=8,
            qdrant_collection="discovery_hypotheses",
        ),
    )

    result = await service.recompute_workspace_graph(workspace_id)

    assert result.transition_summary["clusters_newly_saturated"] == []
    publisher.cluster_saturated.assert_not_awaited()


@pytest.mark.asyncio
async def test_derive_bias_signal_returns_graph_stale_without_clusters() -> None:
    workspace_id = uuid4()
    repo = RepositoryStub()
    repo.workspace_settings = DiscoveryWorkspaceSettings(
        workspace_id=workspace_id,
        bias_enabled=True,
        recompute_interval_minutes=15,
        last_recomputed_at=datetime.now(UTC),
    )
    repo.hypotheses = [_hypothesis(workspace_id, uuid4(), indexed=True) for _ in range(3)]
    service = ProximityGraphService(
        embedder=SimpleNamespace(
            fetch_workspace_embeddings=AsyncMock(return_value=[]),
            qdrant=None,
        ),
        clustering=SimpleNamespace(),
        repository=repo,
        event_publisher=SimpleNamespace(),
        settings=_settings(),
    )

    signal = await service.derive_bias_signal(workspace_id, None)

    assert signal.skipped is True
    assert signal.skip_reason == "graph_stale"


@pytest.mark.asyncio
async def test_index_hypothesis_handles_missing_and_generic_failure() -> None:
    workspace_id = uuid4()
    existing = _hypothesis(workspace_id, uuid4(), indexed=False)
    repo = RepositoryStub()
    repo.hypotheses = [existing]
    embedder = SimpleNamespace(
        embed_hypothesis=AsyncMock(side_effect=RuntimeError("boom")),
        fetch_workspace_embeddings=AsyncMock(return_value=[]),
        qdrant=None,
    )
    service = ProximityGraphService(
        embedder=embedder,
        clustering=SimpleNamespace(),
        repository=repo,
        event_publisher=SimpleNamespace(),
        settings=_settings(),
    )

    timeout = _hypothesis(workspace_id, uuid4(), indexed=False)
    repo.hypotheses.append(timeout)
    embedder.embed_hypothesis = AsyncMock(
        side_effect=[RuntimeError("boom"), httpx.TimeoutException("timeout")]
    )

    missing = await service.index_hypothesis(uuid4())
    failed = await service.index_hypothesis(existing.id)
    timed_out = await service.index_hypothesis(timeout.id)

    assert missing.status == "missing"
    assert failed.status == "pending"
    assert timed_out.status == "pending"
    assert existing.embedding_status == "pending"


@pytest.mark.asyncio
async def test_internal_graph_helpers_cover_filtering_and_classification() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    first = _hypothesis(workspace_id, session_id, indexed=True)
    second = _hypothesis(workspace_id, session_id, indexed=True)
    third = _hypothesis(workspace_id, session_id, indexed=True)
    qdrant = SimpleNamespace(
        search_vectors=AsyncMock(
            return_value=[
                {"payload": {}, "score": 0.9},
                {"payload": {"hypothesis_id": str(first.id)}, "score": 0.8},
                {"payload": {"hypothesis_id": str(third.id)}, "score": 0.7},
                {"payload": {"hypothesis_id": str(second.id)}, "score": 0.6},
            ]
        )
    )
    service = ProximityGraphService(
        embedder=SimpleNamespace(
            fetch_workspace_embeddings=AsyncMock(return_value=[]),
            qdrant=qdrant,
        ),
        clustering=SimpleNamespace(),
        repository=RepositoryStub(),
        event_publisher=SimpleNamespace(),
        settings=_settings(),
    )

    edges = await service._build_edges(
        workspace_id,
        session_id=session_id,
        vector_by_id={first.id: [1.0, 0.0]},
        allowed_ids={first.id, second.id},
    )
    under = service._cluster_entry(
        _cluster(
            workspace_id,
            "singleton",
            classification="normal",
            density=0.4,
            hypothesis_ids=[first.id],
        )
    )
    gap = service._gap_region(
        _cluster(workspace_id, "gap", classification="gap", density=0.0, hypothesis_ids=[])
    )
    resolved_empty = service._resolve_gap_cluster(
        _cluster(workspace_id, "gap", classification="gap", density=0.0, hypothesis_ids=[]),
        [
            _cluster(
                workspace_id,
                "target",
                classification="normal",
                density=0.4,
                hypothesis_ids=[second.id],
            )
        ],
    )
    resolved_missing = service._resolve_gap_cluster(
        _cluster(
            workspace_id,
            "gap",
            classification="gap",
            density=0.0,
            hypothesis_ids=[str(third.id)],
        ),
        [
            _cluster(
                workspace_id,
                "target",
                classification="normal",
                density=0.4,
                hypothesis_ids=[second.id],
            )
        ],
    )

    assert len(edges) == 1
    assert {edges[0].source_hypothesis_id, edges[0].target_hypothesis_id} == {first.id, second.id}
    assert under.classification == "under_explored"
    assert gap.center_hypothesis_id is None
    assert resolved_empty == "target"
    assert resolved_missing == "target"


@pytest.mark.asyncio
async def test_graph_helper_paths_cover_empty_edges_and_normal_staleness() -> None:
    workspace_id = uuid4()
    service = ProximityGraphService(
        embedder=SimpleNamespace(
            fetch_workspace_embeddings=AsyncMock(return_value=[]),
            qdrant=None,
        ),
        clustering=SimpleNamespace(),
        repository=RepositoryStub(),
        event_publisher=SimpleNamespace(),
        settings=_settings(),
    )
    fresh = DiscoveryWorkspaceSettings(
        workspace_id=workspace_id,
        bias_enabled=True,
        recompute_interval_minutes=15,
        last_recomputed_at=datetime.now(UTC),
    )

    edges = await service._build_edges(
        workspace_id,
        session_id=None,
        vector_by_id={uuid4(): [1.0]},
        allowed_ids={uuid4()},
    )
    transition_summary = await service._emit_transitions(
        workspace_id,
        previous=[],
        current=[_cluster(workspace_id, "new", classification="normal", density=0.4)],
    )

    assert edges == []
    assert transition_summary["clusters_newly_saturated"] == []
    assert transition_summary["gaps_filled"] == []
    assert service._staleness_warning(fresh) is None
    assert service._saturation_indicator([_cluster(workspace_id, "normal")]) == "normal"
