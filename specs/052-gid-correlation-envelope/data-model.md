# Data Model: GID Correlation and Event Envelope Extension

**Feature**: 052-gid-correlation-envelope
**Phase**: 1 — Design
**Date**: 2026-04-18
**Brownfield**: Extending shared infrastructure and analytics/log storage. No new business entities.

---

## Existing: CorrelationContext — NO SCHEMA CHANGE

**File**: `apps/control-plane/src/platform/common/events/envelope.py`

```python
class CorrelationContext(BaseModel):
    workspace_id: UUID | None = None
    conversation_id: UUID | None = None
    interaction_id: UUID | None = None
    execution_id: UUID | None = None
    fleet_id: UUID | None = None
    goal_id: UUID | None = None          # ← already present (feature 018/024)
    agent_fqn: str | None = None         # ← added in feature 051
    correlation_id: UUID
```

**Change**: None on the class itself. Behavior change: the `make_envelope()` factory will fall back to a request-scoped ContextVar for `goal_id` when the caller does not provide a correlation context explicitly (see `make_envelope` below).

---

## Modified: `make_envelope()` factory — ContextVar fallback for `goal_id`

**File**: `apps/control-plane/src/platform/common/events/envelope.py`

**Before**:

```python
def make_envelope(
    event_type: str,
    source: str,
    payload: dict[str, Any],
    correlation_context: CorrelationContext | None = None,
    *,
    agent_fqn: str | None = None,
) -> EventEnvelope: ...
```

**After** (signature gains `goal_id`; body gains fallback to `goal_id_var.get()`):

```python
def make_envelope(
    event_type: str,
    source: str,
    payload: dict[str, Any],
    correlation_context: CorrelationContext | None = None,
    *,
    agent_fqn: str | None = None,
    goal_id: UUID | None = None,
) -> EventEnvelope: ...
```

**Semantics** (in priority order):

1. If `correlation_context` is provided and `correlation_context.goal_id` is not `None`, use it unchanged.
2. Else if `goal_id` kwarg is provided, set it on the context (copying the context if one was passed).
3. Else read `goal_id_var.get()` from `common/correlation.py`; if non-empty, parse to UUID and set it on the context.
4. Else leave `goal_id = None`.

---

## Modified: HTTP correlation middleware — `X-Goal-Id` header handling

**File**: `apps/control-plane/src/platform/common/correlation.py`

**New module-level ContextVar**:

```python
goal_id_var: ContextVar[str] = ContextVar("goal_id", default="")
```

**`CorrelationMiddleware.dispatch` gains**:

- Read `request.headers.get("X-Goal-Id", "").strip()`
- If present: validate as UUID string; on failure return `JSONResponse(status_code=422, content={"error": "invalid X-Goal-Id header"})` without calling `call_next`
- If valid: set `goal_id_var`, attach to `request.state.goal_id`, echo as `response.headers["X-Goal-Id"]`
- Reset the ContextVar in the `finally` block alongside `correlation_id_var`

**Validation rule**: Standard UUID v1/v4 string format, 36 characters with hyphens. Empty string is treated as "absent".

---

## Modified: ClickHouse `usage_events` table — new `goal_id` column

**File**: `deploy/clickhouse/init/007-add-goal-id.sql` (NEW)

**DDL (conceptual)**:

```sql
-- Base event table
ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS goal_id Nullable(UUID);

-- Hourly aggregate: recreate with new ORDER BY that includes goal_id
DROP VIEW IF EXISTS usage_hourly_mv;

CREATE TABLE IF NOT EXISTS usage_hourly_v2 (
    workspace_id UUID,
    goal_id Nullable(UUID),
    agent_id UUID,
    provider String,
    model String,
    hour DateTime,
    total_input_tokens UInt64,
    total_output_tokens UInt64,
    total_reasoning_tokens UInt64,
    total_cost Decimal128(6),
    event_count UInt64,
    avg_context_quality Float64
)
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (workspace_id, goal_id, agent_id, provider, model, hour);

CREATE MATERIALIZED VIEW IF NOT EXISTS usage_hourly_mv
TO usage_hourly_v2 AS
SELECT
    workspace_id,
    goal_id,
    agent_id,
    provider,
    model,
    toStartOfHour(event_time) AS hour,
    sum(input_tokens) AS total_input_tokens,
    sum(output_tokens) AS total_output_tokens,
    sum(reasoning_tokens) AS total_reasoning_tokens,
    sum(estimated_cost) AS total_cost,
    count() AS event_count,
    avg(context_quality_score) AS avg_context_quality
FROM usage_events
GROUP BY workspace_id, goal_id, agent_id, provider, model, hour;
```

**Notes**:
- `ALTER ... ADD COLUMN Nullable(UUID)` on `MergeTree` is a metadata-only operation and is safe online.
- The `usage_hourly` original table is retained as-is; the new `usage_hourly_v2` is the forward-compatible aggregate. `AnalyticsRepository` should read from `usage_hourly_v2` going forward; unions with `usage_hourly` can be implemented by queries that need historical reach beyond the cutover.
- All statements use `IF (NOT) EXISTS` for idempotent re-apply.

---

## Modified: Analytics consumer extraction

**File**: `apps/control-plane/src/platform/analytics/consumer.py`

**`_extract_usage_event` returned dict gains one key**:

```python
"goal_id": envelope.correlation_context.goal_id,   # ← NEW
```

**`_extract_quality_event` returned dict gains one key**: same as above.

---

## Modified: Analytics repository `insert_usage_events_batch`

**File**: `apps/control-plane/src/platform/analytics/repository.py`

**INSERT column list**: add `goal_id` between `workspace_id` and `agent_fqn` (or append; exact order per repository convention). Parameter binding follows the existing pattern (list of dicts → column-oriented batch insert via `clickhouse-connect`).

---

## Modified: OpenSearch `audit-events` index template — new mapping property

**File**: `deploy/opensearch/init/init_opensearch.py::create_index_templates`

**`audit_template["template"]["mappings"]["properties"]`** gains:

```python
"goal_id": {"type": "keyword"},
```

**`connector_template["template"]["mappings"]["properties"]`** gains the same (optional; symmetry with audit events — connector deliveries can be goal-scoped).

---

## Validation Rules

| Field | Rule | Location |
|-------|------|----------|
| `X-Goal-Id` header | Valid UUID string, optional | `CorrelationMiddleware` |
| `CorrelationContext.goal_id` | UUID or None | Pydantic model (existing) |
| `usage_events.goal_id` | Nullable UUID | ClickHouse column |
| `audit-events.goal_id` | keyword (opaque string) | OpenSearch mapping |

---

## State Transitions

None. This feature is purely structural — a new dimension propagated through existing pipelines.

---

## Backward compatibility

- Envelopes without `goal_id` deserialize cleanly (Pydantic default `None`).
- ClickHouse rows written before the column add have `NULL` in `goal_id` and are excluded from `WHERE goal_id = ?` queries without error.
- OpenSearch documents written before the mapping change are unaffected; dynamic mapping accepts new fields at any time.
- HTTP callers that do not send `X-Goal-Id` see identical behavior to today.
