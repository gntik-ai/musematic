# Contract: Python OpenSearch Client

**Feature**: 008-opensearch-full-text-search  
**Date**: 2026-04-10  
**Type**: Interface Contract  
**Location**: `apps/control-plane/src/platform/common/clients/opensearch.py`

---

## 1. Overview

`AsyncOpenSearchClient` is the single async wrapper around `opensearch-py 2.x` (`AsyncOpenSearch`) used by all platform services. It enforces:
- Workspace-scoped queries (workspace_id filter is mandatory for search methods)
- Typed return models (no raw dicts returned to callers)
- Uniform exception hierarchy
- Connection lifecycle management (lifespan hook in FastAPI app)

---

## 2. Constructor

```python
AsyncOpenSearchClient(
    hosts: list[str],                   # e.g., ["http://musematic-opensearch:9200"]
    http_auth: tuple[str, str] | None,  # (username, password); None disables auth (dev)
    use_ssl: bool = False,              # True in production
    verify_certs: bool = False,         # True if CA cert provided
    ca_certs: str | None = None,        # Path to CA cert PEM file
    timeout: int = 30,                  # Request timeout in seconds
)
```

**Dependency injection** (FastAPI):
```python
# In common/dependencies.py
async def get_opensearch_client() -> AsyncOpenSearchClient:
    return request.app.state.opensearch_client
```

---

## 3. Methods

### 3.1 `index_document`

```python
async def index_document(
    self,
    index: str,
    document: dict,
    document_id: str | None = None,
    refresh: bool = False,
) -> str
```

- Index a single document. If `document_id` is omitted, OpenSearch auto-generates one.
- Returns the document ID.
- `refresh=True` forces index refresh (use only in tests).
- Raises `OpenSearchIndexError` on mapping conflict or cluster error.

---

### 3.2 `bulk_index`

```python
async def bulk_index(
    self,
    index: str,
    documents: list[dict],
    id_field: str = "agent_id",
    refresh: bool = False,
) -> BulkIndexResult
```

- Bulk index using the OpenSearch Bulk API.
- `id_field` specifies which field in each document to use as `_id`.
- Partial failures are captured in `BulkIndexResult.errors` — does not raise on partial failure.
- Raises `OpenSearchIndexError` only on total failure (cluster unavailable, etc.).

---

### 3.3 `search`

```python
async def search(
    self,
    index: str,
    query: dict,
    workspace_id: str,
    filters: list[dict] | None = None,
    aggregations: dict | None = None,
    from_: int = 0,
    size: int = 10,
    sort: list[dict] | None = None,
) -> SearchResult
```

- Execute a full-text search. `workspace_id` is **always** injected as a `term` filter.
- `query` is the OpenSearch Query DSL dict (e.g., `multi_match` or `bool`).
- `filters` are additional `term`/`range`/`terms` filters appended to the `bool.filter` clause.
- `aggregations` is the OpenSearch aggregations DSL dict.
- `size` is capped at 10,000 (OpenSearch default `max_result_window`).
- Returns `SearchResult` with typed hits, total, aggregations, took_ms.
- Raises `OpenSearchQueryError` on query parse error or cluster error.

---

### 3.4 `search_after`

```python
async def search_after(
    self,
    index: str,
    query: dict,
    workspace_id: str,
    sort: list[dict],
    search_after: list | None = None,
    size: int = 10,
) -> SearchResult
```

- Deep pagination using the `search_after` cursor (avoids `from` + `size` limit).
- `sort` must include a tiebreaker field (e.g., `_id`) for stable ordering.
- `search_after` is the sort values from the last hit of the previous page.
- `SearchResult.search_after` contains the cursor for the next page (or `None` if no more results).

---

### 3.5 `delete_document`

```python
async def delete_document(
    self,
    index: str,
    document_id: str,
) -> bool
```

- Delete a document by ID.
- Returns `True` if deleted, `False` if document not found.
- Raises `OpenSearchIndexError` on cluster error.

---

### 3.6 `delete_by_query`

```python
async def delete_by_query(
    self,
    index: str,
    query: dict,
    workspace_id: str,
) -> int
```

- Delete all documents matching `query` scoped to `workspace_id`.
- Returns count of deleted documents.
- Raises `OpenSearchQueryError` on failure.

---

### 3.7 `health_check`

```python
async def health_check(self) -> ClusterHealth
```

- Returns current cluster health.
- Does not raise on degraded health — callers interpret `ClusterHealth.status`.
- Raises `OpenSearchConnectionError` if the cluster is unreachable.

---

### 3.8 `close`

```python
async def close(self) -> None
```

- Closes the connection pool. Called in the FastAPI `lifespan` shutdown hook.

---

## 4. Return Types

```python
@dataclass
class SearchResult:
    hits: list[dict]           # Raw _source documents
    total: int                 # Total matching documents
    aggregations: dict | None  # Aggregation buckets (None if not requested)
    took_ms: int               # Query execution time in milliseconds
    search_after: list | None  # Cursor for deep pagination (None if no more pages)

@dataclass
class BulkIndexResult:
    indexed: int          # Successfully indexed document count
    failed: int           # Failed document count
    errors: list[dict]    # Per-document error details for failed documents

@dataclass
class ClusterHealth:
    status: str           # "green" | "yellow" | "red"
    nodes: int            # Active node count
    active_shards: int    # Total active primary + replica shards
    relocating_shards: int
```

---

## 5. Exception Hierarchy

```python
class OpenSearchClientError(Exception):
    """Base class for all OpenSearch client errors."""

class OpenSearchConnectionError(OpenSearchClientError):
    """Cluster is unreachable or connection timed out."""

class OpenSearchIndexError(OpenSearchClientError):
    """Document indexing failed (mapping conflict, cluster error)."""

class OpenSearchQueryError(OpenSearchClientError):
    """Query execution failed (parse error, shard failure)."""
```

---

## 6. Workspace Isolation Guarantee

`workspace_id` is injected as a **mandatory `bool.filter` term** in all `search` and `delete_by_query` calls. The implementation wraps the caller's query:

```python
{
  "bool": {
    "must": [caller_query],
    "filter": [
      {"term": {"workspace_id": workspace_id}},
      *additional_filters,
    ]
  }
}
```

No search method returns documents from a different workspace. Callers cannot override or skip the workspace filter. This guarantees SC-006 (100% tenant isolation).

---

## 7. Configuration via Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENSEARCH_HOSTS` | Comma-separated host URLs | `http://localhost:9200` |
| `OPENSEARCH_USERNAME` | Admin username | `admin` |
| `OPENSEARCH_PASSWORD` | Admin password (from Secret) | — |
| `OPENSEARCH_USE_SSL` | Enable TLS | `false` |
| `OPENSEARCH_VERIFY_CERTS` | Verify TLS certificates | `false` |
| `OPENSEARCH_CA_CERTS` | Path to CA certificate | — |
| `OPENSEARCH_TIMEOUT` | Request timeout (seconds) | `30` |

All variables are read via `common/config.py` (Pydantic `Settings`).

---

## 8. Integration Test Pattern

```python
# tests/integration/test_opensearch_basic.py
@pytest.fixture
async def opensearch_client(opensearch_container):
    client = AsyncOpenSearchClient(
        hosts=[opensearch_container.get_connection_url()],
        http_auth=None,  # security disabled in test container
        use_ssl=False,
    )
    yield client
    await client.close()

async def test_index_and_search(opensearch_client, init_templates):
    await opensearch_client.index_document(
        "marketplace-agents-000001",
        {"agent_id": "a1", "name": "Summarizer Bot", "workspace_id": "ws-1", ...},
        document_id="a1",
        refresh=True,
    )
    result = await opensearch_client.search(
        "marketplace-agents-000001",
        query={"match": {"description": "summarizer"}},
        workspace_id="ws-1",
    )
    assert result.total == 1
    assert result.hits[0]["agent_id"] == "a1"
```
