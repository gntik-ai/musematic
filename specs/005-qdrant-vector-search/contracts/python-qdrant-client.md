# Contract: Python Qdrant Client

**Feature**: 005-qdrant-vector-search  
**Type**: Python Internal Interface Contract  
**Date**: 2026-04-09  
**Location**: `apps/control-plane/src/platform/common/clients/qdrant.py`

---

## AsyncQdrantClient

```python
class AsyncQdrantClient:
    def __init__(self, settings: Settings) -> None:
        """
        Initialize using QDRANT_URL, QDRANT_API_KEY, QDRANT_GRPC_PORT from Settings.
        Uses qdrant-client 1.12+ with prefer_grpc=True for data operations.
        """

    async def upsert_vectors(
        self,
        collection: str,
        points: list[PointStruct],
        wait: bool = True,
    ) -> None:
        """
        Upsert a batch of vectors with payloads.
        If a point with the same ID already exists, it is overwritten.

        Args:
            collection: Collection name (must be one of the 4 provisioned collections).
            points: List of PointStruct (id, vector, payload). All payloads MUST include workspace_id.
            wait: If True, block until the operation is indexed (default: True for consistency).

        Raises:
            QdrantError: On upsert failure or connection error.
            ValueError: If any point's vector dimension does not match the collection.
        """

    async def search_vectors(
        self,
        collection: str,
        query_vector: list[float],
        filter: Filter | None = None,
        limit: int = 10,
        with_payload: bool = True,
        score_threshold: float | None = None,
    ) -> list[ScoredPoint]:
        """
        Search for nearest neighbors.

        Args:
            collection: Collection name.
            query_vector: Embedding to search with (must match collection dimension).
            filter: Qdrant Filter object for payload filtering.
                    For multi-tenant collections, MUST include workspace_id condition.
            limit: Maximum number of results (default: 10).
            with_payload: Include full payload in results (default: True).
            score_threshold: Minimum similarity score; results below this are excluded.

        Returns:
            List of ScoredPoint sorted by descending score.

        Raises:
            QdrantError: On search failure or connection error.
        """

    async def delete_vectors(
        self,
        collection: str,
        point_ids: list[str | int],
    ) -> None:
        """
        Delete vectors by their point IDs.
        No-op if any ID does not exist.

        Raises:
            QdrantError: On deletion failure.
        """

    async def get_collection_info(self, collection: str) -> CollectionInfo:
        """
        Get collection metadata: vector count, status, configuration.

        Raises:
            QdrantError: If collection does not exist or connection fails.
        """

    async def health_check(self) -> dict[str, Any]:
        """
        Check cluster health and collection availability.
        Returns {"status": "ok", "collections": [...], "vectors_count": {...}}
        or {"status": "error", "error": msg}.
        """

    async def create_collection_if_not_exists(
        self,
        collection: str,
        vectors_config: VectorsConfig,
        hnsw_config: HnswConfigDiff | None = None,
        replication_factor: int = 1,
        on_disk_payload: bool = False,
    ) -> bool:
        """
        Create collection only if it does not already exist.
        Returns True if created, False if already existed.

        Raises:
            QdrantError: On creation failure.
        """

    async def create_payload_index(
        self,
        collection: str,
        field_name: str,
        field_type: PayloadSchemaType,
    ) -> None:
        """
        Create a payload index on a field.
        Idempotent — no error if index already exists.

        Raises:
            QdrantError: On index creation failure.
        """
```

---

## Data Types

```python
@dataclass(frozen=True)
class PointStruct:
    id: str | int
    vector: list[float]
    payload: dict[str, Any]

@dataclass(frozen=True)
class ScoredPoint:
    id: str | int
    score: float
    payload: dict[str, Any]
    version: int

@dataclass(frozen=True)
class CollectionInfo:
    name: str
    vectors_count: int
    status: str           # "green", "yellow", "red"
    config: dict[str, Any]
```

---

## Exception

```python
class QdrantError(Exception): ...
```

---

## Settings Entries

Add to `apps/control-plane/src/platform/common/config.py`:

```python
QDRANT_URL: str = "http://musematic-qdrant.platform-data:6333"
QDRANT_API_KEY: str = ""          # from qdrant-api-key secret
QDRANT_GRPC_PORT: int = 6334      # used with prefer_grpc=True
QDRANT_COLLECTION_DIMENSIONS: int = 768  # configurable per deployment
```

---

## Multi-Tenant Filter Helper

```python
def workspace_filter(workspace_id: str, extra: Filter | None = None) -> Filter:
    """
    Build a mandatory workspace_id filter with optional additional conditions.
    Use this for all searches against multi-tenant collections.

    Example:
        filter = workspace_filter(
            workspace_id="ws-123",
            extra=Filter(must=[FieldCondition(key="lifecycle_state", match=MatchValue(value="published"))])
        )
    """
```

---

## Usage Pattern

```python
from platform.common.clients.qdrant import AsyncQdrantClient, PointStruct, workspace_filter
from platform.common.config import settings

client = AsyncQdrantClient(settings)

# Upsert agent embedding
await client.upsert_vectors(
    "agent_embeddings",
    [PointStruct(
        id=str(agent_id),
        vector=embedding,  # list[float], 768 dims
        payload={
            "workspace_id": str(workspace_id),
            "agent_id": str(agent_id),
            "lifecycle_state": "published",
            "maturity_level": 3,
            "tags": ["nlp", "summarization"],
        }
    )]
)

# Search with workspace scoping (mandatory)
results = await client.search_vectors(
    "agent_embeddings",
    query_vector=query_embedding,
    filter=workspace_filter(
        workspace_id=str(workspace_id),
        extra=Filter(must=[FieldCondition(
            key="lifecycle_state",
            match=MatchValue(value="published")
        )])
    ),
    limit=10,
)

for point in results:
    print(f"{point.id}: {point.score:.3f} — {point.payload['agent_id']}")
```
