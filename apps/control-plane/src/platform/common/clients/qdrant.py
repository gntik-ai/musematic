from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from platform.common.config import PlatformSettings, Settings
from platform.common.config import settings as default_settings
from platform.common.exceptions import QdrantError
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class PointStruct:
    id: str | int
    vector: list[float]
    payload: dict[str, Any]


def workspace_filter(workspace_id: str, extra: Any | None = None) -> Any:
    try:
        models = import_module("qdrant_client.models")
    except ModuleNotFoundError:
        must: list[Any] = [{"key": "workspace_id", "match": {"value": workspace_id}}]
        if extra is not None:
            must.extend(_filter_values(extra, "must"))
            return {
                "must": must,
                "should": _filter_values(extra, "should"),
                "must_not": _filter_values(extra, "must_not"),
            }
        return {"must": must}

    native_must = [
        models.FieldCondition(
            key="workspace_id",
            match=models.MatchValue(value=workspace_id),
        )
    ]
    if extra is not None:
        native_must.extend(_filter_values(extra, "must"))
        return models.Filter(
            must=native_must,
            should=_filter_values(extra, "should"),
            must_not=_filter_values(extra, "must_not"),
        )
    return models.Filter(must=native_must)


def _filter_values(filter_obj: Any, field: str) -> list[Any]:
    if isinstance(filter_obj, dict):
        return list(filter_obj.get(field, []) or [])
    return list(getattr(filter_obj, field, []) or [])


class AsyncQdrantClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self._client: Any | None = None

    @classmethod
    def from_settings(cls, settings: PlatformSettings) -> AsyncQdrantClient:
        return cls(settings)

    async def connect(self) -> None:
        if self._client is not None:
            return
        qdrant_module = import_module("qdrant_client")
        client_cls = qdrant_module.AsyncQdrantClient
        self._client = client_cls(
            url=self.settings.QDRANT_URL,
            api_key=self.settings.QDRANT_API_KEY or None,
            prefer_grpc=True,
            grpc_port=self.settings.QDRANT_GRPC_PORT,
        )

    async def close(self) -> None:
        if self._client is None:
            return
        close = getattr(self._client, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result
        self._client = None

    async def health_check(self) -> bool:
        try:
            client = await self._ensure_client()
            await client.get_collections()
            return True
        except Exception:
            return False

    async def upsert_vectors(
        self,
        collection: str,
        points: list[dict[str, Any]] | list[PointStruct],
    ) -> None:
        models = import_module("qdrant_client.models")
        normalized = [
            models.PointStruct(
                id=point.id if isinstance(point, PointStruct) else point["id"],
                vector=point.vector if isinstance(point, PointStruct) else point["vector"],
                payload=(
                    point.payload
                    if isinstance(point, PointStruct)
                    else point.get("payload", {})
                ),
            )
            for point in points
        ]
        client = await self._ensure_client()
        await client.upsert(collection_name=collection, points=normalized, wait=True)

    async def search_vectors(
        self,
        collection: str,
        query_vector: list[float],
        limit: int,
        filter: dict[str, Any] | Any | None = None,
    ) -> list[dict[str, Any]]:
        client = await self._ensure_client()
        results = await client.search(
            collection_name=collection,
            query_vector=query_vector,
            query_filter=filter,
            limit=limit,
            with_payload=True,
        )
        return [
            {
                "id": cast(str | int, item.id),
                "score": float(item.score),
                "payload": cast(dict[str, Any], item.payload or {}),
            }
            for item in results
        ]

    async def create_collection(self, collection: str, vector_size: int, distance: str) -> None:
        client = await self._ensure_client()
        models = import_module("qdrant_client.models")
        distance_enum = getattr(models.Distance, distance.upper(), None)
        if distance_enum is None:
            raise QdrantError(f"Unsupported Qdrant distance metric: {distance}")
        await client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(size=vector_size, distance=distance_enum),
        )

    async def create_collection_if_not_exists(
        self,
        collection: str,
        vectors_config: Any,
        hnsw_config: Any | None = None,
        replication_factor: int = 1,
        on_disk_payload: bool = False,
    ) -> bool:
        client = await self._ensure_client()
        try:
            await client.get_collection(collection_name=collection)
            return False
        except Exception:
            await client.create_collection(
                collection_name=collection,
                vectors_config=vectors_config,
                hnsw_config=hnsw_config,
                replication_factor=replication_factor,
                on_disk_payload=on_disk_payload,
            )
            return True

    async def create_payload_index(
        self,
        *,
        collection: str,
        field_name: str,
        field_schema: Any,
    ) -> None:
        client = await self._ensure_client()
        try:
            await client.create_payload_index(
                collection_name=collection,
                field_name=field_name,
                field_schema=field_schema,
                wait=True,
            )
        except Exception:
            return

    async def delete_points(self, collection: str, point_ids: list[str | int]) -> None:
        client = await self._ensure_client()
        models = import_module("qdrant_client.models")
        await client.delete(
            collection_name=collection,
            points_selector=models.PointIdsList(points=point_ids),
            wait=True,
        )

    async def _ensure_client(self) -> Any:
        await self.connect()
        assert self._client is not None
        return self._client
