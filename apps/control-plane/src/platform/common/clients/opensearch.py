from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, cast

from platform.common.config import Settings, settings as default_settings


@dataclass(frozen=True, slots=True)
class SearchResult:
    hits: list[dict[str, Any]]
    total: int
    aggregations: dict[str, Any] | None
    took_ms: int
    search_after: list[Any] | None


@dataclass(frozen=True, slots=True)
class BulkIndexResult:
    indexed: int
    failed: int
    errors: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ClusterHealth:
    status: str
    nodes: int
    active_shards: int
    relocating_shards: int


class OpenSearchClientError(Exception):
    """Base class for all OpenSearch client errors."""


class OpenSearchConnectionError(OpenSearchClientError):
    """Raised when the cluster is unreachable or authentication fails."""


class OpenSearchIndexError(OpenSearchClientError):
    """Raised when indexing or deletion operations fail."""


class OpenSearchQueryError(OpenSearchClientError):
    """Raised when a search or query operation fails."""


class AsyncOpenSearchClient:
    def __init__(
        self,
        hosts: list[str] | None = None,
        http_auth: tuple[str, str] | None = None,
        use_ssl: bool = False,
        verify_certs: bool = False,
        ca_certs: str | None = None,
        timeout: int = 30,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or default_settings
        resolved_hosts = hosts or self._parse_hosts(self.settings.OPENSEARCH_HOSTS)
        resolved_auth = http_auth
        if resolved_auth is None and self.settings.OPENSEARCH_USERNAME and self.settings.OPENSEARCH_PASSWORD:
            resolved_auth = (self.settings.OPENSEARCH_USERNAME, self.settings.OPENSEARCH_PASSWORD)

        opensearch_module = import_module("opensearchpy")
        client_cls = getattr(opensearch_module, "AsyncOpenSearch")
        self._client: Any = client_cls(
            hosts=resolved_hosts,
            http_auth=resolved_auth,
            use_ssl=use_ssl or self.settings.OPENSEARCH_USE_SSL,
            verify_certs=verify_certs or self.settings.OPENSEARCH_VERIFY_CERTS,
            ca_certs=ca_certs or self.settings.OPENSEARCH_CA_CERTS,
            timeout=timeout or self.settings.OPENSEARCH_TIMEOUT,
            ssl_show_warn=False,
        )

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "AsyncOpenSearchClient":
        resolved = settings or default_settings
        auth: tuple[str, str] | None = None
        if resolved.OPENSEARCH_USERNAME and resolved.OPENSEARCH_PASSWORD:
            auth = (resolved.OPENSEARCH_USERNAME, resolved.OPENSEARCH_PASSWORD)
        return cls(
            hosts=cls._parse_hosts(resolved.OPENSEARCH_HOSTS),
            http_auth=auth,
            use_ssl=resolved.OPENSEARCH_USE_SSL,
            verify_certs=resolved.OPENSEARCH_VERIFY_CERTS,
            ca_certs=resolved.OPENSEARCH_CA_CERTS,
            timeout=resolved.OPENSEARCH_TIMEOUT,
            settings=resolved,
        )

    async def index_document(
        self,
        index: str,
        document: dict[str, Any],
        document_id: str | None = None,
        refresh: bool = False,
    ) -> str:
        params: dict[str, Any] = {"index": index, "body": document, "refresh": refresh}
        if document_id is not None:
            params["id"] = document_id
        try:
            response = await self._client.index(**params)
        except Exception as exc:
            raise OpenSearchIndexError(f"Failed to index document into '{index}': {exc}") from exc
        return cast(str, response.get("_id", document_id))

    async def bulk_index(
        self,
        index: str,
        documents: list[dict[str, Any]],
        id_field: str = "agent_id",
        refresh: bool = False,
    ) -> BulkIndexResult:
        if not documents:
            return BulkIndexResult(indexed=0, failed=0, errors=[])

        helpers = import_module("opensearchpy.helpers")
        async_bulk = getattr(helpers, "async_bulk")
        actions: list[dict[str, Any]] = []
        for document in documents:
            action: dict[str, Any] = {"_op_type": "index", "_index": index, "_source": document}
            if id_field in document:
                action["_id"] = document[id_field]
            actions.append(action)

        try:
            indexed, errors = await async_bulk(
                self._client,
                actions,
                refresh=refresh,
                raise_on_error=False,
                raise_on_exception=False,
            )
        except Exception as exc:
            raise OpenSearchIndexError(f"Failed to bulk index documents into '{index}': {exc}") from exc

        typed_errors = [cast(dict[str, Any], error) for error in errors]
        return BulkIndexResult(indexed=int(indexed), failed=len(typed_errors), errors=typed_errors)

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
        body: dict[str, Any] = {
            "query": self._scoped_query(query, workspace_id, filters),
            "from": from_,
            "size": min(size, 10000),
        }
        if aggregations is not None:
            body["aggs"] = aggregations
        if sort is not None:
            body["sort"] = sort
        try:
            response = await self._client.search(index=index, body=body)
        except Exception as exc:
            raise OpenSearchQueryError(f"Failed to search index '{index}': {exc}") from exc
        return self._parse_search_result(response)

    async def search_after(
        self,
        index: str,
        query: dict[str, Any],
        workspace_id: str,
        sort: list[dict[str, Any]],
        search_after: list[Any] | None = None,
        size: int = 10,
    ) -> SearchResult:
        body: dict[str, Any] = {
            "query": self._scoped_query(query, workspace_id),
            "sort": sort,
            "size": min(size, 10000),
        }
        if search_after is not None:
            body["search_after"] = search_after
        try:
            response = await self._client.search(index=index, body=body)
        except Exception as exc:
            raise OpenSearchQueryError(f"Failed to search index '{index}' with search_after: {exc}") from exc
        return self._parse_search_result(response)

    async def delete_document(self, index: str, document_id: str) -> bool:
        try:
            response = await self._client.delete(index=index, id=document_id)
        except Exception as exc:
            if self._status_code(exc) == 404:
                return False
            raise OpenSearchIndexError(f"Failed to delete document '{document_id}' from '{index}': {exc}") from exc
        return cast(str, response.get("result", "")) == "deleted"

    async def delete_by_query(self, index: str, query: dict[str, Any], workspace_id: str) -> int:
        body = {"query": self._scoped_query(query, workspace_id)}
        try:
            response = await self._client.delete_by_query(index=index, body=body, conflicts="proceed", refresh=True)
        except Exception as exc:
            raise OpenSearchQueryError(f"Failed to delete by query in '{index}': {exc}") from exc
        return int(response.get("deleted", 0) or 0)

    async def health_check(self) -> ClusterHealth:
        try:
            response = await self._client.cluster.health()
        except Exception as exc:
            raise OpenSearchConnectionError(f"Failed to contact OpenSearch cluster: {exc}") from exc

        return ClusterHealth(
            status=str(response.get("status", "red")),
            nodes=int(response.get("number_of_nodes", 0) or 0),
            active_shards=int(response.get("active_shards", 0) or 0),
            relocating_shards=int(response.get("relocating_shards", 0) or 0),
        )

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close is None:
            return
        result = close()
        if hasattr(result, "__await__"):
            await result

    def _parse_search_result(self, response: dict[str, Any]) -> SearchResult:
        raw_hits = cast(list[dict[str, Any]], response.get("hits", {}).get("hits", []))
        total = response.get("hits", {}).get("total", 0)
        if isinstance(total, dict):
            total_value = int(total.get("value", 0) or 0)
        else:
            total_value = int(total or 0)
        cursor = cast(list[Any] | None, raw_hits[-1].get("sort") if raw_hits else None)
        return SearchResult(
            hits=[cast(dict[str, Any], hit.get("_source", {})) for hit in raw_hits],
            total=total_value,
            aggregations=cast(dict[str, Any] | None, response.get("aggregations")),
            took_ms=int(response.get("took", 0) or 0),
            search_after=cursor,
        )

    def _scoped_query(
        self,
        query: dict[str, Any],
        workspace_id: str,
        filters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        scoped_filters = [{"term": {"workspace_id": workspace_id}}]
        if filters:
            scoped_filters.extend(filters)
        return {
            "bool": {
                "must": [query],
                "filter": scoped_filters,
            }
        }

    @staticmethod
    def _parse_hosts(value: str) -> list[str]:
        return [host.strip() for host in value.split(",") if host.strip()]

    @staticmethod
    def _status_code(exc: Exception) -> int | None:
        return cast(int | None, getattr(exc, "status_code", getattr(exc, "status", None)))


async def check_opensearch(settings: Settings | None = None) -> dict[str, Any]:
    client = AsyncOpenSearchClient.from_settings(settings)
    try:
        health = await client.health_check()
    except OpenSearchConnectionError as exc:
        return {"service": "opensearch", "status": "error", "error": str(exc)}
    finally:
        await client.close()

    return {
        "service": "opensearch",
        "status": health.status,
        "nodes": health.nodes,
        "active_shards": health.active_shards,
        "relocating_shards": health.relocating_shards,
    }
