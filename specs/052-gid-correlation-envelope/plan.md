# Implementation Plan: GID Correlation and Event Envelope Extension

**Branch**: `052-gid-correlation-envelope` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/052-gid-correlation-envelope/spec.md`

## Summary

The `goal_id` field is already shipped on `CorrelationContext` (features 018/024). This update pass closes the remaining three propagation gaps: (1) HTTP middleware extracts and echoes `X-Goal-Id`; (2) `make_envelope()` auto-populates `goal_id` from a request-scoped ContextVar so event producers inherit it with no per-caller changes; (3) analytics storage and log indexing carry `goal_id` as a queryable dimension. Total scope: 4 modified files + 1 new ClickHouse init SQL + tests.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: FastAPI 0.115+, Starlette middleware, Pydantic v2, aiokafka 0.11+, clickhouse-connect 0.8+, opensearch-py 2.x
**Storage**: ClickHouse (`usage_events`, `usage_hourly_v2`), OpenSearch (`audit-events`, `connector-payloads` index templates). PostgreSQL unaffected.
**Testing**: pytest + pytest-asyncio 8.x; min 95% coverage on modified files
**Target Platform**: Linux / Kubernetes (same as control plane)
**Project Type**: Brownfield modification to existing Python web service + analytics + log init scripts
**Performance Goals**: Per-goal ClickHouse rollups under 2 seconds (SC-003); OpenSearch goal-filter under 1 second (SC-004); HTTP middleware overhead under 1 ms additional per request
**Constraints**: Brownfield Rules 1–8; no file rewrites; additive + backward-compatible only; ClickHouse DDL applied via numbered init SQL (Alembic covers PostgreSQL only)
**Scale/Scope**: 4 modified files (`correlation.py`, `envelope.py`, `analytics/consumer.py`, `analytics/repository.py`, `deploy/opensearch/init/init_opensearch.py` — the init script counts as modified), 1 new ClickHouse init SQL file, 4 test modules

## Constitution Check

**GATE: Must pass before implementation**

| Principle | Status | Notes |
|-----------|--------|-------|
| Modular monolith (Principle I) | ✅ PASS | Changes confined to `common/`, `interactions/` (audit only), `analytics/` — no new services, no cross-context DB access |
| No cross-boundary DB access (Principle IV) | ✅ PASS | Analytics consumer reads its own ClickHouse tables; OpenSearch init script owns its templates |
| Policy is machine-enforced (Principle VI) | ✅ PASS | N/A for this feature |
| GID is a first-class correlation dimension (Principle X) | ✅ PASS | This feature delivers the outstanding wiring for that principle |
| Zero-trust default visibility (Principle IX) | ✅ PASS | N/A for this feature |
| Secrets not in LLM context (Principle XI) | ✅ PASS | N/A for this feature |
| Generic S3 storage (Principle XVI) | ✅ PASS | N/A for this feature |
| Brownfield Rule 1 (no rewrites) | ✅ PASS | Only line-level additions to 4 existing files + 1 new init SQL |
| Brownfield Rule 2 (Alembic only) | ✅ PASS with note | Alembic governs PostgreSQL. ClickHouse schema in this codebase is managed by numbered init SQL files in `deploy/clickhouse/init/` — convention respected (new file `007-add-goal-id.sql`). Research Decision 6. |
| Brownfield Rule 3 (preserve tests) | ✅ PASS | New tests added; no existing tests modified |
| Brownfield Rule 4 (use existing patterns) | ✅ PASS | Middleware change mirrors the established `X-Correlation-ID` pattern; envelope factory mirrors the `agent_fqn` ContextVar-style fallback pattern |
| Brownfield Rule 7 (backward-compatible) | ✅ PASS | Envelope field already optional; ClickHouse column `Nullable`; OpenSearch mapping addition is dynamic-mapping-compatible |

**Post-design re-check**: No violations.

## Project Structure

### Documentation (this feature)

```text
specs/052-gid-correlation-envelope/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── contracts.md     # Phase 1 output
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code — What Changes

```text
apps/control-plane/
├── src/platform/
│   ├── common/
│   │   ├── correlation.py                   MODIFIED — add goal_id_var ContextVar;
│   │   │                                               CorrelationMiddleware extracts
│   │   │                                               X-Goal-Id, validates UUID, sets
│   │   │                                               request.state.goal_id, echoes
│   │   │                                               header; 422 on malformed value
│   │   └── events/
│   │       └── envelope.py                  MODIFIED — make_envelope() gains optional
│   │                                                   goal_id kwarg + ContextVar fallback
│   ├── interactions/
│   │   └── service.py                       AUDIT + minimal fix — goal_status and
│   │                                                   attention_requested paths ensure
│   │                                                   _correlation(... goal_id=...)
│   │                                                   is set when a goal is in scope
│   └── analytics/
│       ├── consumer.py                      MODIFIED — _extract_usage_event and
│       │                                              _extract_quality_event return dicts
│       │                                              gain "goal_id" key pulled from
│       │                                              envelope.correlation_context.goal_id
│       └── repository.py                    MODIFIED — INSERT column list includes goal_id
│
└── tests/
    ├── unit/common/
    │   ├── test_correlation.py              NEW — X-Goal-Id header handling (valid,
    │   │                                          invalid, absent, ContextVar isolation)
    │   └── test_envelope.py                 MODIFIED — add goal_id auto-population tests
    ├── unit/
    │   └── test_analytics_consumer.py       MODIFIED — extraction populates goal_id
    └── integration/
        ├── registry/
        │   └── test_analytics_goal.py       NEW — ClickHouse schema + insert + aggregate
        └── test_opensearch_init.py          MODIFIED — audit-events template carries
                                                        goal_id keyword mapping

deploy/
├── clickhouse/init/
│   └── 007-add-goal-id.sql                  NEW — ALTER usage_events ADD goal_id;
│                                                  new usage_hourly_v2 target with
│                                                  goal_id in ORDER BY; rebuild MV
└── opensearch/init/
    └── init_opensearch.py                   MODIFIED — audit-events + connector-payloads
                                                        mappings gain goal_id keyword
```

**Structure Decision**: Strictly additive changes to 5 existing source files + 1 new ClickHouse init SQL file. No existing file is rewritten; no new bounded context is introduced.

## Implementation Phases

### Phase 1: HTTP Middleware — `X-Goal-Id` header

**Goal**: Accept `X-Goal-Id` inbound, validate as UUID, bind to a request-scoped ContextVar, echo on response.

**Files**:
- `apps/control-plane/src/platform/common/correlation.py` — add `goal_id_var: ContextVar[str]`; `CorrelationMiddleware.dispatch` reads `X-Goal-Id`, validates UUID format, sets context var + `request.state.goal_id`, echoes header; 422 on malformed value; resets var in `finally`

**Independent test**: Unit tests on the middleware — valid UUID sets var and echoes; invalid returns 422; absent is a no-op; two concurrent requests see isolated context vars.

---

### Phase 2: Event Envelope — ContextVar fallback in `make_envelope()`

**Goal**: Any event produced within an HTTP request that carried `X-Goal-Id` inherits `goal_id` on the envelope with zero per-producer changes.

**Files**:
- `apps/control-plane/src/platform/common/events/envelope.py` — `make_envelope()` signature gains `goal_id: UUID | None = None`; body resolves priority (1) explicit context goal_id, (2) kwarg, (3) `goal_id_var.get()`, (4) None

**Independent test**: Unit tests — `make_envelope` without kwargs but with `goal_id_var.set("...")` active → envelope carries that goal_id; kwarg overrides ContextVar; explicit `correlation_context.goal_id` overrides both; no var set → None; pre-feature JSON still deserializes.

---

### Phase 3: Interactions service — goal-emitting producers audit

**Goal**: Ensure `publish_goal_status_changed` and `publish_attention_requested` call sites pass `goal_id` (or `related_goal_id`) into the correlation helper.

**Files**:
- `apps/control-plane/src/platform/interactions/service.py` — targeted line-level fix if audit reveals a producer not currently passing `goal_id` into `self._correlation(...)`

**Note**: `post_goal_message` is already correct. Audit may find this phase is a no-op. If so, remove the phase and move forward.

**Independent test**: Unit tests on `InteractionService` — publishing a goal-status-changed event and an attention request with `related_goal_id` results in envelopes whose `correlation_context.goal_id` is populated.

---

### Phase 4: ClickHouse schema — `goal_id` dimension

**Goal**: Store `goal_id` as a queryable column on `usage_events`, and carry it through to the hourly aggregate.

**Files**:
- `deploy/clickhouse/init/007-add-goal-id.sql` (NEW) — (a) `ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS goal_id Nullable(UUID)`, (b) `CREATE TABLE IF NOT EXISTS usage_hourly_v2 (...)` with `goal_id` in `ORDER BY`, (c) `DROP VIEW IF EXISTS usage_hourly_mv; CREATE MATERIALIZED VIEW usage_hourly_mv TO usage_hourly_v2 AS SELECT ..., goal_id, ... GROUP BY ..., goal_id, ...`
- `apps/control-plane/src/platform/analytics/consumer.py` — `_extract_usage_event` and `_extract_quality_event` dicts gain `"goal_id": envelope.correlation_context.goal_id`
- `apps/control-plane/src/platform/analytics/repository.py` — `insert_usage_events_batch` (and quality counterpart) add `goal_id` to the INSERT column list

**Independent test**: Integration test — apply the init SQL on a test ClickHouse instance; insert an envelope-derived usage event with `goal_id`; query `usage_events` and `usage_hourly_v2` returns matching `goal_id`. Query grouped by `goal_id` reconciles to base-table totals.

---

### Phase 5: OpenSearch mapping — `goal_id` keyword

**Goal**: Make `goal_id` a first-class filter field on the audit log index.

**Files**:
- `deploy/opensearch/init/init_opensearch.py` — `create_index_templates`: `audit_template["template"]["mappings"]["properties"]["goal_id"] = {"type": "keyword"}`; same addition to `connector_template` for symmetry

**Independent test**: Integration test — run `initialize_opensearch()` against the test cluster; `GET /_index_template/audit-events` shows `goal_id` mapping; index a doc with `goal_id` and search by `term: goal_id` returns it; search against a legacy-shaped doc with no `goal_id` does not return it under the `goal_id` filter.

---

## API Endpoints Used / Modified

| Endpoint | Status | Change |
|----------|--------|--------|
| (All HTTP routes) | Existing | Accept optional `X-Goal-Id` header on request; echo on response. No endpoint-specific schema change. |
| Kafka `workflow.runtime`, `runtime.lifecycle`, `evaluation.events` | Existing | Envelope `correlation_context.goal_id` now populated when the producer was triggered by a goal-bound request or an internal goal-acting service |

## Dependencies

- **Features 018 and 024**: Provided the `goal_id` field on `CorrelationContext` and the goal-related event payloads. Already deployed.
- **Feature 020 (Analytics)**: Provides the `usage_events` ClickHouse table and the analytics consumer. Extended by this feature.
- **Feature 008 (OpenSearch)**: Provides the init-script convention and the `audit-events` template. Extended by this feature.
- **Feature 051 (FQN)**: Introduced the `agent_fqn` ContextVar + `make_envelope` kwarg pattern. This feature follows the same pattern for `goal_id`.

## Complexity Tracking

No constitution violations. No complexity justification table needed.

The implementation is intentionally minimal:

| Category | Count |
|---|---|
| Modified Python source files | 5 (`correlation.py`, `envelope.py`, `interactions/service.py` — audit only, `analytics/consumer.py`, `analytics/repository.py`) |
| Modified deployment files | 1 (`deploy/opensearch/init/init_opensearch.py`) |
| New files | 1 ClickHouse init SQL + 2 test modules |
| New bounded contexts | 0 |
| New database tables (PostgreSQL) | 0 |
| New Kafka topics | 0 |
| New API endpoints | 0 |

The user's 6-step plan aligned with the spec, with two refinements discovered during research:

1. Step 1 ("add goal_id to CorrelationContext") is a no-op — the field already exists.
2. Step 3 ("ClickHouse migration on `execution_metrics`") is adjusted to `usage_events` (the actual analytics table in this codebase) plus the hourly aggregate recreation.
