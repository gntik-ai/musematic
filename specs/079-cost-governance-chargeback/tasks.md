# Tasks: Cost Governance and Chargeback

**Feature**: 079-cost-governance-chargeback
**Branch**: `079-cost-governance-chargeback`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

User stories (from spec.md):
- **US1 (P1)** — Per-execution cost attribution (foundational; everything downstream depends on it)
- **US2 (P2)** — Budget enforcement with soft alerts and hard caps (with bounded admin override)
- **US3 (P3)** — Chargeback and showback reports (configurable dimensions; exportable)
- **US4 (P4)** — Cost forecasts and anomaly detection

Each user story is independently testable per spec.md.

---

## Phase 1: Setup

- [ ] T001 Create new bounded-context directory `apps/control-plane/src/platform/cost_governance/` with subdirs `services/` and `jobs/`; add empty `__init__.py` to each (3 files); follow the standard BC layout from constitution § Bounded Context Structure
- [ ] T002 [P] Add `CostGovernanceSettings` extension to `apps/control-plane/src/platform/common/config.py`: `anomaly_evaluation_interval_seconds` (int, default 3600), `forecast_evaluation_interval_seconds` (int, default 3600), `override_token_ttl_seconds` (int, default 300), `minimum_history_periods_for_forecast` (int, default 4), `default_alert_thresholds` (list[int], default `[50, 80, 100]`), `default_currency` (str, default `"USD"`), `attribution_clickhouse_batch_size` (int, default 500), `attribution_clickhouse_flush_interval_seconds` (float, default 5.0); wire `FEATURE_COST_HARD_CAPS` env-var to `feature_cost_hard_caps` (bool, default False — already in constitution § Feature Flag Inventory line 885)
- [ ] T003 [P] Add canonical constants to `apps/control-plane/src/platform/cost_governance/constants.py`: `COST_TYPES = ("model","compute","storage","overhead")`; `BUDGET_PERIOD_TYPES = ("daily","weekly","monthly")`; `ANOMALY_TYPES = ("sudden_spike","sustained_deviation")`; `ANOMALY_SEVERITIES = ("low","medium","high","critical")`; `ANOMALY_STATES = ("open","acknowledged","resolved")`; `BLOCK_REASON_COST_BUDGET = "workspace_cost_budget_exceeded"` (consumed by gateway in US2); `KAFKA_TOPIC = "cost-governance.events"` (matches `{bc-name}.events` convention)

---

## Phase 2: Foundational (blocks every user story)

- [ ] T004 Create Alembic migration `apps/control-plane/migrations/versions/062_cost_governance.py` (rebase to current head at merge): creates `cost_attributions` (partitioned by month on `created_at`; `correction_of` self-FK for credit entries per rule 31; `total_cost_cents` GENERATED ALWAYS AS column per spec; `token_counts` JSONB; CHECK constraints `model_cost_cents >= 0` etc.; indexes `(workspace_id, created_at)`, `(execution_id)`, `(workspace_id, agent_id, created_at)`, partial `(workspace_id, created_at) WHERE correction_of IS NULL`); creates `workspace_budgets` (UNIQUE on `(workspace_id, period_type)` per spec; CHECK on `period_type IN BUDGET_PERIOD_TYPES`; `soft_alert_thresholds` JSONB default `[50, 80, 100]`); creates `budget_alerts` (UNIQUE on `(budget_id, threshold_percentage, period_start)` for once-per-period idempotency per FR-503.2; index `(workspace_id, triggered_at)`); creates `cost_forecasts` (index `(workspace_id, period_end DESC)`); creates `cost_anomalies` (`state` VARCHAR with CHECK; `acknowledged_at`, `acknowledged_by` nullable; `resolved_at` nullable; `correlation_fingerprint` VARCHAR for duplicate suppression per FR-504.4; partial index `(workspace_id, detected_at) WHERE state = 'open'`); adds `cost_budget` JSONB key to `workspace_settings` table comment (UX hint only — source of truth is `workspace_budgets`)
- [ ] T005 [P] Add SQLAlchemy models to `apps/control-plane/src/platform/cost_governance/models.py`: `CostAttribution`, `WorkspaceBudget`, `BudgetAlert`, `CostForecast`, `CostAnomaly`, `OverrideRecord` (FK columns to `workspaces.id`, `executions.id`, `users.id`, `agent_profiles.id`; **no cross-BC ORM relationships** — FK columns only per Principle IV)
- [ ] T006 [P] Add Pydantic schemas to `apps/control-plane/src/platform/cost_governance/schemas.py`: `CostAttributionRecord`, `CostAttributionCorrectionRequest`, `WorkspaceBudgetCreateRequest`, `WorkspaceBudgetResponse`, `BudgetAlertResponse`, `ChargebackReportRequest` (dimensions, time range, group_by), `ChargebackReportResponse`, `ChargebackExportRequest`, `CostForecastResponse`, `CostAnomalyResponse`, `AnomalyAcknowledgeRequest`, `OverrideIssueRequest`, `OverrideIssueResponse`, `BudgetCheckResult`; enum schemas for `CostType`, `BudgetPeriodType`, `AnomalyType`, `AnomalySeverity`, `AnomalyState`
- [ ] T007 [P] Add domain exceptions to `apps/control-plane/src/platform/cost_governance/exceptions.py`: `BudgetNotConfiguredError` → 404, `WorkspaceCostBudgetExceededError` (subclass of existing `BudgetExceededError` → 429 per `common/exceptions.py`), `OverrideExpiredError` → 410, `OverrideAlreadyRedeemedError` → 409, `InvalidBudgetConfigError` → 422, `InsufficientHistoryError` (forecasting; signalling, not user-facing)
- [ ] T008 [P] Add events to `apps/control-plane/src/platform/cost_governance/events.py`: payload classes `CostExecutionAttributedPayload`, `CostBudgetThresholdReachedPayload`, `CostBudgetExceededPayload`, `CostAnomalyDetectedPayload`, `CostForecastUpdatedPayload`; `CostGovernanceEventType` StrEnum mapping to the 5 strings already declared in constitution § Kafka Topics Registry lines 763–767; `register_cost_governance_event_types()` mirroring `analytics/events.py:43–52`; topic name `cost-governance.events`
- [ ] T009 Extend `apps/control-plane/src/platform/cost_governance/repository.py` (new file) with PostgreSQL access: `insert_attribution(...)`, `insert_attribution_correction(original_id, ...)`, `get_attribution_by_execution(execution_id)`, `get_workspace_attributions(workspace_id, since, until, cursor, limit)`, `aggregate_attributions(workspace_id, group_by, since, until)`, `get_active_budget(workspace_id, period_type)`, `list_budgets(workspace_id)`, `upsert_budget(...)`, `delete_budget(id)`, `record_alert(budget_id, threshold, period_start, period_end)` (uses ON CONFLICT DO NOTHING for once-per-period idempotency), `list_alerts(...)`, `insert_forecast(...)`, `get_latest_forecast(workspace_id)`, `insert_anomaly(...)`, `find_open_anomaly_by_fingerprint(workspace_id, fingerprint)` (duplicate suppression), `acknowledge_anomaly(id, by_user_id)`, `resolve_anomaly(id)`, `list_anomalies(workspace_id, state, limit, cursor)`
- [ ] T010 [P] Create `apps/control-plane/src/platform/cost_governance/clickhouse_setup.py` mirroring `analytics/clickhouse_setup.py:159–167`: `cost_events` DDL (`CREATE TABLE IF NOT EXISTS`, `MergeTree()`, `ORDER BY (workspace_id, occurred_at)`, `PARTITION BY toYYYYMM(occurred_at)`, `TTL occurred_at + INTERVAL 730 DAY` to satisfy spec assumption "at least one full annual finance cycle"); materialised views for `cost_hourly_by_workspace`, `cost_daily_by_workspace_agent`, `cost_daily_by_workspace_user`, `cost_daily_by_cost_type` (AggregatingMergeTree, identical pattern to `analytics_usage_hourly_v2`); idempotent `run_setup(client)` invoked at startup
- [ ] T011 [P] Create `apps/control-plane/src/platform/cost_governance/clickhouse_repository.py`: `insert_cost_events_batch(events)` using `AsyncClickHouseClient` from `common/clients/clickhouse.py` (`insert_batch` method); `query_cost_rollups(workspace_id, group_by, since, until)`; `query_cost_baseline(workspace_id, lookback_periods)` for anomaly evaluator; `query_workspace_history(workspace_id, periods)` for forecast trend
- [ ] T012 Create `CostGovernanceService` facade at `apps/control-plane/src/platform/cost_governance/service.py`: composes the 5 sub-services (attribution, chargeback, budget, forecast, anomaly); exposes `get_workspace_cost_summary(workspace_id, period_type, period_start)` and `evaluate_thresholds(workspace_id)` for the analytics-delegation hook (US1-T024); exposes `handle_workspace_archived(workspace_id)` for the workspaces archival hook (US1-T025); thin orchestration only — no business logic
- [ ] T013 [P] Wire dependency-injection providers in `apps/control-plane/src/platform/cost_governance/dependencies.py`: `get_cost_attribution_service`, `get_chargeback_service`, `get_budget_service`, `get_forecast_service`, `get_anomaly_service`, `get_cost_governance_service`, `get_clickhouse_cost_repository`, `get_redis_cost_client`; reuse `get_audit_chain_service` (UPD-024) and `get_alert_service` (feature 077) from their existing dependency modules
- [ ] T014 Mount `cost_governance/router.py` skeleton at `/api/v1/costs/*` per constitution § REST Prefix line 797; wire onto the FastAPI app in `apps/control-plane/src/platform/main.py`; register the event types via `register_cost_governance_event_types()` at app startup; register `clickhouse_setup.run_setup()` at app startup (idempotent); register the two APScheduler jobs (placeholders — implemented in US4)

---

## Phase 3: User Story 1 — Per-Execution Cost Attribution (P1) 🎯 MVP

**Story goal**: Every completed execution produces exactly one immutable attribution record with per-category breakdown summing to total; partial costs captured on failure; in-progress cost queryable; system-initiated executions handled.

**Independent test**: Trigger a sample of executions (model + storage + compute mix; success + failure + system-initiated; one long-running) across multiple workspaces; verify exactly one attribution row per completed execution, per-category sum equals total, in-progress cost visible during run, and the same row is reachable from both the execution detail view and a workspace-scoped cost query.

### Tests

- [ ] T015 [P] [US1] Add unit tests for `attribution_service` in `tests/control-plane/unit/cost_governance/test_attribution_service.py`: token→cost math from `ModelRouterResponse.tokens_in/out × ModelCatalogEntry.input_cost_per_1k_tokens/output_cost_per_1k_tokens` (US1-AS1); partial cost on step failure / cancellation (US1-AS2); late-arriving cost via additive credit-entry row referencing original via `correction_of` FK (rule 31, FR-501.5); shared-infra allocation rule produces a single attributed-workspace row, never a dropped cost (FR-501.6); system-initiated execution with no `initiator_user_id` produces a record with `user_id IS NULL` and an `origin` field set to `system_trigger` (US1-AS4)
- [ ] T016 [P] [US1] Add unit test `tests/control-plane/unit/cost_governance/test_event_registration.py`: all 5 `cost.*` event types registered against the global `event_registry` after `register_cost_governance_event_types()` call; payload schemas validate canonical correlation context

### Implementation

- [ ] T017 [US1] Implement `apps/control-plane/src/platform/cost_governance/services/attribution_service.py` with `AttributionService` class: `record_step_cost(*, execution_id, step_id, workspace_id, agent_id, user_id, payload)` extracts `model_id`, `tokens_in`, `tokens_out`, `duration_ms`, `bytes_written` from payload; resolves model pricing via `model_catalog.service.get_pricing(model_id)`; computes `model_cost_cents = (tokens_in × input_rate + tokens_out × output_rate) / 1000` (preserved as NUMERIC(12,4) — never float-rounded at write); compute and storage rates from `CostGovernanceSettings`; persists to `cost_attributions` synchronously (rule 38; AD-20); enqueues a ClickHouse `cost_events` row in the async batch buffer; emits `cost.execution.attributed` Kafka event via `EventProducer` from `common/events/`; `record_correction(original_attribution_id, *, deltas)` writes a credit-entry row with `correction_of=original_id` and signed `*_cost_cents` deltas; never mutates the original (rule 31); `get_execution_cost(execution_id)` returns the original + summed corrections
- [ ] T018 [US1] Hook `attribution_service.record_step_cost` into `apps/control-plane/src/platform/execution/service.py` `record_runtime_event` at ≈ line 570: insert the call AFTER the existing `_append_domain_event` and INSIDE the same SQLAlchemy transaction so attribution commits atomically with the journal append (FR-CC-2 + AD-20). Resolve workspace/agent/user from `execution` (already loaded in scope). Use the `payload` dict already available in the function. Surface failures as `structlog.warning` without aborting the journal append (cost write failure must not corrupt the journal — feature flag-able via `attribution_service.fail_open`)
- [ ] T019 [US1] Add ClickHouse async batch buffer to `clickhouse_repository.py`: in-memory queue flushed on `attribution_clickhouse_batch_size` rows OR `attribution_clickhouse_flush_interval_seconds` timer (whichever first); same pattern as `analytics_repository.insert_usage_events_batch`; flush on graceful shutdown via FastAPI lifespan
- [ ] T020 [US1] Implement REST endpoint `GET /api/v1/costs/executions/{execution_id}` in `cost_governance/router.py`: returns attribution record + correction summary; RBAC scoped to workspace membership via existing `require_workspace_member` dependency; returns 404 with no leakage if requester not in workspace; FR-501.3 latency target satisfied by single-row PG query
- [ ] T021 [US1] Implement REST endpoint `GET /api/v1/costs/workspaces/{workspace_id}/attributions` in `cost_governance/router.py`: cursor-paginated list; filters `since`, `until`, `agent_id`, `user_id`; joins to ClickHouse only for aggregations (use ClickHouse `query_cost_rollups` for any group-by request, PostgreSQL for raw row access)
- [ ] T022 [US1] Add integration test `tests/control-plane/integration/cost_governance/test_execution_records_attribution.py`: drive an execution through `execution.service` end-to-end with a mock model_router that emits known token counts; assert (a) exactly one PG `cost_attributions` row, (b) `cost_events` row in ClickHouse after batch flush, (c) `cost.execution.attributed` Kafka event observed by a test consumer, (d) per-category sum equals total
- [ ] T023 [US1] Add integration test `tests/control-plane/integration/cost_governance/test_attribution_corrections.py`: write attribution; submit a late-arriving compute cost via `record_correction`; assert the original is unchanged and `get_execution_cost` returns the summed net; assert downstream chargeback rollups (next phase) reconcile (will be re-asserted in US3)

### Analytics back-compat

- [ ] T024 [US1] Migrate `apps/control-plane/src/platform/analytics/service.py` `get_workspace_cost_summary` (≈ `:181–203`) and `check_budget_thresholds` (≈ `:205+`) to thin delegations into `CostGovernanceService.get_workspace_cost_summary` and `.evaluate_thresholds` respectively; preserve public method signatures and return shapes verbatim (rule 7); existing analytics tests must pass without modification; emit a structlog `info` log line on each call recording the delegation so the migration is traceable
- [ ] T025 [US1] Hook `workspaces/service.py` archival path to call `CostGovernanceService.handle_workspace_archived(workspace_id)` (no-op pass-through for now; just confirms cost data is retained — FR-CC-3); add unit assertion `tests/control-plane/integration/cost_governance/test_workspace_archival_preserves_costs.py`

**Checkpoint**: US1 deliverable. Every execution writes a durable, immutable attribution record reachable from execution detail and workspace cost queries. Constitution rule 12, rule 31, rule 38, AD-20 all satisfied. The two analytics helpers from feature 020 are now thin delegations; no two cost paths.

---

## Phase 4: User Story 2 — Budget Enforcement with Soft Alerts and Hard Caps (P2)

**Story goal**: Workspace admins configure per-period budgets; soft alerts fire once per threshold per period; hard cap (gated by `FEATURE_COST_HARD_CAPS`) refuses new starts with an actionable error and a documented override path; in-flight executions complete; concurrent starts at the cap are atomic; period rollover resets alert state.

**Independent test**: Configure a daily budget with thresholds [50, 80, 100] and hard cap enabled; drive synthetic load until each threshold is crossed; verify alerts fire exactly once per threshold per period; hard cap blocks new starts at 100; an authorised admin override admits a single critical execution and the override is audited.

### Tests

- [ ] T026 [P] [US2] Unit tests `tests/control-plane/unit/cost_governance/test_budget_service.py` covering: `evaluate_thresholds` fires each soft alert exactly once per period (FR-503.2); period rollover resets alert state and previously-fired thresholds can fire again (FR-503.7, US2-AS6); budget changed mid-period — previously-fired thresholds stay fired; raising a budget mid-period does not retroactively re-fire any threshold (spec edge case); lowering a budget mid-period that makes a previously-uncrossed threshold cross fires that threshold once (spec edge case)
- [ ] T027 [P] [US2] Unit tests for the override mechanism `tests/control-plane/unit/cost_governance/test_overrides.py`: `issue_override` writes a Redis nonce with `override_token_ttl_seconds` TTL and audits via `audit_chain_service` (rule 9, 32, 34 — double-audit including issuing admin AND workspace context); `redeem_override(token)` is single-shot (second redemption raises `OverrideAlreadyRedeemedError`); expired token raises `OverrideExpiredError`; override is bounded — redeeming admits exactly one start, never disables the cap (FR-503.5)
- [ ] T028 [P] [US2] Unit tests for atomic admit-or-refuse `tests/control-plane/unit/cost_governance/test_concurrent_admit.py` (in-process; full integration is T034): 20 concurrent calls to `check_budget_for_start` near the cap result in either all admitted (if all fit) or N admitted + (20-N) refused; never admits more than budget allows (FR-503.6); test uses a fakeredis with the Lua atomic decrement script

### Implementation

- [ ] T029 [US2] Implement `apps/control-plane/src/platform/cost_governance/services/budget_service.py` with `BudgetService` class:
  - `configure(workspace_id, period_type, budget_cents, soft_alert_thresholds, hard_cap_enabled, admin_override_enabled)` — writes `workspace_budgets` (UPSERT on UNIQUE constraint); audits via `audit_chain_service`; validates thresholds are sorted ascending and ≤ 100; emits no Kafka event for config changes (audit chain is the system of record for governance changes)
  - `evaluate_thresholds(workspace_id)` — computes current period spend (PG query for authoritative truth, then primes Redis hot counter); compares against each threshold; for each newly-crossed threshold, atomically inserts a `budget_alerts` row (ON CONFLICT DO NOTHING for once-per-period idempotency per FR-503.2); on insert success, emits `cost.budget.threshold.reached` and routes notification via `AlertService.process_state_change` (feature 077) targeting workspace admins resolved via `WorkspacesRepository.list_members(role=admin)`
  - `check_budget_for_start(workspace_id, estimated_cost_cents, override_token=None)` — fast-path Redis Lua atomic INCRBY-and-test against `cost:budget:{workspace_id}:{period_type}:{period_start}` (perf goal ≤ 5 ms p95); on Redis miss, fall back to PG `cost_attributions` SUM and prime; if `hard_cap_enabled` and projected post-spend > budget, return `BudgetCheckResult(allowed=False, block_reason="workspace_cost_budget_exceeded", override_endpoint="/api/v1/costs/workspaces/{ws}/budget/override")`; if `override_token` is present, call `redeem_override` and admit on success; emit `cost.budget.exceeded` ONCE per period on first refusal
  - `issue_override(workspace_id, requested_by, reason)` — generates a nonce; SETEX in Redis with TTL `override_token_ttl_seconds`; double-audits via `audit_chain_service` (acting admin + workspace context, rule 34); returns the token to the admin via API response (the token IS the auth — clients store it for the next start)
  - `redeem_override(token)` — atomic Redis DEL via Lua (returns 1 on existed-and-deleted, 0 otherwise); raises `OverrideAlreadyRedeemedError` on 0; audits redemption
  - `invalidate_hot_counter(workspace_id, period_type)` — called after every attribution write so the next gateway check sees fresh truth (constitution § Integration Constraints)
- [ ] T030 [US2] Add Redis Lua script `apps/control-plane/src/platform/cost_governance/services/_budget_atomic.lua`: atomic INCRBY-and-test (load via `redis.script_load` once at startup, EVALSHA per call); covers the concurrent-start-at-cap atomicity guarantee (FR-503.6); a second small script for atomic single-shot override redemption (`GETDEL` semantics — fall back to MULTI/EXEC on Redis < 6.2)
- [ ] T031 [US2] Hook `BudgetService.invalidate_hot_counter` into `AttributionService.record_step_cost` after the synchronous PG insert (T017) — keeps Redis consistent with PG truth without polling
- [ ] T032 [US2] Insert the new check into `apps/control-plane/src/platform/policies/gateway.py` between Purpose check (≈ `:154`) and the existing tool-invocation budget check (≈ `:156`): new private method `_check_workspace_cost_budget(workspace_id, estimated_cost_cents)` calls `BudgetService.check_budget_for_start`; on block, returns the existing `_blocked()` envelope with `block_reason="workspace_cost_budget_exceeded"` and the override endpoint URL in the result body (FR-503.3); only runs when `FEATURE_COST_HARD_CAPS` is True (rule 8); never runs on tool calls inside an already-running execution (FR-503.4 — in-flight executions complete)
- [ ] T033 [US2] Implement REST endpoints in `cost_governance/router.py`:
  - `POST /api/v1/costs/workspaces/{workspace_id}/budgets` — workspace_admin only; calls `BudgetService.configure`
  - `GET /api/v1/costs/workspaces/{workspace_id}/budgets` — workspace member; lists per-period configs
  - `DELETE /api/v1/costs/workspaces/{workspace_id}/budgets/{period_type}` — workspace_admin only
  - `GET /api/v1/costs/workspaces/{workspace_id}/alerts` — workspace member; cursor-paginated alert history
  - `POST /api/v1/costs/workspaces/{workspace_id}/budget/override` — workspace_admin only; body `{reason}`; returns `{token, expires_at}`
  - All endpoints emit audit-chain entries on mutating actions
- [ ] T034 [US2] Add integration test `tests/control-plane/integration/cost_governance/test_tool_gateway_cost_check.py`: configure budget with hard cap; drive PG attribution to 99% of budget; assert next gateway start is admitted; push to 100%; assert next start refused with `block_reason="workspace_cost_budget_exceeded"` and the override URL; in-flight execution from before the cap continues to completion (FR-503.4); issue override, redeem, assert next start admitted; second redemption raises 409
- [ ] T035 [US2] Add integration test `tests/control-plane/integration/cost_governance/test_concurrent_starts_at_cap.py`: 50 concurrent gateway starts when 20 fit under the cap; assert exactly 20 admitted and 30 refused; assert PG sum never exceeds budget by more than the documented race tolerance; uses real Redis from the test fixture
- [ ] T036 [US2] Add integration test `tests/control-plane/integration/cost_governance/test_budget_alerts_lifecycle.py`: drive cumulative spend across thresholds 50/80/100; assert each `budget_alerts` row inserted exactly once; assert each `cost.budget.threshold.reached` Kafka event observed exactly once; assert `AlertService.process_state_change` called with workspace admin recipients (mocked); rollover the period (advance fake clock) and assert thresholds can fire again

**Checkpoint**: US2 deliverable. Soft alerts fire once-per-threshold-per-period; hard cap blocks new starts atomically under contention; bounded admin override audited end-to-end. `FEATURE_COST_HARD_CAPS` gates only the enforcement (alerts always on).

---

## Phase 5: User Story 3 — Chargeback and Showback Reports (P3)

**Story goal**: Authorised users generate cost reports aggregated by configurable dimensions over configurable time ranges; totals reconcile exactly to underlying attribution; reports exportable; visibility filtered at the data layer.

**Independent test**: With ≥ 1 month of attribution data, generate a chargeback report grouped by workspace + cost type for the prior month; verify totals reconcile to summed underlying rows; export and confirm a downstream-parseable structure; attempt a workspace filter the requester cannot see and confirm the unauthorised workspaces are excluded with no leakage.

### Tests

- [ ] T037 [P] [US3] Unit tests `tests/control-plane/unit/cost_governance/test_chargeback_service.py`: reconciliation across all supported group-by combinations (workspace, agent, user, cost_type, day/week/month buckets) — sum of grouped rows equals SELECT SUM of raw attributions in the same RBAC scope (FR-502.2, SC-005); RBAC filter applied at the SQL/CH WHERE level — unauthorised workspace rows never reach the aggregator (FR-502.4, SC-009); export shape includes dimensions + time range + per-category breakdown + totals (FR-502.3, US3-AS3); credit-entry corrections from US1 are netted into the totals correctly

### Implementation

- [ ] T038 [US3] Implement `apps/control-plane/src/platform/cost_governance/services/chargeback_service.py` `ChargebackService.generate_report(*, requester, dimensions, group_by, since, until, workspace_filter=None)`: resolves visible workspaces from `workspaces.service.list_visible_for(requester)` (in-process); applies the visibility set as a WHERE clause inside the ClickHouse `query_cost_rollups` call (NOT post-filter — FR-502.4); returns a `ChargebackReport` with `dimensions`, `time_range`, `group_by`, `rows`, `totals`, `currency`, `generated_at`; nets credit corrections via the same query (`SUM(model_cost_cents) - SUM(correction_credit_cents)` per group)
- [ ] T039 [US3] Implement `ChargebackService.export_report(report, format)` supporting `format="csv"` (default, RFC 4180) and `format="ndjson"`; both include the dimensions, time range, per-category breakdown, totals, and currency; never embeds RBAC-out-of-scope rows (defence-in-depth assertion in the export path); filename schema `chargeback-{workspace_id_or_all}-{since}-{until}.{ext}`
- [ ] T040 [US3] Implement REST endpoint `POST /api/v1/costs/reports/chargeback` in `cost_governance/router.py`: synchronous for ≤ 90-day windows; for larger ranges, returns 202 with a job id (deferred — can be a follow-up; v1 cap is 90 days documented in the response). Body: `ChargebackReportRequest`. Response: `ChargebackReportResponse`. Audit-chain entry on every successful generation (rule 9 — bulk cost data access by an admin)
- [ ] T041 [US3] Implement REST endpoint `POST /api/v1/costs/reports/chargeback/export` in `cost_governance/router.py`: returns `application/octet-stream` (or `text/csv` / `application/x-ndjson` based on format) with `Content-Disposition: attachment; filename=...`; audit-chain entry includes the export format and row count (no row contents)
- [ ] T042 [US3] Add integration test `tests/control-plane/integration/cost_governance/test_chargeback_report_api.py`: seed 30 days of attributions across 3 workspaces × 4 cost types; generate report grouped by workspace + cost_type; assert totals reconcile to PG SUM(); export CSV and parse; assert output rows match report rows; submit a request with a workspace filter the requester cannot view → response excludes those rows AND does not mention them in error / 404 (no enumeration leakage)

**Checkpoint**: US3 deliverable. Reports reconcile exactly to attribution; RBAC enforced at the SQL layer; CSV + NDJSON exports work end-to-end.

---

## Phase 6: User Story 4 — Cost Forecasts and Anomaly Detection (P4)

**Story goal**: Forward-looking forecast of end-of-period spend with confidence range; anomalies (sudden spikes, sustained deviations) detected and recorded with baseline-vs-observed comparison and notification; duplicate alerts suppressed; new workspaces not flagged on first use; insufficient-history forecasts clearly low-confidence.

**Independent test**: Seed a workspace with a steady cost trend over multiple periods; inject a controlled spike; verify the forecast for the current period reflects the historical trend before the spike; the spike triggers an anomaly notification with baseline + observed; the forecast updates after the spike is incorporated; a brand-new workspace is not flagged.

### Tests

- [ ] T043 [P] [US4] Unit tests `tests/control-plane/unit/cost_governance/test_forecast_service.py`: trend-based forecast with steady history matches expected within ε; outlier resilience — a single 10× spike in history does not move the forecast more than the documented dampening factor (spec edge case "extreme outliers"); insufficient history (< `minimum_history_periods_for_forecast`) returns `ForecastResponse(confidence="insufficient_history", value=None)` not a misleading number (FR-504.2); confidence range widens with volatility
- [ ] T044 [P] [US4] Unit tests `tests/control-plane/unit/cost_governance/test_anomaly_service.py`: `sudden_spike` detection — observed > baseline × spike_multiplier triggers an anomaly row with severity per configured bands (FR-504.3); `sustained_deviation` detection — N consecutive evaluation windows above threshold triggers; duplicate suppression — if an open anomaly with the same `correlation_fingerprint` exists, no new row and no new alert (FR-504.4); acknowledge transitions state to `acknowledged`; resolve transitions to `resolved` and the same fingerprint can re-fire (FR-504.5); brand-new workspace with zero history is skipped (FR-504.6, US4-AS — "Anomaly during onboarding")

### Implementation

- [ ] T045 [US4] Implement `apps/control-plane/src/platform/cost_governance/services/forecast_service.py` `ForecastService`:
  - `compute_forecast(workspace_id)` — pulls history from ClickHouse `query_workspace_history`; if periods < `minimum_history_periods_for_forecast`, persists a `cost_forecasts` row with `confidence_interval={"status":"insufficient_history"}` and `forecast_cents=NULL`; otherwise applies trimmed-mean trend + linear regression (numpy/scipy — already in the requirement set), computes 80% confidence interval, projects to current period end; persists; emits `cost.forecast.updated`
  - `get_latest_forecast(workspace_id)` — reads `cost_forecasts` ordered by `computed_at DESC` LIMIT 1; returns response including `freshness` (computed_at age)
- [ ] T046 [US4] Implement `apps/control-plane/src/platform/cost_governance/services/anomaly_service.py` `AnomalyService`:
  - `detect(workspace_id)` — pulls baseline (rolling N-period median) from ClickHouse; pulls latest window observed value; computes `correlation_fingerprint = hash(workspace_id, window_bucket, anomaly_type, severity_band)`; if matching open anomaly exists, no-op (FR-504.4); else inserts `cost_anomalies` row with type/severity/baseline/observed/summary; emits `cost.anomaly.detected`; routes notification via `AlertService.process_state_change` to workspace admins
  - `acknowledge(anomaly_id, by_user_id)`, `resolve(anomaly_id)` — state transitions; audit-chain entry on each
  - `list_anomalies(workspace_id, state, ...)` — for the dashboard / API
- [ ] T047 [US4] Implement APScheduler jobs in `cost_governance/jobs/forecast_job.py` and `cost_governance/jobs/anomaly_job.py`: per-workspace iteration on the configured intervals; bounded concurrency (semaphore = 8); structured-log start/end with workspace count and durations; jobs run on the existing `scheduler` runtime profile only (guard via `settings.runtime_profile == "scheduler"`)
- [ ] T048 [US4] Implement REST endpoints in `cost_governance/router.py`:
  - `GET /api/v1/costs/workspaces/{workspace_id}/forecast` — returns latest forecast or 404 with `insufficient_history` code; never returns a misleading number (FR-504.2)
  - `GET /api/v1/costs/workspaces/{workspace_id}/anomalies?state=open` — cursor paginated
  - `POST /api/v1/costs/anomalies/{anomaly_id}/acknowledge` — body `{notes}`; workspace_admin only
  - `POST /api/v1/costs/anomalies/{anomaly_id}/resolve` — workspace_admin only
- [ ] T049 [US4] Add integration test `tests/control-plane/integration/cost_governance/test_anomaly_lifecycle_api.py`: seed steady history; inject a spike; trigger `detect` directly; assert one anomaly row + one `cost.anomaly.detected` event + alert routed; trigger `detect` again with the same spike still active; assert no new row + no new alert (suppression); acknowledge; verify state transitions; resolve; verify a subsequent re-occurrence creates a new anomaly
- [ ] T050 [US4] Add integration test `tests/control-plane/integration/cost_governance/test_forecast_lifecycle.py`: seed insufficient history → assert response signals `insufficient_history` (FR-504.2, US4-AS3); seed sufficient steady history → forecast exists with reasonable confidence interval; advance attribution data; trigger forecast job; assert forecast freshness updates

**Checkpoint**: US4 deliverable. Forecasts have explicit confidence handling; anomalies detect, suppress duplicates, and lifecycle through ack/resolve.

---

## Phase 7: Frontend `/costs/`

**Story goal**: Surface attribution, budgets, chargeback, forecast, and anomaly data through a workspace-admin-friendly UI distinct from `/analytics/` (feature 049). Satisfies rule 45 (every backend has a UI).

- [ ] T051 [P] Create `apps/web/lib/api/costs.ts`: typed wrappers over `/api/v1/costs/*` matching `CostAttributionRecord`, `WorkspaceBudgetResponse`, `ChargebackReportResponse`, `CostForecastResponse`, `CostAnomalyResponse`, `BudgetAlertResponse`; reuse the shared `apiClient` and JWT injection from `lib/api.ts`
- [ ] T052 [P] Create `apps/web/components/features/cost-governance/CostBreakdownChart.tsx` (Recharts stacked bar by cost type), `BudgetThresholdGauge.tsx` (current spend vs budget with threshold markers), `ForecastChart.tsx` (line chart with confidence interval ribbon, low-confidence empty state), `AnomalyCard.tsx` (severity badge, baseline vs observed, ack/resolve actions), `BudgetConfigForm.tsx` (RHF + Zod, period type radio, threshold multi-input, hard cap toggle), `OverrideDialog.tsx` (reason textarea required, returns + displays expiry countdown), `ChargebackReportBuilder.tsx` (group-by checkboxes, date range picker, export button)
- [ ] T053 [US-FE] Create `apps/web/app/(main)/costs/page.tsx`: dashboard surfacing `MetricCard` grid (period spend, % of budget, forecast, open anomalies count), `CostBreakdownChart`, `BudgetThresholdGauge` per active period, top-N agents/users tables, anomaly feed; uses TanStack Query hooks `useWorkspaceCostSummary`, `useLatestForecast`, `useOpenAnomalies`
- [ ] T054 [US-FE] Create `apps/web/app/(main)/costs/budgets/page.tsx`: workspace-admin-only (route guard via existing layout pattern); list per-period budgets; create/edit/delete via `BudgetConfigForm` in a Sheet; alert history table; `OverrideDialog` accessible from a "Request Override" button
- [ ] T055 [US-FE] Create `apps/web/app/(main)/costs/reports/page.tsx`: chargeback report builder via `ChargebackReportBuilder`; preview table; CSV / NDJSON export download triggered via `apiClient` blob fetch; result viewer with reconciliation hint
- [ ] T056 [US-FE] Create `apps/web/app/(main)/costs/anomalies/[id]/page.tsx`: detail view with baseline vs observed chart, summary, ack/resolve actions, audit history snippet; `useAnomaly(id)` hook
- [ ] T057 [P] [US-FE] Vitest + RTL component tests for `BudgetThresholdGauge` (color transitions at 50/80/100), `BudgetConfigForm` (Zod validation: thresholds sorted ascending, ≤ 100; period type required), `ForecastChart` (low-confidence empty state); MSW-mocked API tests for the dashboard happy path
- [ ] T058 [US-FE] Playwright E2E test `apps/web/tests/e2e/costs.spec.ts`: workspace-admin happy path — log in → navigate to `/costs/budgets` → create a daily budget → drive synthetic load via dev-only seed endpoint (gated by `FEATURE_E2E_MODE` per constitution Critical Reminder 26) → see threshold gauge update → see soft alert in alert history; the hard-cap path is covered by backend integration test T034 (E2E does not need to re-cover it)

**Checkpoint**: Rule 45 satisfied for this feature in-PR (workspace-admin budget config also surfaces in UPD-043 via coordination — not blocking).

---

## Phase 8: Polish & Cross-Cutting

- [ ] T059 [P] Create Grafana dashboard JSON `deploy/helm/observability/templates/dashboards/cost-governance.json` (rules 24, 27): panels for attribution write rate (per workspace, per second), budget threshold crossings per period, hard-cap blocks (counter), anomaly count by severity, forecast vs actual delta, ClickHouse batch flush latency; labels limited to `service`, `bounded_context`, `level`, `namespace`, `pod` (rule 22 — `workspace_id` in JSON payload only); ConfigMap with `grafana_dashboard: "1"` label
- [ ] T060 [P] Add OpenAPI tags `cost-governance-attributions`, `cost-governance-budgets`, `cost-governance-reports`, `cost-governance-forecasts`, `cost-governance-anomalies` and ensure all `/api/v1/costs/*` routers carry them
- [ ] T061 [P] Wire E2E suite directory `tests/e2e/suites/cost_governance/` (constitution rule 25): `test_attribution_visible_during_run.py` (US1-AS3), `test_hard_cap_blocks_then_override.py` (US2-AS3 + US2-AS4), `test_anomaly_alert_routes_to_admin.py` (US4 + feature 077 cross-BC); reuse the existing journey crossing-point fixture from feature 071 (`tests/e2e/`); at least one journey MUST exercise the new BC at a boundary crossing (rule 25)
- [ ] T062 [P] Run `ruff check apps/control-plane/src/platform/cost_governance` and `mypy --strict apps/control-plane/src/platform/cost_governance`; resolve all findings; assert no `os.getenv` for `*_SECRET` / `*_API_KEY` outside SecretProvider files (rule 39 — none expected here, but verify)
- [ ] T063 [P] Run `pytest tests/control-plane/unit/cost_governance tests/control-plane/integration/cost_governance -q`; verify ≥ 95% line coverage on `apps/control-plane/src/platform/cost_governance/` (constitution § Quality Gates)
- [ ] T064 [P] Smoke-run the `quickstart.md` walkthrough (configure budget → run synthetic load → observe alert → trigger anomaly → ack) against a local control plane; capture deviations and update `quickstart.md` or behaviour accordingly
- [ ] T065 Update `CLAUDE.md` Recent Changes via `bash .specify/scripts/bash/update-agent-context.sh` so future agent context reflects this BC; verify the entry mentions the analytics-delegation migration so future planners do not reintroduce a parallel cost path

---

## Dependencies

```
Phase 1 (Setup) ──▶ Phase 2 (Foundational) ──▶ Phase 3 (US1, P1) ──▶ Checkpoint MVP
                                                       │
                                                       ▼
                                              ┌──────────────────────┐
                                              │ Phase 4 US2 (P2)     │ — depends on US1 (attribution feeds budget)
                                              │ Phase 5 US3 (P3)     │ — depends on US1 (rollups read attribution)
                                              │ Phase 6 US4 (P4)     │ — depends on US1 (forecast/anomaly read history)
                                              └──────────────────────┘
                                                       │
                                                       ▼
                                              Phase 7 (Frontend `/costs/`)
                                                       │
                                                       ▼
                                                Phase 8 (Polish)
```

**MVP scope**: Phase 1 + Phase 2 + Phase 3 = 25 tasks. Delivers per-execution attribution end-to-end with no behaviour change for callers. Budget enforcement (US2), reports (US3), and forecasting/anomalies (US4) ship in subsequent waves.

**Parallel opportunities**:
- Phase 1: T002 ∥ T003 (different files).
- Phase 2: T005 ∥ T006 ∥ T007 ∥ T008 ∥ T010 ∥ T011 ∥ T013 (independent files); T009 / T012 / T014 sequential after their inputs land.
- Phase 3: T015 ∥ T016 (test-only); T017 sequential (core service); T018 / T019 / T020 / T021 mostly parallel after T017; T022 / T023 sequential after T017–T019; T024 / T025 parallel.
- Phase 4: T026 ∥ T027 ∥ T028 (test-only); T029 sequential (core); T030 ∥ T031 after T029; T032 sequential (gateway integration); T033 (REST) parallel to integration tests T034 / T035 / T036.
- Phase 5: T037 (tests) parallel to T038 / T039 (impl); T040 / T041 / T042 sequential after T038.
- Phase 6: T043 ∥ T044 (test-only); T045 ∥ T046 (impl, different files); T047 / T048 after T045 + T046; T049 / T050 sequential.
- Phase 7: T051 ∥ T052 ∥ T057 (lib + components + tests); T053 / T054 / T055 / T056 (pages) parallel after T051 + T052; T058 sequential at the end.
- Phase 8: T059 ∥ T060 ∥ T061 ∥ T062 ∥ T063 ∥ T064 (independent surfaces); T065 last.

---

## Implementation strategy

1. **Wave A (MVP — US1)** — Phases 1, 2, 3. One backend dev. Delivers per-execution attribution including the analytics back-compat migration (T024). After Wave A, every execution writes a durable attribution record and existing analytics callers see no behaviour change.
2. **Wave B (US2 — enforcement)** — Phase 4. One backend dev. Soft alerts always-on; hard cap behind `FEATURE_COST_HARD_CAPS`. Atomicity (T030, T035) is the highest-risk task — pair-review.
3. **Wave C (US3 + US4 in parallel)** — Phases 5 and 6. Two backend devs. US3 (chargeback) and US4 (forecast + anomaly) are independent except both read from the same `cost_events` ClickHouse table; coordinate on the rollup view names.
4. **Wave D (Frontend)** — Phase 7. One frontend dev. Can start as soon as the REST contracts from Phases 3–6 are merged; no need to wait for Wave C completion if scoped per page.
5. **Wave E (Polish)** — Phase 8. Dashboard, OpenAPI tags, E2E, lint/types/coverage gates, smoke-run, agent-context update.

**Constitution coverage matrix**:

| Rule / AD | Where applied | Tasks |
|---|---|---|
| 1, 4, 5 (brownfield) | All — extends `execution`, `policies`, `analytics`, `workspaces`; new BC `cost_governance` | T017, T018, T024, T025, T032 |
| 2 (Alembic only) | Phase 2 | T004 |
| 6 (additive enums) | Phase 1 | T003 (string constants, no enum mutation; gateway block_reason is a string literal) |
| 7 (backwards compat) | Phase 3 | T024 (analytics signatures preserved) |
| 8 (feature flags) | Phase 4 | T032 (gateway hard-cap gated by `FEATURE_COST_HARD_CAPS`) |
| 9 (PII / sensitive op audit) | Phase 4, 5 | T027 (override audit), T040 (chargeback bulk-export audit) |
| 11 (LLM through model_router) | Phase 3 | T017 (token counts read from `ModelRouterResponse`, never provider SDK) |
| 12 (cost-incurring action records attribution) | Phase 3 | T017, T018 (hook in `execution.service`) |
| 18 (residency at query time) | Phase 5 | T038 (chargeback respects workspace residency on read) |
| 20, 22 (structured JSON logs, low-cardinality labels) | All Python files | T017 (workspace_id in payload, never label); T059 (dashboard label policing) |
| 21 (correlation IDs context-managed) | Phase 3 | T017 (carries existing CorrelationContext on attribution write) |
| 23 (no secrets in logs) | All — N/A (no secrets handled by this BC) | T062 (CI verification) |
| 24, 27 (BC dashboard via Helm) | Phase 8 | T059 |
| 25 (E2E suite + journey crossing) | Phase 8 | T061 |
| 31, 38 (cost cumulative; never modify past attributions) | Phase 3 | T017 (record_correction creates credit-entry; never UPDATE the original); T015 (test) |
| 32 (audit chain on config changes) | Phase 4 | T029 (configure / override actions); T030 |
| 34 (impersonation / overrides double-audit) | Phase 4 | T027, T029 (override audit includes acting admin AND workspace context) |
| 36 (UX-impacting FR documented) | Phase 8 | T064 (quickstart) + T065 (CLAUDE.md) — docs site update tracked in PR description |
| 38 (every cost-incurring step calls attribution_service) | Phase 3 | T018 |
| 45 (backend has UI) | Phase 7 | T053–T056 |
| 50 (mock LLM for previews) | N/A — this BC performs no LLM calls | — |
| AD-20 (per-execution cost synchronous at commit) | Phase 3 | T018 (call inside the same DB transaction as journal append) |

---

## Notes

- The `[Story]` tag maps each task to its user story (US1, US2, US3, US4, or US-FE for frontend tasks that span stories) so independent delivery is preserved.
- Constitution rule 12 names `cost_governance/services/attribution_service.py` as the canonical implementation that ALL cost-incurring actions must call. T017 is therefore not just adding a new service — it is implementing the contract the rest of the platform already presumes exists.
- The 5 Kafka event types and the `/api/v1/costs/*` REST prefix and `FEATURE_COST_HARD_CAPS` feature flag are ALREADY declared in the constitution (lines 763–767, 797, 885). T008 / T014 / T032 implement what is already named — do not invent new names.
- Migration `062_cost_governance.py` MUST rebase to the current alembic head at merge time (latest at branch cut: `061_content_safety_fairness`).
- The analytics-delegation migration (T024) is the single most important guard against future drift: without it, two cost paths exist and SC-005 (reconciliation) becomes unenforceable.
