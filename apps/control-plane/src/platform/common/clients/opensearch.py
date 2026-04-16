from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from platform.common.config import PlatformSettings, Settings
from platform.common.config import settings as default_settings
from typing import Any, cast


class OpenSearchClientError(Exception):
    """Base class for OpenSearch client errors."""


class OpenSearchConnectionError(OpenSearchClientError):
    """Raised when the cluster is unreachable or authentication fails."""


class OpenSearchIndexError(OpenSearchClientError):
    """Raised when indexing or deletion operations fail."""


class OpenSearchQueryError(OpenSearchClientError):
    """Raised when a search or query operation fails."""


@dataclass(frozen=True, slots=True)
class BulkIndexResult:
    indexed: int
    failed: int
    errors: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class SearchResult:
    hits: list[dict[str, Any]]
    total: int
    aggregations: dict[str, Any] | None
    took_ms: int
    search_after: list[Any] | None


@dataclass(frozen=True, slots=True)
class ClusterHealth:
    status: str
    nodes: int
    active_shards: int
    relocating_shards: int


class AsyncOpenSearchClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self._client: Any | None = None

    @classmethod
    def from_settings(cls, settings: PlatformSettings) -> AsyncOpenSearchClient:
        return cls(settings)

    @staticmethod
    def _client_class() -> Any:
        opensearch_module = import_module("opensearchpy")
        client_cls = getattr(opensearch_module, "AsyncOpenSearch", None)
        if client_cls is not None:
            return client_cls
        return import_module("opensearchpy._async.client").AsyncOpenSearch

    async def connect(self) -> None:
        if self._client is not None:
            return
        client_cls = self._client_class()
        auth: tuple[str, str] | None = None
        if self.settings.OPENSEARCH_USERNAME and self.settings.OPENSEARCH_PASSWORD:
            auth = (self.settings.OPENSEARCH_USERNAME, self.settings.OPENSEARCH_PASSWORD)
        self._client = client_cls(
            hosts=self._parse_hosts(self.settings.OPENSEARCH_HOSTS),
            http_auth=auth,
            use_ssl=self.settings.OPENSEARCH_USE_SSL,
            verify_certs=self.settings.OPENSEARCH_VERIFY_CERTS,
            ca_certs=self.settings.OPENSEARCH_CA_CERTS,
            timeout=self.settings.OPENSEARCH_TIMEOUT,
            ssl_show_warn=False,
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

    async def health_check(self) -> ClusterHealth:
        client = await self._ensure_client()
        try:
            response = cast(dict[str, Any], await client.cluster.health())
        except Exception as exc:
            raise OpenSearchConnectionError(str(exc)) from exc
        return ClusterHealth(
            status=str(response.get("status", "red")),
            nodes=int(response.get("number_of_nodes", 0)),
            active_shards=int(response.get("active_shards", 0)),
            relocating_shards=int(response.get("relocating_shards", 0)),
        )

    async def index(self, index: str, doc_id: str, body: dict[str, Any]) -> None:
        client = await self._ensure_client()
        try:
            await client.index(index=index, id=doc_id, body=body)
        except Exception as exc:
            raise OpenSearchIndexError(str(exc)) from exc

    async def search(
        self,
        index: str,
        query: dict[str, Any],
        workspace_id: str,
        filters: list[dict[str, Any]] | None = None,
        aggregations: dict[str, Any] | None = None,
        from_: int = 0,
        size: int = 10,
        sort: list[dict[str, Any]] | None = None,
    ) -> SearchResult:
        client = await self._ensure_client()
        payload: dict[str, Any] = {
            "query": self._workspace_scoped_query(query, workspace_id, filters),
            "from": max(from_, 0),
            "size": min(max(size, 0), 10_000),
        }
        if aggregations is not None:
            payload["aggs"] = aggregations
        if sort is not None:
            payload["sort"] = sort
        try:
            response = cast(dict[str, Any], await client.search(index=index, body=payload))
        except Exception as exc:
            raise OpenSearchQueryError(str(exc)) from exc
        return self._search_result(response)

    async def search_after(
        self,
        index: str,
        query: dict[str, Any],
        workspace_id: str,
        sort: list[dict[str, Any]],
        search_after: list[Any] | None = None,
        size: int = 10,
    ) -> SearchResult:
        client = await self._ensure_client()
        payload: dict[str, Any] = {
            "query": self._workspace_scoped_query(query, workspace_id),
            "sort": sort,
            "size": min(max(size, 0), 10_000),
        }
        if search_after is not None:
            payload["search_after"] = search_after
        try:
            response = cast(dict[str, Any], await client.search(index=index, body=payload))
        except Exception as exc:
            raise OpenSearchQueryError(str(exc)) from exc
        return self._search_result(response)

    async def bulk(self, operations: list[dict[str, Any]]) -> dict[str, Any]:
        client = await self._ensure_client()
        helpers = import_module("opensearchpy.helpers")
        async_bulk = helpers.async_bulk
        try:
            success, errors = await async_bulk(
                client,
                operations,
                raise_on_error=False,
                raise_on_exception=False,
            )
        except Exception as exc:
            raise OpenSearchIndexError(str(exc)) from exc
        return {"success": int(success), "errors": cast(list[dict[str, Any]], errors)}

    async def delete_by_query(
        self,
        index: str,
        query: dict[str, Any],
        workspace_id: str,
    ) -> int:
        client = await self._ensure_client()
        payload = {"query": self._workspace_scoped_query(query, workspace_id)}
        try:
            response = await client.delete_by_query(index=index, body=payload)
        except Exception as exc:
            raise OpenSearchQueryError(str(exc)) from exc
        return int(response.get("deleted", 0))

    async def index_document(
        self,
        index: str,
        document: dict[str, Any],
        document_id: str | None = None,
        refresh: bool = False,
    ) -> str:
        client = await self._ensure_client()
        params: dict[str, Any] = {"index": index, "body": document, "refresh": refresh}
        if document_id is not None:
            params["id"] = document_id
        try:
            response = await client.index(**params)
        except Exception as exc:
            raise OpenSearchIndexError(str(exc)) from exc
        return cast(str, response.get("_id", document_id))

    async def delete_document(
        self,
        index: str,
        document_id: str,
    ) -> bool:
        client = await self._ensure_client()
        try:
            response = cast(dict[str, Any], await client.delete(index=index, id=document_id))
        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
            if status == 404:
                return False
            raise OpenSearchIndexError(str(exc)) from exc
        return str(response.get("result", "")).lower() == "deleted"

    async def bulk_index(
        self,
        index: str,
        documents: list[dict[str, Any]],
        id_field: str = "id",
        refresh: bool = False,
    ) -> BulkIndexResult:
        operations: list[dict[str, Any]] = []
        for document in documents:
            action: dict[str, Any] = {"_op_type": "index", "_index": index, "_source": document}
            if id_field in document:
                action["_id"] = document[id_field]
            operations.append(action)
        result = await self.bulk(operations)
        del refresh
        return BulkIndexResult(
            indexed=result["success"],
            failed=len(result["errors"]),
            errors=result["errors"],
        )

    async def _ensure_client(self) -> Any:
        await self.connect()
        assert self._client is not None
        return self._client

    @staticmethod
    def _workspace_scoped_query(
        query: dict[str, Any],
        workspace_id: str,
        filters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        scoped_filters: list[dict[str, Any]] = [{"term": {"workspace_id": workspace_id}}]
        if filters:
            scoped_filters.extend(filters)
        return {
            "bool": {
                "must": [query],
                "filter": scoped_filters,
            }
        }

    @staticmethod
    def _search_result(response: dict[str, Any]) -> SearchResult:
        hit_block = cast(dict[str, Any], response.get("hits", {}))
        raw_hits = cast(list[dict[str, Any]], hit_block.get("hits", []))
        documents: list[dict[str, Any]] = []
        next_cursor: list[Any] | None = None
        for hit in raw_hits:
            document = dict(cast(dict[str, Any], hit.get("_source", {})))
            if "_id" not in document and hit.get("_id") is not None:
                document["_id"] = hit["_id"]
            documents.append(document)
            if hit.get("sort") is not None:
                next_cursor = cast(list[Any], hit["sort"])
        total = hit_block.get("total", 0)
        if isinstance(total, dict):
            total_value = int(total.get("value", 0))
        else:
            total_value = int(total)
        return SearchResult(
            hits=documents,
            total=total_value,
            aggregations=cast(dict[str, Any] | None, response.get("aggregations")),
            took_ms=int(response.get("took", 0)),
            search_after=next_cursor,
        )

    @staticmethod
    def _parse_hosts(value: str) -> list[str]:
        return [host.strip() for host in value.split(",") if host.strip()]


async def check_opensearch(settings: Settings | None = None) -> dict[str, Any]:
    client = AsyncOpenSearchClient.from_settings(settings or default_settings)
    try:
        health = await client.health_check()
    finally:
        await client.close()
    return {
        "service": "opensearch",
        "status": "healthy" if health.status in {"green", "yellow"} else "unhealthy",
        "details": {
            "status": health.status,
            "nodes": health.nodes,
            "active_shards": health.active_shards,
            "relocating_shards": health.relocating_shards,
        },
    }
