from __future__ import annotations

from importlib import import_module
from platform.common.clients.qdrant import AsyncQdrantClient, PointStruct
from platform.common.config import PlatformSettings
from platform.discovery.models import Hypothesis
from platform.discovery.repository import DiscoveryRepository
from typing import Any
from uuid import UUID

import httpx


class HypothesisEmbedder:
    """Compute and store hypothesis embeddings in Qdrant."""

    def __init__(
        self,
        *,
        settings: PlatformSettings,
        qdrant: AsyncQdrantClient | None,
        repository: DiscoveryRepository,
    ) -> None:
        self.settings = settings
        self.qdrant = qdrant
        self.repository = repository

    async def ensure_collection(self) -> None:
        if self.qdrant is None:
            return
        models = import_module("qdrant_client.models")
        await self.qdrant.create_collection_if_not_exists(
            self.settings.discovery.qdrant_collection,
            vectors_config=models.VectorParams(
                size=self.settings.discovery.embedding_vector_size,
                distance=models.Distance.COSINE,
            ),
            hnsw_config=models.HnswConfigDiff(m=16, ef_construct=128, full_scan_threshold=10000),
        )
        for field_name in ("workspace_id", "session_id", "cluster_id", "status"):
            await self.qdrant.create_payload_index(
                collection=self.settings.discovery.qdrant_collection,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

    async def embed_hypothesis(self, hypothesis: Hypothesis) -> list[float]:
        vector = await self._embed_text(f"{hypothesis.title}\n\n{hypothesis.description}")
        if self.qdrant is not None:
            await self.ensure_collection()
            await self.qdrant.upsert_vectors(
                self.settings.discovery.qdrant_collection,
                [
                    PointStruct(
                        id=str(hypothesis.id),
                        vector=vector,
                        payload={
                            "workspace_id": str(hypothesis.workspace_id),
                            "session_id": str(hypothesis.session_id),
                            "hypothesis_id": str(hypothesis.id),
                            "title": hypothesis.title,
                            "cluster_id": hypothesis.cluster_id,
                            "status": hypothesis.status,
                        },
                    )
                ],
            )
        hypothesis.qdrant_point_id = str(hypothesis.id)
        await self.repository.session.flush()
        return vector

    async def fetch_session_embeddings(
        self,
        session_id: UUID,
        workspace_id: UUID,
    ) -> list[dict[str, Any]]:
        return await self.fetch_workspace_embeddings(workspace_id, session_id=session_id)

    async def fetch_workspace_embeddings(
        self,
        workspace_id: UUID,
        *,
        session_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        if self.qdrant is None:
            return []
        client = await self.qdrant._ensure_client()
        models = import_module("qdrant_client.models")
        must = [
            models.FieldCondition(
                key="workspace_id",
                match=models.MatchValue(value=str(workspace_id)),
            ),
            models.FieldCondition(key="status", match=models.MatchValue(value="active")),
        ]
        if session_id is not None:
            must.append(
                models.FieldCondition(
                    key="session_id",
                    match=models.MatchValue(value=str(session_id)),
                )
            )
        query_filter = models.Filter(must=must)
        points, _ = await client.scroll(
            collection_name=self.settings.discovery.qdrant_collection,
            scroll_filter=query_filter,
            limit=1000,
            with_vectors=True,
            with_payload=True,
        )
        return [
            {
                "id": str(point.id),
                "vector": list(point.vector or []),
                "payload": dict(point.payload or {}),
            }
            for point in points
        ]

    async def _embed_text(self, text: str) -> list[float]:
        payload = {"model": self.settings.memory.embedding_model, "input": text}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.settings.memory.embedding_api_url, json=payload)
            response.raise_for_status()
            data = response.json()
        vector = data.get("data", [{}])[0].get("embedding")
        if not isinstance(vector, list):
            raise ValueError("Embedding API response missing data[0].embedding")
        return [float(value) for value in vector]
