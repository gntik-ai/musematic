# Contract: Python ClickHouse Async Client

**Feature**: 007-clickhouse-analytics  
**Date**: 2026-04-10  
**Type**: Python library interface contract

---

## Overview

`AsyncClickHouseClient` is the platform's analytics database client, located at `apps/control-plane/src/platform/common/clients/clickhouse.py`. It wraps `clickhouse-connect 0.8+` (HTTP interface) and provides workspace-scoped query execution, batch inserts, and a `BatchBuffer` utility for efficient event ingestion from Kafka consumers.

---

## Configuration

```python
# apps/control-plane/src/platform/common/config.py (additions)
class Settings(BaseSettings):
    CLICKHOUSE_URL: str | None = None          # e.g., "http://musematic-clickhouse.platform-data:8123"
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str = ""              # from Secret: clickhouse-credentials
    CLICKHOUSE_DATABASE: str = "default"
    CLICKHOUSE_INSERT_BATCH_SIZE: int = 1000   # BatchBuffer max size
    CLICKHOUSE_INSERT_FLUSH_INTERVAL: float = 5.0  # BatchBuffer flush interval (seconds)
```

**No local mode fallback**: ClickHouse has no local mode. If `CLICKHOUSE_URL` is not set, the client raises `ClickHouseConnectionError`.

---

## AsyncClickHouseClient API

### Constructor

```python
client = AsyncClickHouseClient(settings: Settings)
# Raises ClickHouseConnectionError if CLICKHOUSE_URL is not set
# Initializes clickhouse-connect client lazily on first use
```

### `execute_query`

```python
async def execute_query(
    sql: str,
    params: dict[str, Any] = {},
) -> list[dict[str, Any]]
```

Execute a SELECT query. Returns rows as a list of dicts (column name → value). Parameters use ClickHouse `{name:Type}` placeholder syntax.

**Raises**: `ClickHouseQueryError` on query execution failure.

---

### `execute_command`

```python
async def execute_command(
    sql: str,
    params: dict[str, Any] = {},
) -> None
```

Execute a DDL or DML command (CREATE, ALTER, INSERT single row). No return value.

**Raises**: `ClickHouseQueryError` on execution failure.

---

### `insert_batch`

```python
async def insert_batch(
    table: str,
    data: list[dict[str, Any]],
    column_names: list[str],
) -> None
```

Batch insert rows using `clickhouse-connect`'s native columnar protocol. `data` is a list of row dicts, `column_names` specifies the column order. This is the primary insertion method — individual row inserts should use `execute_command` only for one-off operations.

**Raises**: `ClickHouseQueryError` on insert failure (e.g., schema mismatch, type error).

---

### `health_check`

```python
async def health_check() -> dict[str, Any]
```

Returns:
```python
{
    "status": "ok" | "error",
    "version": "24.x.x",
    "uptime_seconds": 12345,
    "error": "...",              # error mode only
}
```

---

### `close`

```python
async def close() -> None
```

Closes the underlying HTTP connection pool. Call on application shutdown.

---

## BatchBuffer API

```python
buffer = BatchBuffer(
    client=client,
    table="usage_events",
    column_names=["event_id", "workspace_id", ...],
    max_size=1000,            # flush when buffer reaches this size
    flush_interval=5.0,       # flush every N seconds regardless of size
)
```

### `add`

```python
async def add(row: dict[str, Any]) -> None
```

Add a row to the buffer. If the buffer reaches `max_size`, an automatic flush occurs.

### `flush`

```python
async def flush() -> None
```

Manually flush all buffered rows via `client.insert_batch()`. No-op if buffer is empty.

### `start`

```python
async def start() -> None
```

Start the background flush timer (`asyncio.Task`). The timer calls `flush()` every `flush_interval` seconds.

### `stop`

```python
async def stop() -> None
```

Stop the background flush timer and flush any remaining buffered rows.

---

## Exception Hierarchy

```
ClickHouseClientError(Exception)
├── ClickHouseConnectionError   # HTTP connectivity failure or CLICKHOUSE_URL not set
└── ClickHouseQueryError        # Query execution error (syntax, timeout, type mismatch)
```

---

## Usage Example

```python
from platform.common.clients.clickhouse import AsyncClickHouseClient, BatchBuffer
from platform.common.config import Settings

settings = Settings(
    CLICKHOUSE_URL="http://musematic-clickhouse.platform-data:8123",
    CLICKHOUSE_PASSWORD="<password>",
)

async def main():
    client = AsyncClickHouseClient(settings)

    # Single query
    rows = await client.execute_query(
        "SELECT agent_id, sum(input_tokens) AS total "
        "FROM usage_events "
        "WHERE workspace_id = {ws_id:UUID} "
        "AND event_time >= {start:DateTime64(3)} "
        "GROUP BY agent_id",
        params={"ws_id": "...", "start": "2026-04-01 00:00:00.000"},
    )
    for row in rows:
        print(f"Agent {row['agent_id']}: {row['total']} tokens")

    # Batch insert with buffer
    buffer = BatchBuffer(
        client=client,
        table="usage_events",
        column_names=[
            "event_id", "workspace_id", "user_id", "agent_id",
            "provider", "model", "input_tokens", "output_tokens",
            "estimated_cost", "event_time",
        ],
    )
    await buffer.start()

    # Add events (auto-flushes at 1000 or every 5s)
    for event in events:
        await buffer.add(event)

    await buffer.stop()   # flushes remaining
    await client.close()
```

---

## Workspace Isolation Convention

Workspace isolation is enforced at the query level — callers must include `WHERE workspace_id = ...` in all queries. The client does NOT inject workspace filters automatically. High-level service methods in downstream bounded contexts should enforce workspace scoping at the service layer, consistent with the Qdrant and Neo4j client patterns.

---

## Partition Pruning Convention

Queries against time-partitioned tables SHOULD include a time-range filter (e.g., `WHERE event_time >= ... AND event_time < ...`) to enable partition pruning. The client logs a warning if a query against a known partitioned table lacks a time filter. Callers can verify partition pruning via `EXPLAIN` output.
