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


class AsyncOpenSearchClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self._client: Any | None = None

    @classmethod
    def from_settings(cls, settings: PlatformSettings) -> AsyncOpenSearchClient:
        return cls(settings)

    async def connect(self) -> None:
        if self._client is not None:
            return
        opensearch_module = import_module("opensearchpy")
        client_cls = opensearch_module.AsyncOpenSearch
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

    async def health_check(self) -> bool:
        try:
            client = await self._ensure_client()
            await client.cluster.health()
            return True
        except Exception:
            return False

    async def index(self, index: str, doc_id: str, body: dict[str, Any]) -> None:
        client = await self._ensure_client()
        try:
            await client.index(index=index, id=doc_id, body=body)
        except Exception as exc:
            raise OpenSearchIndexError(str(exc)) from exc

    async def search(self, index: str, query: dict[str, Any], size: int = 10) -> dict[str, Any]:
        client = await self._ensure_client()
        try:
            return cast(
                dict[str, Any],
                await client.search(index=index, body={"query": query, "size": size}),
            )
        except Exception as exc:
            raise OpenSearchQueryError(str(exc)) from exc

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
        workspace_id: str | None = None,
    ) -> int:
        client = await self._ensure_client()
        payload: dict[str, Any] = {"query": query}
        if workspace_id is not None:
            payload["query"] = {
                "bool": {
                    "must": [query],
                    "filter": [{"term": {"workspace_id": workspace_id}}],
                }
            }
        try:
            response = await client.delete_by_query(index=index, body=payload)
        except Exception as exc:
            raise OpenSearchIndexError(str(exc)) from exc
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
    def _parse_hosts(value: str) -> list[str]:
        return [host.strip() for host in value.split(",") if host.strip()]


async def check_opensearch(settings: Settings | None = None) -> dict[str, Any]:
    client = AsyncOpenSearchClient.from_settings(settings or default_settings)
    try:
        healthy = await client.health_check()
    finally:
        await client.close()
    return {"service": "opensearch", "status": "healthy" if healthy else "unhealthy"}
