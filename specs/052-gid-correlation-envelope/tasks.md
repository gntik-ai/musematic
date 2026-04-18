# Tasks: GID Correlation and Event Envelope Extension

**Input**: Design documents from `specs/052-gid-correlation-envelope/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/contracts.md ✅, quickstart.md ✅

**Scope note**: `CorrelationContext.goal_id` already exists (shipped in features 018/024). `InteractionService.post_goal_message` already sets `goal_id` on the envelope. This update pass wires the remaining propagation gaps: HTTP header extraction, envelope auto-population via ContextVar fallback, analytics ClickHouse dimension, and log index mapping. Total scope: 5 modified source files + 1 new ClickHouse init SQL + 4 test modules. The spec requested test coverage (per FR/SC); tests are included.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the request-scoped ContextVar for `goal_id` and the envelope factory fallback. These are prerequisites for both US1 (header propagation) and US4 (internal producers picking up the value).

- [X] T001 Add `goal_id_var: ContextVar[str] = ContextVar("goal_id", default="")` module-level variable in `apps/control-plane/src/platform/common/correlation.py` (alongside the existing `correlation_id_var`); no change to middleware behavior yet — just the variable definition
- [X] T002 Extend `make_envelope()` in `apps/control-plane/src/platform/common/events/envelope.py` to accept a new keyword argument `goal_id: UUID | None = None` and to fall back to `correlation.goal_id_var.get()` (parsed as UUID, empty string → None) when neither `correlation_context.goal_id` nor the `goal_id` kwarg is provided; priority order per data-model.md §`make_envelope()` Semantics: (1) explicit `correlation_context.goal_id`, (2) `goal_id` kwarg, (3) ContextVar fallback, (4) None. Import path: `from platform.common.correlation import goal_id_var`. Preserve existing `agent_fqn` behavior unchanged.

**Checkpoint**: `make_envelope()` correctly populates `goal_id` from the ContextVar when it is set, and the feature is still dormant from the outside (no middleware change yet). Existing envelope tests pass unchanged.

---

## Phase 2: Foundational — No additional foundational tasks

> The envelope field `CorrelationContext.goal_id` is **already implemented** (feature 018/024). The `goal_id` ContextVar and factory fallback from Phase 1 are the only shared plumbing needed.

---

## Phase 3: US1 — Goal-scoped request tracing across services (Priority: P1)

**Goal**: Inbound `X-Goal-Id` header is extracted, validated as UUID, bound to the request-scoped ContextVar, attached to `request.state.goal_id`, and echoed on the response. Any event produced during that request inherits `goal_id` on its envelope via the Phase 1 factory fallback.

**Independent Test**: Send an HTTP request with header `X-Goal-Id: <uuid>` to a goal-producing endpoint; assert response carries `X-Goal-Id: <uuid>`; assert the captured Kafka envelope's `correlation_context.goal_id == UUID(<uuid>)`. Send with malformed header → 422.

- [X] T003 [US1] Extend `CorrelationMiddleware.dispatch` in `apps/control-plane/src/platform/common/correlation.py` to (a) read `request.headers.get("X-Goal-Id", "").strip()`, (b) if non-empty, validate it as a UUID string (wrap `UUID(value)`); on `ValueError` return `starlette.responses.JSONResponse(status_code=422, content={"error": "invalid X-Goal-Id header"})` without calling `call_next`, (c) if valid, call `goal_id_var.set(value)` and store the token; set `request.state.goal_id = value`; (d) after `call_next`, echo `response.headers["X-Goal-Id"] = value`; (e) in the `finally` block, reset `goal_id_var` from the stored token alongside the existing `correlation_id_var` reset. Empty/absent header is a no-op (no var set, no echo).

**Checkpoint**: US1 complete — HTTP header propagation is live and any event produced inside a goal-bound request carries `goal_id` on its envelope.

---

## Phase 4: US2 — Goal-dimensioned analytics and cost attribution (Priority: P1)

**Goal**: `usage_events` ClickHouse table carries `goal_id` as a `Nullable(UUID)` column; hourly aggregate includes `goal_id` as a grouping dimension; the analytics consumer extracts `goal_id` from the envelope and writes it through the repository.

**Independent Test**: Apply the init SQL against a test ClickHouse instance; ingest two usage events with different `goal_id` values on the same (workspace, agent, model); query `SELECT goal_id, sum(input_tokens) FROM usage_hourly_v2 WHERE workspace_id = ? GROUP BY goal_id` and assert two distinct buckets; ingest a third event with `goal_id=None`; assert a `NULL` bucket appears.

- [X] T004 [P] [US2] Create `deploy/clickhouse/init/007-add-goal-id.sql` with idempotent DDL: (a) `ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS goal_id Nullable(UUID)`, (b) `CREATE TABLE IF NOT EXISTS usage_hourly_v2 (workspace_id UUID, goal_id Nullable(UUID), agent_id UUID, provider String, model String, hour DateTime, total_input_tokens UInt64, total_output_tokens UInt64, total_reasoning_tokens UInt64, total_cost Decimal128(6), event_count UInt64, avg_context_quality Float64) ENGINE = SummingMergeTree() PARTITION BY toYYYYMM(hour) ORDER BY (workspace_id, goal_id, agent_id, provider, model, hour)`, (c) `DROP VIEW IF EXISTS usage_hourly_mv`, (d) `CREATE MATERIALIZED VIEW IF NOT EXISTS usage_hourly_mv TO usage_hourly_v2 AS SELECT workspace_id, goal_id, agent_id, provider, model, toStartOfHour(event_time) AS hour, sum(input_tokens) AS total_input_tokens, sum(output_tokens) AS total_output_tokens, sum(reasoning_tokens) AS total_reasoning_tokens, sum(estimated_cost) AS total_cost, count() AS event_count, avg(context_quality_score) AS avg_context_quality FROM usage_events GROUP BY workspace_id, goal_id, agent_id, provider, model, hour`. Do NOT drop the existing `usage_hourly` table (kept for backward compatibility with any historical queries).
- [X] T005 [P] [US2] Modify `_extract_usage_event` in `apps/control-plane/src/platform/analytics/consumer.py` (around line 216): add the key `"goal_id": envelope.correlation_context.goal_id` to the returned dict. Also add `"goal_id": envelope.correlation_context.goal_id` to the dict returned by `_extract_quality_event` (around line 256). Value may be `None`; no validation needed here.
- [X] T006 [US2] Update `AnalyticsRepository.insert_usage_events_batch` (and the quality counterpart if present) in `apps/control-plane/src/platform/analytics/repository.py`: add `goal_id` to the INSERT column list and the per-row value tuple/dict passed to `clickhouse-connect`. Mirror the exact column ordering used in the new `007-add-goal-id.sql`. If the quality event insertion has a matching shape and the column was added to a quality table in this feature, update the insert there too; otherwise leave quality inserts unchanged (goal_id is stored on usage_events only per the plan).

**Checkpoint**: US2 complete — every newly ingested usage event carries `goal_id` in ClickHouse; aggregate queries can group by goal.

---

## Phase 5: US3 — Goal-scoped log search for incident response (Priority: P2)

**Goal**: OpenSearch `audit-events` (and symmetrically `connector-payloads`) index templates carry `goal_id` as a top-level `keyword` mapping, so `term: {goal_id: <uuid>}` queries filter directly on the field.

**Independent Test**: Run `initialize_opensearch()` against a test cluster; assert `GET /_index_template/audit-events` includes `mappings.properties.goal_id == {"type": "keyword"}`; index a document with `goal_id = "<uuid>"` into `audit-events-000002` (a fresh rollover index); assert `POST /audit-events-*/_search {"query": {"term": {"goal_id": "<uuid>"}}}` returns the document.

- [X] T007 [US3] Modify `create_index_templates` in `deploy/opensearch/init/init_opensearch.py`: add `"goal_id": {"type": "keyword"}` to `audit_template["template"]["mappings"]["properties"]` (alongside the existing `workspace_id` mapping). Add the same key to `connector_template["template"]["mappings"]["properties"]` for symmetry. Do not modify `marketplace_template`. The function is idempotent on re-run (`put_index_template` overwrites), so no version bump is required.

**Checkpoint**: US3 complete — log search by `goal_id` returns matching records directly without joins.

---

## Phase 6: US4 — Internal producers preserve goal context (Priority: P2)

**Goal**: Internal goal-emitting service paths in `InteractionService` that today publish events without carrying `goal_id` on the envelope get fixed so the GID travels on the envelope, not just in the payload.

**Independent Test**: Call `InteractionService.transition_goal_status(...)` and `InteractionService.create_attention_request(...)` with `related_goal_id` set; capture the published envelopes; assert `envelope.correlation_context.goal_id` matches the goal being acted on.

- [X] T008 [US4] Audit goal-emitting call sites in `apps/control-plane/src/platform/interactions/service.py`: locate every `self.producer.publish_*` (or equivalent via `publish_goal_*` / `publish_attention_*`) invocation where the payload carries a `goal_id` or `related_goal_id` but the adjacent `_correlation(...)` call does not pass `goal_id=`. For each, add `goal_id=<the goal uuid in scope>` to the `self._correlation(...)` keyword arguments. Known reference call sites: `post_goal_message` (already correct, line ~431 — verify only), `publish_goal_status_changed` producers (look for `GoalStatusChangedPayload` constructor calls), and `publish_attention_requested` where `related_goal_id is not None` (attention request producer should pass `goal_id=request.related_goal_id` into `_correlation`). Leave unrelated envelopes untouched; do not default a goal_id when the action is not goal-bound.

**Checkpoint**: US4 complete — every internal producer that acts on behalf of a goal carries the GID on its envelope.

---

## Phase 7: Tests

**Purpose**: Cover the 3 new code paths and the 3 storage changes. Spec acceptance scenarios are the source of truth.

- [X] T009 [P] Write unit tests in `apps/control-plane/tests/unit/common/test_correlation.py` (new file): (1) `test_x_goal_id_valid_uuid_sets_context_var` — send a request with a valid UUID; assert `goal_id_var.get()` inside the handler equals the UUID; assert response echoes `X-Goal-Id`; (2) `test_x_goal_id_invalid_uuid_returns_422` — send a request with `X-Goal-Id: not-a-uuid`; assert HTTP 422 with JSON body `{"error": "invalid X-Goal-Id header"}`; assert downstream handler was NOT invoked; (3) `test_x_goal_id_absent_is_noop` — send a request without the header; assert `goal_id_var.get() == ""` inside the handler; assert response has no `X-Goal-Id` header; (4) `test_x_goal_id_empty_string_treated_as_absent` — send with `X-Goal-Id: ` (whitespace only); assert same as absent case; (5) `test_concurrent_requests_do_not_share_goal_id` — run two requests concurrently with different UUIDs via `asyncio.gather`; assert each handler observes only its own value. Use Starlette `TestClient` + a minimal ASGI app mounting only `CorrelationMiddleware`.
- [X] T010 [P] Extend unit tests in `apps/control-plane/tests/unit/common/test_envelope.py`: (1) `test_make_envelope_picks_up_goal_id_from_context_var` — inside a block where `goal_id_var.set("a3b0c480-0f1e-4b60-9f0f-7e0e4d3f2a11")`, call `make_envelope("agent.created", "registry", payload={})` with no kwargs and no `correlation_context`; assert `envelope.correlation_context.goal_id == UUID("a3b0c480-...")`; (2) `test_explicit_goal_id_kwarg_overrides_context_var` — with the var set to UUID A, call `make_envelope(..., goal_id=UUID_B)`; assert envelope carries `UUID_B`; (3) `test_correlation_context_goal_id_overrides_both` — pass a `CorrelationContext(correlation_id=uuid4(), goal_id=UUID_C)` while var is A and kwarg is B; assert envelope carries `UUID_C`; (4) `test_no_goal_id_anywhere_leaves_none` — var unset, no kwarg, no context; assert `goal_id is None`; (5) `test_backwards_compatible_missing_field` — deserialize JSON `{"correlation_id": "<uuid>"}` into `CorrelationContext`; assert no error and `goal_id is None`.
- [X] T011 [P] Extend unit tests in `apps/control-plane/tests/unit/test_analytics_consumer.py` (add to existing file if present; create if not): (1) `test_extract_usage_event_carries_goal_id` — build an `EventEnvelope` with `correlation_context.goal_id = UUID(...)`, call `AnalyticsPipelineConsumer._extract_usage_event(envelope)`; assert the returned dict contains `"goal_id": UUID(...)`; (2) `test_extract_usage_event_without_goal_id_is_none` — envelope with `correlation_context.goal_id = None`; assert the returned dict contains `"goal_id": None`; (3) `test_extract_quality_event_carries_goal_id` — same for `_extract_quality_event`.
- [X] T012 [US2] Write integration tests in `apps/control-plane/tests/integration/registry/test_analytics_goal.py` (new file): spin up a test ClickHouse via the existing fixture (`clickhouse_client`); apply `deploy/clickhouse/init/007-add-goal-id.sql` via `clickhouse_client.execute(...)` for each statement; (1) `test_usage_events_has_goal_id_column` — `DESCRIBE usage_events` includes `goal_id Nullable(UUID)`; (2) `test_insert_usage_event_with_goal_id` — insert a row via `AnalyticsRepository.insert_usage_events_batch` with a populated `goal_id`; `SELECT goal_id FROM usage_events` returns the UUID; (3) `test_group_by_goal_id_yields_two_buckets` — insert 2 events for goal A and 1 for goal B on the same (workspace, agent, model, hour); query `SELECT goal_id, sum(input_tokens) FROM usage_hourly_v2 GROUP BY goal_id ORDER BY goal_id`; assert 2 rows with sums matching the inputs; (4) `test_null_goal_id_bucket` — insert one event with `goal_id = None`; query `SELECT count() FROM usage_events WHERE goal_id IS NULL`; assert 1; (5) `test_migration_idempotent` — run the init SQL twice; assert no error.
- [X] T013 [US3] Extend integration tests in `apps/control-plane/tests/integration/test_opensearch_init.py`: (1) `test_audit_events_template_has_goal_id_mapping` — after `initialize_opensearch()` runs, call `client.indices.get_index_template(name="audit-events")`; assert the response's `mappings.properties.goal_id == {"type": "keyword"}`; (2) `test_connector_payloads_template_has_goal_id_mapping` — same for the connector template; (3) `test_goal_id_searchable_on_rollover_index` — create `audit-events-000002` with the `audit-events` alias; index a document `{"event_id": "...", "goal_id": "<uuid>", ...}`; `POST audit-events-*/_search {"query": {"term": {"goal_id": "<uuid>"}}}`; assert 1 hit with the indexed document.

---

## Dependencies and Execution Order

### Phase Dependencies

- **Phase 1 (Setup — T001, T002)**: No dependencies — start immediately
- **Phase 3 (US1)**: T003 depends on T001 (needs `goal_id_var` defined)
- **Phase 4 (US2)**: T005 depends on T002 (consumer reads `envelope.correlation_context.goal_id`, which is populated by the factory). T006 depends on T004 (schema must exist before inserts include the column). T005 and T004 are parallelizable with each other.
- **Phase 5 (US3)**: T007 is independent of Phases 1–4
- **Phase 6 (US4)**: T008 depends on the convention established by T002 but not on its implementation (could ship before T002 since `_correlation` accepts `goal_id` independently of `make_envelope`'s fallback logic)
- **Phase 7 (Tests)**: T009 depends on T003 (middleware behavior); T010 depends on T002 (factory fallback); T011 depends on T005 (consumer extraction); T012 depends on T004 + T006 (schema + repository); T013 depends on T007 (OpenSearch mapping)

### User Story Dependencies

- **US1**: Depends on Phase 1 (ContextVar exists)
- **US2**: Depends on Phase 1 (consumer reads envelope populated by the factory; though technically independent of middleware, US2 is only meaningful end-to-end when US1 is also live)
- **US3**: Fully independent
- **US4**: Fully independent (uses the already-correct `_correlation(goal_id=...)` path established before this feature)

### Parallel Opportunities

```bash
# Phase 1 setup: T001 and T002 touch different files — safe to parallelize
T001 correlation.py ContextVar   |   T002 envelope.py factory fallback

# After Phase 1, US1 (T003) and US3 (T007) can run in parallel
T003 middleware X-Goal-Id        |   T007 OpenSearch mapping

# Within US2: T004 (SQL) and T005 (consumer extraction) parallel; T006 (repo) waits on T004
T004 ClickHouse init SQL         |   T005 consumer extraction
                                 |  → T006 repository insert columns

# Phase 7 tests: T009, T010, T011 are all different test files → parallel
T009 test_correlation.py         |   T010 test_envelope.py   |   T011 test_analytics_consumer.py
# T012 and T013 are integration tests — can run in parallel once their targets are in place
```

---

## Implementation Strategy

### MVP (US1 + US2 — Phases 1, 3, 4)

1. T001 + T002: ContextVar + factory fallback (parallel)
2. T003: middleware header extraction
3. T004 + T005: ClickHouse DDL + consumer extraction (parallel)
4. T006: repository INSERT column addition
5. **VALIDATE**: Send an HTTP request with `X-Goal-Id`; confirm a usage event lands in ClickHouse with matching `goal_id`; query grouped by `goal_id` returns the expected bucket

### Full feature (all phases)

1. MVP (T001–T006) → validate
2. T007: OpenSearch mapping
3. T008: interactions producer audit and patch
4. T009–T013: tests
5. Deploy: apply `deploy/clickhouse/init/007-add-goal-id.sql` on the target cluster; re-run `initialize_opensearch()` job; roll control-plane pods to pick up the middleware change

### Parallel team strategy

- Developer A: T001 → T003 → T009 (middleware + its unit test)
- Developer B: T002 → T010 (factory + its unit test)
- Developer C: T004 + T006 → T012 (ClickHouse schema + repo + integration test)
- Developer D: T005 → T011 (consumer extraction + its unit test)
- Developer E: T007 → T013 (OpenSearch mapping + its integration test)
- Developer F: T008 (interactions audit) — independent of all

---

## Notes

- [P] marks tasks that touch different files with no inter-dependency on an incomplete task — safe to parallelize
- `CorrelationContext.goal_id` is NOT added by this feature — it already exists; the field addition was shipped in features 018/024
- `InteractionService.post_goal_message` is NOT modified — it already passes `goal_id` to `_correlation(...)`
- T008 is an audit-first task: if the audit finds all goal-emitting producers already carry `goal_id` on the envelope (the most likely outcome), the task is a no-op and should be closed as such; if any gaps are found, the fix is a one-line addition to each
- Total modifications: 5 existing files + 1 new ClickHouse init SQL file + 4 test modules (2 new + 2 extended)
