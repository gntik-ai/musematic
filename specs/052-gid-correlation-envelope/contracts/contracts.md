# Contracts: GID Correlation and Event Envelope Extension

**Feature**: 052-gid-correlation-envelope
**Phase**: 1 — Design
**Date**: 2026-04-18

---

## 1. HTTP header contract: `X-Goal-Id`

### Request

Any HTTP request to the control-plane API MAY include:

```
X-Goal-Id: <uuid>
```

**Format**: Standard UUID string, 36 characters with hyphens (e.g., `a3b0c480-0f1e-4b60-9f0f-7e0e4d3f2a11`). Case-insensitive; the server normalizes to lowercase.

**Semantics**: When present, the server binds the value to the request-scoped correlation context for the lifetime of the request and propagates it to any Kafka event envelope produced during handling, directly or indirectly (including background tasks spawned from the request).

### Response

The server echoes the resolved header:

```
X-Goal-Id: <uuid>
```

If the request did not include `X-Goal-Id`, the response does not include it either.

### Error: malformed header

If `X-Goal-Id` is present but not a valid UUID string, the server responds with:

```
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{"error": "invalid X-Goal-Id header"}
```

The downstream route handler is not invoked; no events are produced.

### Authorization

The header itself is not authenticated (it is a correlation hint, not a capability). Authorization of goal access is enforced by the existing workspace/goal authorization layer when a route actually operates on a specific goal. Providing a GID for a goal the caller cannot access is not, in itself, an error.

---

## 2. Event envelope contract: `CorrelationContext.goal_id`

### Field

The existing `CorrelationContext` Pydantic model carries `goal_id: UUID | None`. This feature does not change the field shape.

### Producer contract

Any event producer SHOULD populate `correlation_context.goal_id` when the event relates to a specific workspace goal. Producers fall into two populated paths:

1. **Auto-populated** — When an event is produced inside an HTTP request that carried `X-Goal-Id`, the `make_envelope()` factory picks up the value from the request-scoped `ContextVar` and sets it automatically. No per-producer change required.
2. **Explicitly populated** — When an event is produced outside an HTTP context (background task, scheduled job, internal service call), the producer explicitly passes `goal_id=` to `make_envelope()` or constructs a `CorrelationContext` with the field set.

### Consumer contract

Consumers MUST accept envelopes where `goal_id` is `None`. Consumers SHOULD use `goal_id` as a grouping or filtering dimension where the bounded context's purpose makes it relevant (analytics, log indexing, operator dashboards).

### Backward compatibility

Envelopes serialized before this feature may omit `goal_id` entirely. Pydantic v2 tolerates missing optional fields and sets them to the default `None`. No consumer needs to be changed.

---

## 3. Analytics storage contract: `usage_events.goal_id`

### ClickHouse column

```sql
goal_id Nullable(UUID)
```

Added to:

- `usage_events` — base event table
- `usage_hourly_v2` — hourly aggregate target of `usage_hourly_mv` (replaces `usage_hourly` going forward; the legacy table is retained until its retention window expires)

### Query contract

Clients of the analytics repository can:

- `SELECT ..., goal_id FROM usage_events` — returns `NULL` for rows written before the column add.
- `WHERE goal_id = ?` — returns rows matching the supplied UUID; excludes rows with `NULL` without error.
- `GROUP BY goal_id` — buckets by goal; `NULL` is its own bucket.

### Aggregate contract

`usage_hourly_v2` carries `goal_id` in both the SELECT projection of the materialized view and the `ORDER BY` of the target `SummingMergeTree` table, so sums are correctly partitioned per (workspace, goal, agent, provider, model, hour).

---

## 4. Log index contract: `audit-events.goal_id`

### OpenSearch mapping

```json
"goal_id": { "type": "keyword" }
```

Added to the `audit-events` (and optionally `connector-payloads`) index templates. Applies to all indexes rolled over after the template update. Existing indexes keep their old mapping but accept the field via OpenSearch dynamic mapping (default setting) from first occurrence.

### Query contract

Clients of the log index can:

- Filter by `term: { goal_id: "<uuid>" }` — returns all records with that `goal_id`.
- Documents without `goal_id` are silently excluded from the filter response.

### Latency target

Goal-filtered log search over a 24-hour window for a single workspace returns results in under 1 second (SC-004).

---

## 5. Internal contract: `goal_id_var` ContextVar

### Module

`apps/control-plane/src/platform/common/correlation.py`

### Definition

```python
goal_id_var: ContextVar[str] = ContextVar("goal_id", default="")
```

### Producer side

`CorrelationMiddleware` sets this var at the start of each HTTP request from `X-Goal-Id` (if valid) and resets it in a `finally` block. Other code MUST NOT call `.set(...)` on this ContextVar outside the middleware.

### Consumer side

`make_envelope()` reads `goal_id_var.get()` as a fallback when no explicit `goal_id` or `correlation_context.goal_id` is provided. Other code MAY read the ContextVar but SHOULD prefer explicit parameters where feasible.

### Non-HTTP contexts

Background tasks, scheduled jobs, and Kafka consumers do not have a request-scoped ContextVar and so `goal_id_var.get()` returns the empty string. Producers in these contexts MUST pass `goal_id` explicitly if the event is goal-scoped.

---

## 6. Operational contract: rollout and rollback

### Rollout

- ClickHouse DDL (`007-add-goal-id.sql`) is idempotent and safe to run online. New events written by an updated consumer populate `goal_id`; legacy rows retain `NULL`.
- OpenSearch template updates apply on next rollover; dynamic mapping covers the interim.
- Application code changes deploy normally; the middleware addition is a no-op for requests that don't send the header.

### Rollback

- Reverting the application is safe: unmodified consumers still accept envelopes with or without `goal_id`.
- Reverting the ClickHouse DDL is not attempted; the added column is `Nullable` and has no downstream dependencies outside this feature. Leaving the column in place is harmless if the application reverts.
- OpenSearch mapping additions are also left in place on rollback; they cost nothing and don't affect unrelated queries.
