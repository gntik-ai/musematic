# Contract: Python Neo4j Async Client

**Feature**: 006-neo4j-knowledge-graph  
**Date**: 2026-04-09  
**Type**: Python library interface contract

---

## Overview

`AsyncNeo4jClient` is the platform's async graph database client, located at `apps/control-plane/src/platform/common/clients/neo4j.py`. It wraps the `neo4j-python-driver 5.x` async driver and provides workspace-scoped graph operations. In local mode (no `NEO4J_URL` configured), all methods transparently route to a PostgreSQL CTE fallback.

---

## Configuration

```python
# apps/control-plane/src/platform/common/config.py (additions)
class Settings(BaseSettings):
    NEO4J_URL: str | None = None   # e.g., "bolt://neo4j:password@musematic-neo4j.platform-data:7687"
    NEO4J_MAX_CONNECTION_POOL_SIZE: int = 50
    GRAPH_MODE: str = "auto"       # "auto" | "neo4j" | "local"
```

**Mode resolution** (when `GRAPH_MODE=auto`):
- `NEO4J_URL` is set → `neo4j` mode (uses `AsyncGraphDatabase.driver()`)
- `NEO4J_URL` is unset → `local` mode (uses PostgreSQL CTE fallback)

---

## AsyncNeo4jClient API

### Constructor

```python
client = AsyncNeo4jClient(settings: Settings)
# Initializes driver lazily on first use; no network call at construction time
```

### `run_query`

```python
async def run_query(
    cypher: str,
    params: dict = {},
    workspace_id: str | None = None,
) -> list[dict[str, Any]]
```

Execute arbitrary Cypher. If `workspace_id` is provided, it is available as `$workspace_id` in the query params. The caller is responsible for including workspace filter clauses in the Cypher string.

**Raises**: `Neo4jClientError` on driver-level errors.

---

### `create_node`

```python
async def create_node(
    label: str,
    properties: dict[str, Any],
) -> str
```

Creates a node with the given label and properties. Returns the node's `id` property. `properties` MUST include `id` (UUID string) and `workspace_id`.

**Raises**: `Neo4jConstraintViolationError` if a uniqueness constraint is violated.

---

### `create_relationship`

```python
async def create_relationship(
    from_id: str,
    to_id: str,
    rel_type: str,
    properties: dict[str, Any] = {},
) -> None
```

Creates a directed relationship `(from)-[r:REL_TYPE]->(to)` between two nodes identified by their `id` property. `rel_type` must be a valid relationship type (see data-model.md).

**Raises**: `Neo4jNodeNotFoundError` if either node does not exist.

---

### `traverse_path`

```python
async def traverse_path(
    start_id: str,
    rel_types: list[str],
    max_hops: int,
    workspace_id: str,
) -> list[PathResult]
```

Traverses paths from `start_id` up to `max_hops` hops, following only the specified relationship types. All returned nodes must belong to `workspace_id`. Returns an empty list if no paths exist.

**Local mode constraint**: `max_hops` must be ≤ 3. Raises `HopLimitExceededError` if exceeded.

---

### `shortest_path`

```python
async def shortest_path(
    from_id: str,
    to_id: str,
    rel_types: list[str] = [],
) -> PathResult | None
```

Finds the shortest path (fewest hops) between two nodes. Uses `shortestPath()` Cypher function (or APOC `apoc.algo.dijkstra` for weighted paths). Returns `None` if no path exists. `rel_types` filters which relationship types to traverse (empty = all types).

**Local mode**: Not supported — raises `NotImplementedError` with message `"shortest_path not available in local mode"`.

---

### `health_check`

```python
async def health_check() -> dict[str, Any]
```

Returns:
```python
{
    "status": "ok" | "error",
    "mode": "neo4j" | "local",
    "version": "5.x.x",          # neo4j mode only
    "edition": "community" | "enterprise",  # neo4j mode only
    "error": "...",               # error mode only
}
```

---

### `close`

```python
async def close() -> None
```

Closes the underlying driver connection pool. Call on application shutdown (lifespan hook).

---

## Data Types

### `PathResult`

```python
@dataclass
class PathResult:
    nodes: list[dict[str, Any]]         # ordered node properties
    relationships: list[dict[str, Any]] # ordered relationship properties
    length: int                          # number of hops
```

---

## Exception Hierarchy

```
Neo4jClientError(Exception)
├── Neo4jConstraintViolationError   # Uniqueness/constraint violation
├── Neo4jNodeNotFoundError          # Referenced node does not exist
├── Neo4jConnectionError            # Driver-level connectivity failure
└── HopLimitExceededError           # local mode only: max_hops > 3
```

---

## Usage Example

```python
from platform.common.clients.neo4j import AsyncNeo4jClient
from platform.common.config import Settings

settings = Settings(NEO4J_URL="bolt://neo4j:password@musematic-neo4j.platform-data:7687")
client = AsyncNeo4jClient(settings)

# Create an agent node
agent_id = await client.create_node(
    label="Agent",
    properties={
        "id": "agent-001",
        "workspace_id": "ws-acme",
        "fqn": "acme:research-agent",
        "lifecycle_state": "published",
    },
)

# Traverse all paths up to 3 hops
paths = await client.traverse_path(
    start_id="agent-001",
    rel_types=["DEPENDS_ON", "COORDINATES"],
    max_hops=3,
    workspace_id="ws-acme",
)

# Health check
health = await client.health_check()
assert health["status"] == "ok"
assert health["mode"] == "neo4j"

await client.close()
```

---

## Workspace Isolation Convention

**All** queries that return graph data MUST scope results to a single `workspace_id`. The client does NOT automatically inject workspace filters into arbitrary Cypher in `run_query` — callers must include the filter explicitly. High-level methods (`traverse_path`, `create_node`) enforce workspace scoping internally.

Cross-workspace relationships (where `workspace_id` differs between nodes) are excluded from workspace-scoped queries unless the caller explicitly omits the workspace filter in `run_query`.

---

## Local Mode Fallback

When operating in local mode, all graph data is stored as `graph_nodes` and `graph_edges` tables in PostgreSQL (schema defined separately). The fallback uses SQLAlchemy recursive CTEs:

```python
# Pseudo-CTE for 3-hop traversal
WITH RECURSIVE traverse AS (
    SELECT id, label, properties, 0 AS hops FROM graph_nodes WHERE id = :start_id
    UNION ALL
    SELECT n.id, n.label, n.properties, t.hops + 1
    FROM graph_nodes n
    JOIN graph_edges e ON e.to_id = n.id
    JOIN traverse t ON t.id = e.from_id
    WHERE t.hops < :max_hops
      AND n.properties->>'workspace_id' = :workspace_id
)
SELECT * FROM traverse
```

The same `PathResult` type is returned. Performance is degraded (seconds vs. milliseconds for large graphs). Maximum `max_hops` is 3.
