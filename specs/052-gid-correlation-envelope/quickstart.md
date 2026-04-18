# Quickstart: GID Correlation and Event Envelope Extension

**Feature**: 052-gid-correlation-envelope
**Phase**: 1 — Design
**Date**: 2026-04-18

---

## What This Feature Changes

```text
apps/control-plane/
├── src/platform/
│   ├── common/
│   │   ├── correlation.py           MODIFIED — X-Goal-Id extraction + goal_id_var
│   │   └── events/
│   │       └── envelope.py          MODIFIED — make_envelope() fallback to goal_id_var
│   ├── interactions/
│   │   └── service.py               AUDIT ONLY — post_goal_message already correct;
│   │                                               verify goal_status_changed and
│   │                                               attention_requested paths pass
│   │                                               goal_id into _correlation()
│   └── analytics/
│       ├── consumer.py              MODIFIED — _extract_*_event dicts carry goal_id
│       └── repository.py            MODIFIED — INSERT column list adds goal_id
│
deploy/
├── clickhouse/init/
│   └── 007-add-goal-id.sql          NEW — ALTER base table + new hourly aggregate v2
└── opensearch/init/
    └── init_opensearch.py           MODIFIED — audit-events + connector-payloads
                                                mappings gain goal_id keyword
```

**What does NOT change**:
- `envelope.py::CorrelationContext` — `goal_id` already defined (feature 018/024)
- `interactions/service.py::post_goal_message` — already sets goal_id correctly
- Any bounded context outside analytics and interactions
- HTTP API endpoints — no route adds or removes

---

## Test Setup

```bash
cd apps/control-plane
make test-unit          # unit tests: middleware, envelope factory, consumer extraction
make test-integration   # integration: ClickHouse schema, OpenSearch mapping, end-to-end propagation
```

Integration tests require live ClickHouse and OpenSearch connections (same setup used by features 020 and 008).

---

## Testing Per User Story

### US1 — Goal-scoped request tracing across services

**Focus**: `X-Goal-Id` header propagates through middleware to all downstream events.

**Test cases**:

1. HTTP request with `X-Goal-Id: a3b0c480-0f1e-4b60-9f0f-7e0e4d3f2a11` to a goal-producing endpoint → response carries `X-Goal-Id: a3b0c480-0f1e-4b60-9f0f-7e0e4d3f2a11`.
2. Kafka event produced during that request → `envelope.correlation_context.goal_id == UUID("a3b0c480-0f1e-4b60-9f0f-7e0e4d3f2a11")`.
3. Two different requests with two different `X-Goal-Id` values handled concurrently → each request's downstream event carries only its own goal's UUID; no leakage via ContextVar.
4. HTTP request with `X-Goal-Id: not-a-uuid` → HTTP 422; no event produced; no exception raised in middleware.
5. HTTP request without `X-Goal-Id` → response has no `X-Goal-Id` header; downstream events carry `goal_id = None`; no errors.

---

### US2 — Goal-dimensioned analytics and cost attribution

**Focus**: ClickHouse `usage_events.goal_id` column + hourly aggregate include goal dimension.

**Test cases**:

1. After migration: `DESCRIBE usage_events` shows `goal_id Nullable(UUID)` column.
2. Insert a usage event via the analytics consumer with `envelope.correlation_context.goal_id = UUID(...)` → row in `usage_events` has matching `goal_id`.
3. Insert a usage event without `goal_id` → row has `goal_id IS NULL`; no error.
4. Run `SELECT goal_id, sum(input_tokens) FROM usage_events WHERE workspace_id = ? GROUP BY goal_id` → results include per-goal buckets and a `NULL` bucket.
5. `usage_hourly_v2` target table is populated via the materialized view: after writing events for two distinct goals in the same hour, query returns two rows with distinct `goal_id`.
6. Sum of `sum(total_input_tokens)` across all goal buckets for a workspace equals `sum(input_tokens)` in the base `usage_events` table for the same window (reconciliation invariant).

---

### US3 — Goal-scoped log search for incident response

**Focus**: OpenSearch `audit-events` index mapping carries `goal_id` keyword.

**Test cases**:

1. After running `init_opensearch.py`: `GET /_index_template/audit-events` shows `goal_id: { "type": "keyword" }` under mappings.properties.
2. A rolled-over fresh index inherits the `goal_id` mapping.
3. Index a document with `goal_id: "a3b0c480-0f1e-4b60-9f0f-7e0e4d3f2a11"` into `audit-events-000002` → `GET audit-events-*/_search?q=goal_id:a3b0c480-0f1e-4b60-9f0f-7e0e4d3f2a11` returns the document.
4. Index a document without `goal_id` → the same search does not return it.
5. Legacy index (written before template update) → documents appear in queries that don't filter by `goal_id`; are excluded from `goal_id = ?` queries.

---

### US4 — Internal producers preserve goal context

**Focus**: Goal-emitting service paths in `interactions/service.py` carry `goal_id` on the envelope.

**Test cases**:

1. Call `InteractionService.post_goal_message(goal_id=..., ...)` directly (no HTTP context) → captured envelope's `correlation_context.goal_id` equals the goal UUID. (Already works; regression guard.)
2. Transition a goal's status via the service → published `GoalStatusChangedPayload` event's envelope carries `goal_id`.
3. Raise an attention request with `related_goal_id` set → published `AttentionRequestedPayload` event's envelope carries `goal_id` (matching `related_goal_id`).
4. Raise an attention request with `related_goal_id = None` → envelope's `goal_id` is `None`; no default substituted.

---

### Combined: End-to-end correlation trace

**Setup**: Start the control-plane API, a Kafka broker, and ClickHouse + OpenSearch locally (or use the integration test harness).

**Test case**:

1. POST a request with `X-Goal-Id: <G>` that triggers an execution producing a usage event on `workflow.runtime`.
2. Analytics consumer ingests the event.
3. Query ClickHouse: `SELECT goal_id FROM usage_events WHERE workspace_id = <W>` returns `<G>`.
4. A log emitted during the same request (if wired into an `audit-events` write path) carries `goal_id = <G>` and is findable via `goal_id:<G>` search in OpenSearch.

---

## Edge Cases

| Scenario | Expected Behavior |
|----------|------------------|
| Two concurrent requests with different `X-Goal-Id` values | Each request's events carry only its own GID (ContextVar isolation) |
| Background task spawned from a goal-bound request | If task runs within the same asyncio context, inherits the GID; if detached (e.g., Kafka consumer callback), producer must pass `goal_id` explicitly |
| Header present but value is empty string | Treated as absent; no GID set; no 422 |
| Header present and valid but points to a goal the caller cannot access | 422 not raised here; access control enforced at the endpoint for goal-specific routes |
| ClickHouse column exists but query filters by `goal_id` on a workspace with only legacy rows | Returns empty result set; no error |
| OpenSearch query filters by `goal_id` on an old index | Returns empty result set; no error |
| Envelope deserialization of a historical event (pre-feature 018) | `goal_id = None`; no validation error |

---

## Migration Apply

```bash
# ClickHouse — analytics schema
clickhouse-client -q "$(cat deploy/clickhouse/init/007-add-goal-id.sql)"

# OpenSearch — index templates
python -m deploy.opensearch.init.init_opensearch

# Verify
clickhouse-client -q "DESCRIBE usage_events"   # expect goal_id Nullable(UUID)
curl -s $OPENSEARCH_URL/_index_template/audit-events | jq .index_templates[0].index_template.template.mappings.properties.goal_id
# expect: { "type": "keyword" }
```
