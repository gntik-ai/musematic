from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.discovery.events import DiscoveryEventPublisher
from platform.discovery.models import HypothesisCluster
from platform.discovery.proximity.embeddings import HypothesisEmbedder
from platform.discovery.repository import DiscoveryRepository
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProximityComputationResult:
    status: str
    clusters: list[HypothesisCluster]
    landscape_context: dict[str, Any]


class ProximityClustering:
    """Compute hypothesis proximity clusters from Qdrant embeddings."""

    def __init__(
        self,
        *,
        settings: PlatformSettings,
        repository: DiscoveryRepository,
        embedder: HypothesisEmbedder,
        publisher: DiscoveryEventPublisher,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.embedder = embedder
        self.publisher = publisher

    async def compute(self, session_id: UUID, workspace_id: UUID) -> ProximityComputationResult:
        embeddings = await self.embedder.fetch_session_embeddings(session_id, workspace_id)
        result = self.compute_embeddings(
            embeddings,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        await self.repository.replace_clusters(session_id, workspace_id, result.clusters)
        for cluster in result.clusters:
            for hypothesis_id in cluster.hypothesis_ids:
                await self.repository.update_hypothesis_cluster(
                    UUID(hypothesis_id),
                    workspace_id,
                    cluster.cluster_label,
                )
        await self.publisher.proximity_computed(session_id, workspace_id, len(result.clusters))
        return result

    def compute_embeddings(
        self,
        embeddings: list[dict[str, Any]],
        *,
        workspace_id: UUID,
        session_id: UUID | None,
    ) -> ProximityComputationResult:
        if len(embeddings) < 3:
            return ProximityComputationResult(
                status="low_data",
                clusters=[],
                landscape_context={"status": "low_data", "gap_descriptions": []},
            )
        try:
            import numpy as np
            from scipy.cluster.hierarchy import fclusterdata
            from scipy.spatial.distance import cdist

            vectors = np.array([item["vector"] for item in embeddings], dtype=float)
            labels = fclusterdata(
                vectors,
                t=self.settings.discovery.proximity_clustering_threshold,
                criterion="distance",
                metric="cosine",
                method="average",
            )
            distances = cdist(vectors, vectors, metric="cosine")
        except ModuleNotFoundError:
            labels, distances = _fallback_labels_and_distances(
                [item["vector"] for item in embeddings],
                self.settings.discovery.proximity_clustering_threshold,
            )
        clusters = self._build_clusters(session_id, workspace_id, embeddings, labels, distances)
        status = (
            "saturated" if any(c.classification == "over_explored" for c in clusters) else "normal"
        )
        return ProximityComputationResult(
            status=status,
            clusters=clusters,
            landscape_context={
                "status": status,
                "gap_descriptions": [
                    cluster.centroid_description
                    for cluster in clusters
                    if cluster.classification == "gap"
                ],
            },
        )

    def _build_clusters(
        self,
        session_id: UUID | None,
        workspace_id: UUID,
        embeddings: list[dict[str, Any]],
        labels: Any,
        distances: Any,
    ) -> list[HypothesisCluster]:
        clusters: list[HypothesisCluster] = []
        for label in sorted({int(item) for item in labels}):
            indexes = [index for index, item in enumerate(labels) if int(item) == label]
            hypothesis_ids = [
                str(embeddings[index]["payload"]["hypothesis_id"]) for index in indexes
            ]
            density = _average_similarity(distances, indexes)
            classification = (
                "over_explored"
                if len(indexes) >= self.settings.discovery.proximity_over_explored_min_size
                and density >= self.settings.discovery.proximity_over_explored_similarity
                else "normal"
            )
            title = str(embeddings[indexes[0]]["payload"].get("title") or f"cluster_{label}")
            clusters.append(
                HypothesisCluster(
                    session_id=session_id,
                    workspace_id=workspace_id,
                    cluster_label=f"cluster_{label}",
                    centroid_description=title,
                    hypothesis_count=len(indexes),
                    density_metric=density,
                    classification=classification,
                    hypothesis_ids=hypothesis_ids,
                    computed_at=datetime.now(UTC),
                )
            )
        clusters.extend(self._gap_clusters(session_id, workspace_id, embeddings, labels, distances))
        return clusters

    def _gap_clusters(
        self,
        session_id: UUID | None,
        workspace_id: UUID,
        embeddings: list[dict[str, Any]],
        labels: Any,
        distances: Any,
    ) -> list[HypothesisCluster]:
        threshold = self.settings.discovery.proximity_gap_distance_threshold
        gaps: list[HypothesisCluster] = []
        for index, row in enumerate(distances):
            non_zero = [float(value) for value in row if float(value) > 0.0]
            if non_zero and min(non_zero) > threshold:
                hypothesis_id = str(embeddings[index]["payload"]["hypothesis_id"])
                gaps.append(
                    HypothesisCluster(
                        session_id=session_id,
                        workspace_id=workspace_id,
                        cluster_label=f"gap_{index}",
                        centroid_description=f"Potential gap near {hypothesis_id}",
                        hypothesis_count=0,
                        density_metric=0.0,
                        classification="gap",
                        hypothesis_ids=[hypothesis_id],
                        computed_at=datetime.now(UTC),
                    )
                )
        return gaps[:3]


async def proximity_clustering_task(
    clustering: ProximityClustering,
    session_id: UUID,
    workspace_id: UUID,
) -> ProximityComputationResult:
    return await clustering.compute(session_id, workspace_id)


def _average_similarity(distances: Any, indexes: list[int]) -> float:
    try:
        import numpy as np
    except ModuleNotFoundError:
        pairs = [
            float(distances[left][right])
            for left_index, left in enumerate(indexes)
            for right in indexes[left_index + 1 :]
        ]
        if not pairs:
            return 1.0
        return 1.0 - (sum(pairs) / len(pairs))

    if len(indexes) < 2:
        return 1.0
    submatrix = distances[np.ix_(indexes, indexes)]
    upper = submatrix[np.triu_indices_from(submatrix, k=1)]
    if upper.size == 0:
        return 1.0
    return float(1.0 - np.mean(upper))


def _fallback_labels_and_distances(
    vectors: list[list[float]],
    threshold: float,
) -> tuple[list[int], list[list[float]]]:
    distances = [[_cosine_distance(left, right) for right in vectors] for left in vectors]
    labels: list[int] = []
    centroids: list[list[float]] = []
    for vector in vectors:
        assigned = None
        for index, centroid in enumerate(centroids):
            if _cosine_distance(vector, centroid) <= threshold:
                assigned = index + 1
                break
        if assigned is None:
            centroids.append(vector)
            assigned = len(centroids)
        labels.append(assigned)
    return labels, distances


def _cosine_distance(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return 1.0
    return float(1.0 - dot / (left_norm * right_norm))
