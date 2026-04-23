from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from platform.common.clients.qdrant import workspace_filter
from platform.common.config import DiscoverySettings
from platform.discovery.events import DiscoveryEventPublisher
from platform.discovery.models import DiscoveryWorkspaceSettings, Hypothesis, HypothesisCluster
from platform.discovery.proximity.clustering import ProximityClustering
from platform.discovery.proximity.embeddings import HypothesisEmbedder
from platform.discovery.repository import DiscoveryRepository
from platform.discovery.schemas import (
    ClusterEntry,
    EdgeEntry,
    GapRegionEntry,
    NodeEntry,
    ProximityGraphResponse,
)
from typing import Any
from uuid import UUID

import httpx


@dataclass(frozen=True, slots=True)
class BiasSignal:
    workspace_id: UUID
    session_id: UUID | None
    explore_hints: list[str]
    avoid_hints: list[str]
    source: str
    generated_at: datetime
    skipped: bool
    skip_reason: str | None = None
    min_hypotheses_required: int | None = None
    current_embedded_count: int | None = None


@dataclass(frozen=True, slots=True)
class IndexResult:
    hypothesis_id: UUID
    status: str
    qdrant_point_id: str | None = None


@dataclass(frozen=True, slots=True)
class RecomputeResult:
    workspace_id: UUID
    cluster_count: int
    gap_count: int
    transition_summary: dict[str, Any]


class ProximityGraphService:
    """Workspace-scope proximity graph orchestration."""

    def __init__(
        self,
        *,
        embedder: HypothesisEmbedder,
        clustering: ProximityClustering,
        repository: DiscoveryRepository,
        event_publisher: DiscoveryEventPublisher,
        settings: DiscoverySettings,
    ) -> None:
        self.embedder = embedder
        self.clustering = clustering
        self.repository = repository
        self.publisher = event_publisher
        self.settings = settings

    async def compute_workspace_graph(
        self,
        workspace_id: UUID,
        session_id: UUID | None = None,
        include_edges: bool = True,
        max_nodes: int = 10_000,
    ) -> ProximityGraphResponse:
        workspace_settings = await self._get_or_create_workspace_settings(workspace_id)
        hypotheses = await self.repository.list_hypotheses_for_workspace(workspace_id, session_id)
        pending_embedding_count = sum(
            1 for item in hypotheses if item.embedding_status == "pending"
        )
        indexed = [item for item in hypotheses if item.embedding_status == "indexed"]
        truncated = len(hypotheses) > max_nodes
        visible_hypotheses = hypotheses[:max_nodes]
        visible_indexed_ids = {
            item.id for item in visible_hypotheses if item.embedding_status == "indexed"
        }
        if len(indexed) < self.settings.min_hypotheses:
            return ProximityGraphResponse(
                workspace_id=workspace_id,
                session_id=session_id,
                status="pre_proximity",
                saturation_indicator="low_data",
                computed_at=workspace_settings.last_recomputed_at,
                pending_embedding_count=pending_embedding_count,
                truncated=truncated,
                min_hypotheses_required=self.settings.min_hypotheses,
                current_embedded_count=len(indexed),
                nodes=[self._node_entry(item) for item in visible_hypotheses],
            )

        cluster_rows = (
            await self.repository.list_clusters(session_id, workspace_id)
            if session_id is not None
            else await self.repository.list_workspace_clusters(workspace_id)
        )
        edges = []
        if include_edges and visible_indexed_ids:
            embeddings = await self.embedder.fetch_workspace_embeddings(
                workspace_id,
                session_id=session_id,
            )
            vector_by_id = {
                UUID(item["payload"]["hypothesis_id"]): item["vector"]
                for item in embeddings
                if item.get("payload", {}).get("hypothesis_id")
            }
            edges = await self._build_edges(
                workspace_id,
                session_id=session_id,
                vector_by_id={
                    key: value for key, value in vector_by_id.items() if key in visible_indexed_ids
                },
                allowed_ids=visible_indexed_ids,
            )

        return ProximityGraphResponse(
            workspace_id=workspace_id,
            session_id=session_id,
            status="computed",
            saturation_indicator=self._saturation_indicator(cluster_rows),
            computed_at=workspace_settings.last_recomputed_at,
            staleness_warning=self._staleness_warning(workspace_settings),
            pending_embedding_count=pending_embedding_count,
            truncated=truncated,
            current_embedded_count=len(indexed),
            nodes=[self._node_entry(item) for item in visible_hypotheses],
            edges=edges,
            clusters=[
                self._cluster_entry(item) for item in cluster_rows if item.classification != "gap"
            ],
            gap_regions=[
                self._gap_region(item) for item in cluster_rows if item.classification == "gap"
            ],
        )

    async def derive_bias_signal(
        self,
        workspace_id: UUID,
        session_id: UUID | None,
    ) -> BiasSignal:
        workspace_settings = await self._get_or_create_workspace_settings(workspace_id)
        if not workspace_settings.bias_enabled:
            return BiasSignal(
                workspace_id=workspace_id,
                session_id=session_id,
                explore_hints=[],
                avoid_hints=[],
                source="session_scope" if session_id is not None else "workspace_scope",
                generated_at=datetime.now(UTC),
                skipped=True,
                skip_reason="bias_disabled",
            )
        indexed = await self.repository.list_hypotheses_for_workspace(
            workspace_id,
            session_id,
            embedding_status="indexed",
        )
        if len(indexed) < self.settings.min_hypotheses:
            return BiasSignal(
                workspace_id=workspace_id,
                session_id=session_id,
                explore_hints=[],
                avoid_hints=[],
                source="session_scope" if session_id is not None else "workspace_scope",
                generated_at=datetime.now(UTC),
                skipped=True,
                skip_reason="insufficient_data",
                min_hypotheses_required=self.settings.min_hypotheses,
                current_embedded_count=len(indexed),
            )
        cluster_rows = (
            await self.repository.list_clusters(session_id, workspace_id)
            if session_id is not None
            else await self.repository.list_workspace_clusters(workspace_id)
        )
        if not cluster_rows:
            return BiasSignal(
                workspace_id=workspace_id,
                session_id=session_id,
                explore_hints=[],
                avoid_hints=[],
                source="session_scope" if session_id is not None else "workspace_scope",
                generated_at=datetime.now(UTC),
                skipped=True,
                skip_reason="graph_stale",
            )
        return BiasSignal(
            workspace_id=workspace_id,
            session_id=session_id,
            explore_hints=[
                row.centroid_description for row in cluster_rows if row.classification == "gap"
            ],
            avoid_hints=[
                row.centroid_description
                for row in cluster_rows
                if row.classification == "over_explored"
            ],
            source="session_scope" if session_id is not None else "workspace_scope",
            generated_at=datetime.now(UTC),
            skipped=False,
        )

    async def index_hypothesis(self, hypothesis_id: UUID) -> IndexResult:
        hypothesis = await self.repository.get_hypothesis_any(hypothesis_id)
        if hypothesis is None:
            return IndexResult(hypothesis_id=hypothesis_id, status="missing")
        try:
            await self.embedder.embed_hypothesis(hypothesis)
            hypothesis.embedding_status = "indexed"
            await self.repository.session.flush()
            return IndexResult(
                hypothesis_id=hypothesis_id,
                status="indexed",
                qdrant_point_id=hypothesis.qdrant_point_id,
            )
        except ValueError:
            hypothesis.embedding_status = "failed"
        except httpx.HTTPStatusError as exc:
            hypothesis.embedding_status = "pending" if exc.response.status_code >= 500 else "failed"
        except (httpx.ConnectError, httpx.TimeoutException):
            hypothesis.embedding_status = "pending"
        except Exception:
            hypothesis.embedding_status = "pending"
        await self.repository.session.flush()
        return IndexResult(
            hypothesis_id=hypothesis_id,
            status=hypothesis.embedding_status,
            qdrant_point_id=hypothesis.qdrant_point_id,
        )

    async def recompute_workspace_graph(self, workspace_id: UUID) -> RecomputeResult:
        workspace_settings = await self._get_or_create_workspace_settings(workspace_id)
        embeddings = await self.embedder.fetch_workspace_embeddings(workspace_id)
        result = self.clustering.compute_embeddings(
            embeddings,
            workspace_id=workspace_id,
            session_id=None,
        )
        previous = await self.repository.list_workspace_clusters(workspace_id)
        transitions = await self._emit_transitions(workspace_id, previous, result.clusters)
        await self.repository.replace_workspace_clusters(workspace_id, result.clusters)
        now = datetime.now(UTC)
        summary = {
            "clusters_newly_saturated": transitions["clusters_newly_saturated"],
            "gaps_filled": transitions["gaps_filled"],
            "total_clusters": sum(1 for item in result.clusters if item.classification != "gap"),
            "total_gaps": sum(1 for item in result.clusters if item.classification == "gap"),
            "saturation_ratio": transitions["saturation_ratio"],
        }
        await self.repository.upsert_workspace_settings(
            workspace_id,
            bias_enabled=workspace_settings.bias_enabled,
            recompute_interval_minutes=workspace_settings.recompute_interval_minutes,
            last_recomputed_at=now,
            last_transition_summary=summary,
        )
        await self.publisher.proximity_computed(None, workspace_id, len(result.clusters))
        return RecomputeResult(
            workspace_id=workspace_id,
            cluster_count=summary["total_clusters"],
            gap_count=summary["total_gaps"],
            transition_summary=summary,
        )

    async def _emit_transitions(
        self,
        workspace_id: UUID,
        previous: list[HypothesisCluster],
        current: list[HypothesisCluster],
    ) -> dict[str, Any]:
        previous_by_label = {item.cluster_label: item for item in previous}
        current_by_label = {item.cluster_label: item for item in current}
        saturated: list[str] = []
        for label, current_cluster in current_by_label.items():
            previous_cluster = previous_by_label.get(label)
            if previous_cluster is None:
                continue
            density_delta = abs(current_cluster.density_metric - previous_cluster.density_metric)
            if (
                previous_cluster.classification == "normal"
                and current_cluster.classification == "over_explored"
                and density_delta >= 0.02
            ):
                saturated.append(label)
                await self.publisher.cluster_saturated(
                    workspace_id=workspace_id,
                    cluster_id=label,
                    classification_from=previous_cluster.classification,
                    classification_to=current_cluster.classification,
                    member_count=current_cluster.hypothesis_count,
                    density=current_cluster.density_metric,
                )
        previous_gaps = {
            item.centroid_description: item for item in previous if item.classification == "gap"
        }
        current_gaps = {
            item.centroid_description: item for item in current if item.classification == "gap"
        }
        gap_filled: list[str] = []
        current_clusters = [item for item in current if item.classification != "gap"]
        for label, gap in previous_gaps.items():
            if label in current_gaps:
                continue
            cluster_id = self._resolve_gap_cluster(gap, current_clusters)
            gap_filled.append(label)
            await self.publisher.gap_filled(
                workspace_id=workspace_id,
                former_gap_label=label,
                now_part_of_cluster_id=cluster_id,
            )
        total_clusters = max(1, len(current_clusters))
        return {
            "clusters_newly_saturated": saturated,
            "gaps_filled": gap_filled,
            "saturation_ratio": len(
                [item for item in current_clusters if item.classification == "over_explored"]
            )
            / total_clusters,
        }

    async def _build_edges(
        self,
        workspace_id: UUID,
        *,
        session_id: UUID | None,
        vector_by_id: dict[UUID, list[float]],
        allowed_ids: set[UUID],
    ) -> list[EdgeEntry]:
        if not vector_by_id or self.embedder.qdrant is None:
            return []
        models = import_module("qdrant_client.models")
        extra_filter = None
        if session_id is not None:
            extra_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="session_id",
                        match=models.MatchValue(value=str(session_id)),
                    )
                ]
            )
        query_filter = workspace_filter(str(workspace_id), extra=extra_filter)
        edges: dict[tuple[UUID, UUID], EdgeEntry] = {}
        for source_id, vector in vector_by_id.items():
            results = await self.embedder.qdrant.search_vectors(
                self.settings.qdrant_collection,
                vector,
                self.settings.proximity_graph_max_neighbors_per_node + 1,
                filter=query_filter,
            )
            for item in results:
                target_raw = item.get("payload", {}).get("hypothesis_id")
                if target_raw is None:
                    continue
                target_id = UUID(str(target_raw))
                if target_id == source_id or target_id not in allowed_ids:
                    continue
                left, right = sorted((source_id, target_id), key=lambda value: value.int)
                key = (left, right)
                score = max(0.0, min(1.0, float(item.get("score", 0.0))))
                if key not in edges or score > edges[key].similarity:
                    edges[key] = EdgeEntry(
                        source_hypothesis_id=left,
                        target_hypothesis_id=right,
                        similarity=score,
                    )
        return list(edges.values())

    async def _get_or_create_workspace_settings(
        self, workspace_id: UUID
    ) -> DiscoveryWorkspaceSettings:
        settings = await self.repository.get_workspace_settings(workspace_id)
        if settings is not None:
            return settings
        return await self.repository.upsert_workspace_settings(
            workspace_id,
            bias_enabled=self.settings.proximity_bias_default_enabled,
            recompute_interval_minutes=self.settings.proximity_graph_recompute_interval_minutes,
        )

    def _staleness_warning(self, workspace_settings: DiscoveryWorkspaceSettings) -> str | None:
        if workspace_settings.last_recomputed_at is None:
            return None
        delta = datetime.now(UTC) - workspace_settings.last_recomputed_at.astimezone(UTC)
        minutes = int(delta.total_seconds() // 60)
        if minutes <= self.settings.proximity_graph_staleness_warning_minutes:
            return None
        return (
            f"Graph last computed {minutes} minutes ago; staleness threshold is "
            f"{self.settings.proximity_graph_staleness_warning_minutes} minutes."
        )

    def _saturation_indicator(self, cluster_rows: list[HypothesisCluster]) -> str:
        if not cluster_rows:
            return "low_data"
        if any(item.classification == "over_explored" for item in cluster_rows):
            return "saturated"
        return "normal"

    def _node_entry(self, hypothesis: Hypothesis) -> NodeEntry:
        return NodeEntry(
            hypothesis_id=hypothesis.id,
            cluster_id=hypothesis.cluster_id,
            embedding_status=hypothesis.embedding_status,
        )

    def _cluster_entry(self, cluster: HypothesisCluster) -> ClusterEntry:
        classification = cluster.classification
        if classification == "normal" and cluster.hypothesis_count <= 1:
            classification = "under_explored"
        return ClusterEntry(
            cluster_id=cluster.cluster_label,
            centroid_description=cluster.centroid_description,
            classification=classification,
            hypothesis_ids=[UUID(item) for item in cluster.hypothesis_ids],
            density=max(0.0, min(1.0, float(cluster.density_metric))),
        )

    def _gap_region(self, cluster: HypothesisCluster) -> GapRegionEntry:
        center_id = None
        if cluster.hypothesis_ids:
            center_id = UUID(cluster.hypothesis_ids[0])
        return GapRegionEntry(
            label=cluster.centroid_description,
            center_hypothesis_id=center_id,
            min_distance_to_nearest=max(0.0, min(1.0, 1.0 - float(cluster.density_metric))),
        )

    def _resolve_gap_cluster(
        self,
        gap: HypothesisCluster,
        clusters: list[HypothesisCluster],
    ) -> str | None:
        if not gap.hypothesis_ids:
            return clusters[0].cluster_label if clusters else None
        center_id = gap.hypothesis_ids[0]
        for cluster in clusters:
            if center_id in cluster.hypothesis_ids:
                return cluster.cluster_label
        return clusters[0].cluster_label if clusters else None
