from __future__ import annotations

import math
from difflib import SequenceMatcher
from importlib import import_module
from platform.common.clients.qdrant import AsyncQdrantClient, PointStruct
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.evaluation.scorers.base import ScoreResult
from typing import Any
from uuid import uuid4

import httpx

EVALUATION_EMBEDDINGS_COLLECTION = "evaluation_embeddings"


class SemanticSimilarityScorer:
    def __init__(
        self,
        *,
        settings: PlatformSettings | None = None,
        qdrant: AsyncQdrantClient | None = None,
        collection_name: str = EVALUATION_EMBEDDINGS_COLLECTION,
    ) -> None:
        self.settings = settings or default_settings
        self.qdrant = qdrant or AsyncQdrantClient.from_settings(self.settings)
        self.collection_name = collection_name
        self._collection_ready = False

    async def score(self, actual: str, expected: str, config: dict[str, Any]) -> ScoreResult:
        threshold = float(config.get("threshold", 0.8))
        try:
            await self.ensure_collection()
            actual_embedding = await self._embed_text(actual)
            expected_embedding = await self._embed_text(expected)
            similarity = self._cosine_similarity(actual_embedding, expected_embedding)
            await self._store_embeddings(actual_embedding, expected_embedding)
            return ScoreResult(
                score=similarity,
                passed=similarity >= threshold,
                rationale="semantic similarity computed from embeddings",
                extra={"threshold": threshold, "collection": self.collection_name},
            )
        except Exception as exc:
            fallback = SequenceMatcher(None, actual, expected).ratio()
            return ScoreResult(
                score=fallback,
                passed=fallback >= threshold,
                rationale=f"semantic scorer fallback used: {exc}",
                error="semantic_similarity_fallback",
                extra={"threshold": threshold, "fallback": True},
            )

    async def ensure_collection(self) -> None:
        if self._collection_ready:
            return
        models = import_module("qdrant_client.models")
        await self.qdrant.create_collection_if_not_exists(
            collection=self.collection_name,
            vectors_config=models.VectorParams(
                size=self.settings.memory.embedding_dimensions,
                distance=models.Distance.COSINE,
            ),
            on_disk_payload=True,
        )
        self._collection_ready = True

    async def _embed_text(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.settings.memory.embedding_api_url,
                json={"input": text, "model": self.settings.memory.embedding_model},
            )
            response.raise_for_status()
        return self._extract_embedding(response.json())

    async def _store_embeddings(
        self,
        actual_embedding: list[float],
        expected_embedding: list[float],
    ) -> None:
        await self.qdrant.upsert_vectors(
            self.collection_name,
            [
                PointStruct(
                    id=str(uuid4()),
                    vector=actual_embedding,
                    payload={"type": "actual"},
                ),
                PointStruct(
                    id=str(uuid4()),
                    vector=expected_embedding,
                    payload={"type": "expected"},
                ),
            ],
        )

    @staticmethod
    def _extract_embedding(payload: dict[str, Any]) -> list[float]:
        if isinstance(payload.get("embedding"), list):
            return [float(item) for item in payload["embedding"]]
        data = payload.get("data")
        if (
            isinstance(data, list)
            and data
            and isinstance(data[0], dict)
            and isinstance(data[0].get("embedding"), list)
        ):
            return [float(item) for item in data[0]["embedding"]]
        raise ValueError("Embedding response missing vector payload")

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            raise ValueError("Embedding vectors must be present and have matching sizes")
        dot = sum(lhs * rhs for lhs, rhs in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return max(0.0, min(1.0, dot / (left_norm * right_norm)))
