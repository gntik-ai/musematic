from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from importlib import import_module
from typing import Any, cast
from urllib import error, request

from platform.common.config import Settings, settings as default_settings
from platform.common.exceptions import QdrantError


@dataclass(frozen=True, slots=True)
class PointStruct:
    id: str | int
    vector: list[float]
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ScoredPoint:
    id: str | int
    score: float
    payload: dict[str, Any]
    version: int


@dataclass(frozen=True, slots=True)
class CollectionInfo:
    name: str
    vectors_count: int
    status: str
    config: dict[str, Any]


def workspace_filter(workspace_id: str, extra: Any | None = None) -> Any:
    models = import_module("qdrant_client.models")
    must = [
        models.FieldCondition(
            key="workspace_id",
            match=models.MatchValue(value=workspace_id),
        )
    ]
    if extra is not None:
        must.extend(list(getattr(extra, "must", []) or []))
        return models.Filter(
            must=must,
            should=list(getattr(extra, "should", []) or []),
            must_not=list(getattr(extra, "must_not", []) or []),
        )
    return models.Filter(must=must)


class AsyncQdrantClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        qdrant_module = import_module("qdrant_client")
        client_cls = getattr(qdrant_module, "AsyncQdrantClient")
        self._client: Any = client_cls(
            url=self.settings.QDRANT_URL,
            api_key=self.settings.QDRANT_API_KEY or None,
            prefer_grpc=True,
            grpc_port=self.settings.QDRANT_GRPC_PORT,
        )

    async def upsert_vectors(self, collection: str, points: list[PointStruct], wait: bool = True) -> None:
        try:
            models = import_module("qdrant_client.models")
            qdrant_points = [
                models.PointStruct(id=point.id, vector=point.vector, payload=point.payload)
                for point in points
            ]
            await self._client.upsert(collection_name=collection, points=qdrant_points, wait=wait)
        except Exception as exc:
            raise QdrantError(f"Failed to upsert vectors into collection '{collection}': {exc}") from exc

    async def search_vectors(
        self,
        collection: str,
        query_vector: list[float],
        filter: Any | None = None,
        limit: int = 10,
        with_payload: bool = True,
        score_threshold: float | None = None,
    ) -> list[ScoredPoint]:
        try:
            results = await self._client.search(
                collection_name=collection,
                query_vector=query_vector,
                query_filter=filter,
                limit=limit,
                with_payload=with_payload,
                score_threshold=score_threshold,
            )
        except Exception as exc:
            raise QdrantError(f"Failed to search vectors in collection '{collection}': {exc}") from exc

        return [
            ScoredPoint(
                id=cast(str | int, result.id),
                score=float(result.score),
                payload=cast(dict[str, Any], result.payload or {}),
                version=int(getattr(result, "version", 0) or 0),
            )
            for result in results
        ]

    async def delete_vectors(self, collection: str, point_ids: list[str | int]) -> None:
        try:
            models = import_module("qdrant_client.models")
            selector = models.PointIdsList(points=point_ids)
            await self._client.delete(collection_name=collection, points_selector=selector)
        except Exception as exc:
            raise QdrantError(f"Failed to delete vectors from collection '{collection}': {exc}") from exc

    async def get_collection_info(self, collection: str) -> CollectionInfo:
        try:
            info = await self._client.get_collection(collection_name=collection)
        except Exception as exc:
            raise QdrantError(f"Failed to get collection info for '{collection}': {exc}") from exc

        return CollectionInfo(
            name=collection,
            vectors_count=int(getattr(info, "vectors_count", 0) or 0),
            status=str(getattr(info, "status", "unknown")),
            config=self._to_dict(info.config) if getattr(info, "config", None) is not None else {},
        )

    async def health_check(self) -> dict[str, Any]:
        collections: list[str] = []
        try:
            response = await self._client.get_collections()
            collections = [item.name for item in getattr(response, "collections", [])]
            status = await asyncio.to_thread(self._fetch_healthz)
            return {"status": status, "collections": collections}
        except Exception as exc:
            return {"status": "error", "error": str(exc), "collections": collections}

    async def create_collection_if_not_exists(
        self,
        collection: str,
        vectors_config: Any,
        hnsw_config: Any | None = None,
        replication_factor: int = 1,
        on_disk_payload: bool = False,
    ) -> bool:
        try:
            await self._client.get_collection(collection_name=collection)
            return False
        except Exception:
            pass

        try:
            await self._client.create_collection(
                collection_name=collection,
                vectors_config=vectors_config,
                hnsw_config=hnsw_config,
                replication_factor=replication_factor,
                on_disk_payload=on_disk_payload,
            )
            return True
        except Exception as exc:
            raise QdrantError(f"Failed to create collection '{collection}': {exc}") from exc

    async def create_payload_index(self, collection: str, field_name: str, field_type: Any) -> None:
        try:
            await self._client.create_payload_index(
                collection_name=collection,
                field_name=field_name,
                field_schema=field_type,
            )
        except Exception as exc:
            raise QdrantError(
                f"Failed to create payload index '{field_name}' on collection '{collection}': {exc}"
            ) from exc

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            result = close()
            if asyncio.iscoroutine(result):
                await result

    async def __aenter__(self) -> "AsyncQdrantClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    def _fetch_healthz(self) -> str:
        url = f"{self.settings.QDRANT_URL.rstrip('/')}/healthz"
        headers = {}
        if self.settings.QDRANT_API_KEY:
            headers["Authorization"] = f"api-key {self.settings.QDRANT_API_KEY}"
        req = request.Request(url, headers=headers)
        try:
            with request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode())
        except error.HTTPError as exc:
            raise QdrantError(f"Qdrant health check failed with HTTP {exc.code}") from exc
        except Exception as exc:
            raise QdrantError(f"Qdrant health check failed: {exc}") from exc
        return str(payload.get("status", "ok"))

    def _to_dict(self, value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return cast(dict[str, Any], value.model_dump())
        if hasattr(value, "dict"):
            return cast(dict[str, Any], value.dict())
        return cast(dict[str, Any], value)
