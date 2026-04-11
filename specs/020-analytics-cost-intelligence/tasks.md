# Tasks: Analytics and Cost Intelligence

**Input**: Design documents from `specs/020-analytics-cost-intelligence/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/analytics-api.md ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story. Tests included (spec requires ≥95% coverage).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)

---

## Phase 1: Setup (Package Structure + Storage Schema)

**Purpose**: Create the `analytics` package skeleton, ClickHouse DDL, and PostgreSQL migration — no business logic yet.

- [x] T001 Create `apps/control-plane/src/platform/analytics/` package with empty stubs: `__init__.py`, `models.py`, `schemas.py`, `service.py`, `repository.py`, `router.py`, `events.py`, `exceptions.py`, `dependencies.py`, `consumer.py`, `clickhouse_setup.py`, `recommendation.py`, `forecast.py`
- [x] T002 [P] Implement `apps/control-plane/src/platform/analytics/clickhouse_setup.py`: idempotent `CREATE TABLE IF NOT EXISTS` for `analytics_usage_events` (MergeTree, ORDER BY `(toYYYYMM(timestamp), workspace_id, agent_fqn)`) and `analytics_quality_events` (MergeTree), plus `CREATE MATERIALIZED VIEW IF NOT EXISTS` for `analytics_usage_hourly`, `analytics_usage_daily`, `analytics_usage_monthly` (all AggregatingMergeTree with countState/sumState/avgState aggregate functions) — see data-model.md §2 for exact DDL
- [x] T003 [P] Create Alembic migration `apps/control-plane/migrations/versions/005_analytics_cost_models.py`: `analytics_cost_models` table (UUID PK, model_id, provider, display_name, input_token_cost_usd Numeric(18,10), output_token_cost_usd Numeric(18,10), per_second_cost_usd nullable, is_active bool, valid_from timestamptz, valid_until nullable), index on `(model_id, is_active)`, partial unique index `UNIQUE(model_id) WHERE is_active=true`, seed pricing rows for gpt-4o/claude-3-5-sonnet/claude-3-5-haiku/gemini-2.0-flash

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared models, schemas, exceptions, and repository infrastructure used by all user stories.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 [P] Implement `CostModel` SQLAlchemy model in `apps/control-plane/src/platform/analytics/models.py`: all columns per data-model.md §1.1, using `Base, UUIDMixin, TimestampMixin, AuditMixin`, `__tablename__ = "analytics_cost_models"`
- [x] T005 [P] Implement base Pydantic schemas in `apps/control-plane/src/platform/analytics/schemas.py`: `Granularity(StrEnum)`, `RecommendationType(StrEnum)`, `ConfidenceLevel(StrEnum)`, `CostModelCreate`, `CostModelResponse`, `UsageQueryParams`, `CostIntelligenceParams`, `ForecastParams`, `RecommendationsParams` — all per data-model.md §3
- [x] T006 [P] Implement exceptions in `apps/control-plane/src/platform/analytics/exceptions.py`: `AnalyticsError`, `WorkspaceAuthorizationError`, `AnalyticsStoreUnavailableError` with appropriate HTTP status codes and error_codes matching contracts/analytics-api.md
- [x] T007 Implement `CostModelRepository` (SQLAlchemy) and `AnalyticsRepository` class skeleton (ClickHouse) in `apps/control-plane/src/platform/analytics/repository.py`: `CostModelRepository` with `get_active_pricing(model_id)` and `list_all()` methods; `AnalyticsRepository.__init__` accepting `clickhouse_connect.Client`; stub method signatures for all query methods
- [x] T008 Implement `get_analytics_service()` and `get_analytics_repository()` FastAPI DI factories in `apps/control-plane/src/platform/analytics/dependencies.py` (singletons scoped to app lifespan, injecting ClickHouse client from `common/clients/clickhouse.py`)

**Checkpoint**: Foundation ready — all user story phases can now proceed.

---

## Phase 3: User Story 1 — Usage Data Pipeline and Visibility (Priority: P1) 🎯 MVP

**Goal**: Kafka consumer ingests runtime events → ClickHouse. REST endpoint returns workspace usage rollups with time/agent/model filters.

**Independent Test**: Produce several `workflow.runtime` Kafka events. Verify rows appear in `analytics_usage_events` within 5 seconds. Query `GET /api/v1/analytics/usage?workspace_id=...&start_time=...&end_time=...&granularity=daily` — verify rollup totals match produced events. Query with a different workspace_id — verify no data returned (workspace isolation).

- [x] T009 [P] [US1] Implement `AnalyticsRepository.insert_usage_events_batch(events: list[dict])` and `AnalyticsRepository.query_usage_rollups(workspace_id, granularity, start_time, end_time, agent_fqn, model_id, limit, offset)` in `apps/control-plane/src/platform/analytics/repository.py`: `insert_usage_events_batch` calls `client.insert("analytics_usage_events", rows, column_names=[...])`; `query_usage_rollups` queries the appropriate materialized view (`analytics_usage_hourly`/`analytics_usage_daily`/`analytics_usage_monthly`) using `countMerge()`/`sumMerge()` + WHERE on workspace_id + time range
- [x] T010 [US1] Implement `AnalyticsPipelineConsumer` in `apps/control-plane/src/platform/analytics/consumer.py`: `AIOKafkaConsumer` on `workflow.runtime` + `runtime.lifecycle` topics with consumer group `analytics-pipeline`; accumulate events in list buffer; flush trigger: 100 events OR 5 seconds (`asyncio.wait_for`); `_extract_usage_event(envelope)` extracts `execution_id`, `workspace_id`, `agent_fqn`, `model_id`, `input_tokens`, `output_tokens`, `execution_duration_ms`, `self_correction_loops`, `reasoning_tokens`; `_compute_cost(tokens_in, tokens_out, duration_ms, model_id)` reads pricing from in-memory `CostModelRepository` cache (refresh every 300s); failed batch → exponential backoff (1s, 2s, 4s) → DLQ after 3 failures via `common/events/retry.py`
- [x] T011 [US1] Add `UsageRollupItem`, `UsageResponse` Pydantic schemas to `apps/control-plane/src/platform/analytics/schemas.py`
- [x] T012 [US1] Implement `AnalyticsService.get_usage(params, user_id)` in `apps/control-plane/src/platform/analytics/service.py`: validate `params.workspace_id in await workspaces_service.get_user_workspace_ids(user_id)` → raise `WorkspaceAuthorizationError` if not; call `AnalyticsRepository.query_usage_rollups()`; return `UsageResponse`
- [x] T013 [US1] Implement `GET /api/v1/analytics/usage` in `apps/control-plane/src/platform/analytics/router.py`: FastAPI router with workspace_id + time range + granularity + pagination query params; call `analytics_service.get_usage()`; return 200 with `UsageResponse` or 403/400/503 per contracts/analytics-api.md
- [x] T014 [P] [US1] Write unit tests for cost computation logic in `apps/control-plane/tests/unit/test_analytics_cost_computation.py`: correct cost for known token counts + pricing; zero-token events; model not found (fallback/error); pricing cache refresh
- [x] T015 [US1] Write integration tests for pipeline ingestion and usage query in `apps/control-plane/tests/integration/test_analytics_pipeline.py` + `tests/integration/test_analytics_usage_query.py`: Kafka event → ClickHouse within 5s; rollup values match event totals; cross-workspace isolation (403); hourly/daily/monthly granularity returns correct groupings; empty workspace returns 200 with empty items

**Checkpoint**: US1 complete — pipeline ingesting, rollups computing, usage endpoint working.

---

## Phase 4: User Story 2 — Cost-Per-Quality Analysis (Priority: P1)

**Goal**: Consume `evaluation.events` to ingest quality scores. Add `GET /analytics/cost-intelligence` returning cost-per-quality ratios ranked by efficiency.

**Independent Test**: Seed usage events and quality events for two agents on different models. Query `GET /api/v1/analytics/cost-intelligence`. Verify cost-per-quality values are `total_cost / avg_quality_score`. Verify ranking is ascending by cost_per_quality. Verify agent with no quality data shows `null` for ratio and appears last in ranking.

- [x] T016 [US2] Extend `AnalyticsPipelineConsumer` in `apps/control-plane/src/platform/analytics/consumer.py` to also consume `evaluation.events` topic: add `_extract_quality_event(envelope)` extracting `execution_id`, `workspace_id`, `agent_fqn`, `model_id`, `quality_score`, `eval_suite_id`; batch-insert to `analytics_quality_events` table
- [x] T017 [P] [US2] Implement `AnalyticsRepository.query_cost_quality_join(workspace_id, start_time, end_time)` in `apps/control-plane/src/platform/analytics/repository.py`: ClickHouse query — `SELECT u.agent_fqn, u.model_id, u.provider, sum(u.cost_usd) AS total_cost, count() AS exec_count, avg(q.quality_score) AS avg_quality FROM analytics_usage_events u LEFT JOIN analytics_quality_events q ON u.execution_id = q.execution_id WHERE u.workspace_id = ? AND u.timestamp BETWEEN ? AND ? GROUP BY u.agent_fqn, u.model_id, u.provider`
- [x] T018 [P] [US2] Add `AgentCostQuality`, `CostIntelligenceResponse` schemas to `apps/control-plane/src/platform/analytics/schemas.py`
- [x] T019 [US2] Implement `AnalyticsService.get_cost_intelligence(params, user_id)` in `apps/control-plane/src/platform/analytics/service.py`: workspace auth check; call `query_cost_quality_join()`; compute `cost_per_quality = total_cost / avg_quality` (null if no quality data); sort by cost_per_quality ascending (nulls last); assign `efficiency_rank`; return `CostIntelligenceResponse`
- [x] T020 [US2] Implement `GET /api/v1/analytics/cost-intelligence` in `apps/control-plane/src/platform/analytics/router.py`
- [x] T021 [US2] Write integration tests for cost-per-quality in `apps/control-plane/tests/integration/test_analytics_cost_intelligence.py`: ratio = total_cost/avg_quality verified; null quality → null ratio + ranked last; same agent on two models → two separate entries; period filter works correctly; 403 for unauthorized workspace

**Checkpoint**: US2 complete — cost-per-quality computed and ranked for all agents with data.

---

## Phase 5: User Story 3 — Optimization Recommendations (Priority: P2)

**Goal**: Rule-based `RecommendationEngine` generates 4 recommendation types from aggregated ClickHouse data. `GET /analytics/recommendations` returns actionable suggestions with savings estimates and confidence levels.

**Independent Test**: Seed data with agent A having runs on expensive+cheap models with similar quality (≥30 data points). Seed agent B with self-correction loops > 2x fleet average. Query recommendations. Verify model_switch recommendation for agent A with estimated savings > 0 and confidence "high". Verify self_correction_tuning recommendation for agent B.

- [x] T022 [P] [US3] Implement `AnalyticsRepository.query_agent_metrics(workspace_id)` and `AnalyticsRepository.query_fleet_baselines(workspace_id)` in `apps/control-plane/src/platform/analytics/repository.py`: `query_agent_metrics` returns per-agent aggregates (avg_quality per model, avg_self_correction_loops, avg_input_tokens, avg_output_tokens, execution_count, avg_cost_per_execution, first_seen); `query_fleet_baselines` returns workspace-wide averages (avg_loops, median_quality, p95_input_output_ratio)
- [x] T023 [P] [US3] Implement `RecommendationEngine` in `apps/control-plane/src/platform/analytics/recommendation.py`: `generate(agent_metrics, fleet_baselines)` → list; `_check_model_switch()` (same agent, two models, quality within 0.05, cheaper model exists, ≥30 data points each); `_check_self_correction_tuning()` (avg_loops > fleet_avg × 2.0, ≥10 executions); `_check_context_optimization()` (input/output ratio > fleet p95 AND avg_quality < fleet_median, ≥20 executions); `_check_underutilization()` (execution_count_last_30d < 5 AND age > 7 days); `_confidence(data_points)` → high/medium/low; pure computation (no I/O)
- [x] T024 [P] [US3] Add `OptimizationRecommendation`, `RecommendationsParams`, `RecommendationsResponse` schemas to `apps/control-plane/src/platform/analytics/schemas.py`
- [x] T025 [P] [US3] Add `analytics.recommendation.generated` event payload type and `publish_recommendation_generated()` helper to `apps/control-plane/src/platform/analytics/events.py`
- [x] T026 [US3] Implement `AnalyticsService.get_recommendations(params, user_id)` in `apps/control-plane/src/platform/analytics/service.py`: workspace auth; call `query_agent_metrics()` + `query_fleet_baselines()`; run `RecommendationEngine.generate()`; if recommendations non-empty, emit `analytics.recommendation.generated` Kafka event; return `RecommendationsResponse`
- [x] T027 [US3] Implement `GET /api/v1/analytics/recommendations` in `apps/control-plane/src/platform/analytics/router.py`
- [x] T028 [P] [US3] Write unit tests for all 4 recommendation rules in `apps/control-plane/tests/unit/test_analytics_recommendation.py`: model_switch triggers correctly (and doesn't fire with insufficient data points or quality gap > 0.05); self_correction_tuning fires at 2x threshold but not 1.5x; context_optimization fires when ratio > p95 AND quality below median; underutilization fires for low-activity agents; confidence levels correct at 100/30/10 data points
- [x] T029 [US3] Write integration tests for recommendations in `apps/control-plane/tests/integration/test_analytics_recommendations.py`: model_switch recommendation appears with seeded data; correct savings estimate; confidence "high" with 100+ data points, "low" with <30; zero recommendations for workspace with insufficient data (no error, empty list)

**Checkpoint**: US3 complete — 4 recommendation types generated with savings estimates and confidence levels.

---

## Phase 6: User Story 4 — Budget Forecasting (Priority: P2)

**Goal**: `ForecastEngine` applies linear regression to daily cost series to project 7/30/90-day costs with confidence intervals. `GET /analytics/cost-forecast` returns `ResourcePrediction`.

**Independent Test**: Seed 30 days of daily cost data with a clear upward linear trend. Query `GET /api/v1/analytics/cost-forecast?workspace_id=...&horizon_days=30`. Verify `trend_direction = "increasing"`, `total_projected_expected > trailing_30d_actual_sum`. Seed flat data — verify `trend_direction = "stable"`. Seed 3 days only — verify `warning` field is populated.

- [x] T030 [P] [US4] Implement `AnalyticsRepository.query_daily_cost_series(workspace_id, days_back)` in `apps/control-plane/src/platform/analytics/repository.py`: query `analytics_usage_daily` materialized view, return list of `{day: date, cost_usd: float}` sorted ascending by day
- [x] T031 [P] [US4] Implement `ForecastEngine` in `apps/control-plane/src/platform/analytics/forecast.py`: `forecast(daily_costs: list[float], horizon_days: int) -> ResourcePrediction`; `_linear_regression(xs, ys) -> tuple[slope, intercept]` using `statistics.mean/stdev` (no scipy); `_confidence_interval(residuals, n_future) -> tuple[low_delta, high_delta]` using t-factor (t=2.0 for 95% CI); `_volatility_flag(residuals, mean_cost) -> bool` (True if stdev/mean > 0.3); insufficient data warning when < 7 data points; trend_direction from slope sign (|slope| < 0.01 × mean → "stable")
- [x] T032 [P] [US4] Add `ForecastPoint`, `ResourcePrediction`, `ForecastParams` schemas to `apps/control-plane/src/platform/analytics/schemas.py`
- [x] T033 [P] [US4] Add `analytics.forecast.updated` event payload and `publish_forecast_updated()` to `apps/control-plane/src/platform/analytics/events.py`
- [x] T034 [US4] Implement `AnalyticsService.get_forecast(params, user_id)` in `apps/control-plane/src/platform/analytics/service.py`: workspace auth; call `query_daily_cost_series(days_back=90)`; extract cost list; run `ForecastEngine.forecast()`; emit `analytics.forecast.updated` Kafka event; return `ResourcePrediction`
- [x] T035 [US4] Implement `GET /api/v1/analytics/cost-forecast` in `apps/control-plane/src/platform/analytics/router.py`; validate `horizon_days` ∈ {7, 30, 90}
- [x] T036 [P] [US4] Write unit tests for `ForecastEngine` in `apps/control-plane/tests/unit/test_analytics_forecast.py`: linear trend → expected direction; flat data → "stable"; high variance → `high_volatility=true`; <7 data points → `warning` field populated; CI low < expected < high; known regression (seeded xs/ys) → correct slope/intercept
- [x] T037 [US4] Write integration tests for forecast in `apps/control-plane/tests/integration/test_analytics_forecast.py`: 30-day upward trend → projected > actual; 3-day data → warning field; horizon_days=7 vs 90 returns different forecast lengths; 403 for unauthorized workspace

**Checkpoint**: US4 complete — budget forecast with trend direction, confidence intervals, and insufficient-data warning.

---

## Phase 7: User Story 5 — KPI Dashboarding (Priority: P3)

**Goal**: KPI time-series endpoint returns cost, execution volume, avg quality, and cost-per-quality trend at configurable granularity. Internal `get_workspace_cost_summary()` interface exposed for notifications context.

**Independent Test**: Seed multi-day data. Query `GET /api/v1/analytics/kpi?workspace_id=...&granularity=daily`. Verify response contains time-series points with total_cost, execution_count, avg_quality_score. Switch to `granularity=hourly` — verify finer-grained points. Verify workspace filter works. Call `get_workspace_cost_summary()` directly — verify returned dict has expected keys and correct totals.

- [x] T038 [P] [US5] Implement `AnalyticsRepository.query_kpi_series(workspace_id, granularity, start_time, end_time)` in `apps/control-plane/src/platform/analytics/repository.py`: fan out to appropriate materialized view, JOIN with quality events for avg_quality; return list of `{period, total_cost, execution_count, avg_duration_ms, avg_quality_score}`
- [x] T039 [P] [US5] Add `KpiDataPoint`, `KpiSeries` Pydantic schemas to `apps/control-plane/src/platform/analytics/schemas.py`
- [x] T040 [US5] Implement `AnalyticsService.get_kpi_series(workspace_id, granularity, start_time, end_time, user_id)` and `get_workspace_cost_summary(workspace_id, days_back)` (internal interface, no auth check needed — called by trusted in-process callers) in `apps/control-plane/src/platform/analytics/service.py`
- [x] T041 [US5] Implement `GET /api/v1/analytics/kpi` in `apps/control-plane/src/platform/analytics/router.py`: accepts workspace_id, granularity, start_time, end_time; returns `KpiSeries`

**Checkpoint**: US5 complete — KPI dashboard data available with granularity switching and workspace filtering.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Wire up consumers, mount router, add observability, coverage audit, linting.

- [x] T042 [P] Register `AnalyticsPipelineConsumer` startup/shutdown in `apps/control-plane/entrypoints/worker_main.py` lifespan; call `clickhouse_setup.run_setup()` at startup
- [x] T043 [P] Mount analytics router in `apps/control-plane/src/platform/api/__init__.py` (or `main.py`): `app.include_router(analytics_router, prefix="/api/v1")`; call `clickhouse_setup.run_setup()` in `api_main.py` lifespan
- [x] T044 [P] Add `analytics.budget.threshold_crossed` event payload to `apps/control-plane/src/platform/analytics/events.py`; add background APScheduler task in `worker_main.py` that runs daily: calls `get_workspace_cost_summary()` per workspace, compares to configured `ANALYTICS_BUDGET_THRESHOLD_USD` env var, emits event if threshold crossed
- [x] T045 [P] Run `ruff check . --fix` and `mypy --strict apps/control-plane/src/platform/analytics/` — fix all errors in `apps/control-plane/src/platform/analytics/`
- [x] T046 [P] Run `pytest apps/control-plane/tests/ -k "analytics" --cov=src/platform/analytics --cov-report=term` — ensure coverage ≥ 95%; add unit tests for any gaps in `apps/control-plane/tests/unit/`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T002 and T003 parallel
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories; T004/T005/T006 parallel, T007 after T004
- **US1 (Phase 3)**: After Phase 2 — T009 + T014 parallel; T010 after T009 (needs cost compute from T009 helpers)
- **US2 (Phase 4)**: After US1 — extends consumer (T016) + adds new repository method (T017)
- **US3 (Phase 5)**: After US2 — needs quality data in ClickHouse (from T016)
- **US4 (Phase 6)**: After US1 — only needs daily cost series; can proceed in parallel with US3
- **US5 (Phase 7)**: After US1 — needs rollup views working; can proceed in parallel with US3/US4
- **Polish (Phase 8)**: After all user stories

### User Story Dependencies

- **US1 (P1)**: After Foundational — independent
- **US2 (P1)**: After US1 — extends consumer + adds quality JOIN query
- **US3 (P2)**: After US2 — needs quality scores in ClickHouse for cost-quality rules
- **US4 (P2)**: After US1 — only needs daily cost rollups (independent of US2/US3)
- **US5 (P3)**: After US1 — reads same rollup views (independent of US2/US3/US4)

### Parallel Opportunities

- T002 (ClickHouse DDL) and T003 (Alembic migration) in Phase 1 — different files, independent
- T004, T005, T006 in Phase 2 — different files, independent
- T009 (repository methods) and T014 (unit tests) in Phase 3 — different files
- T017, T018 in Phase 4 — different files
- T022, T023, T024, T025 in Phase 5 — all different files
- T030, T031, T032, T033 in Phase 6 — all different files
- T042, T043, T044, T045, T046 in Phase 8 — independent polish tasks

---

## Parallel Example: Phase 2 (Foundational)

```bash
# All three independent — run in parallel:
Task T004: "Implement CostModel SQLAlchemy model in models.py"
Task T005: "Implement base Pydantic schemas in schemas.py"
Task T006: "Implement exceptions in exceptions.py"
```

## Parallel Example: User Story 3 (Recommendations)

```bash
# All four independent files — run in parallel:
Task T022: "Implement AnalyticsRepository.query_agent_metrics() in repository.py"
Task T023: "Implement RecommendationEngine in recommendation.py"
Task T024: "Add recommendation Pydantic schemas to schemas.py"
Task T025: "Add analytics.recommendation.generated event to events.py"
# Then sequentially:
Task T026: "Implement AnalyticsService.get_recommendations() in service.py"
Task T027: "Implement GET /analytics/recommendations in router.py"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (ClickHouse DDL + PostgreSQL migration)
2. Complete Phase 2: Foundational (models, schemas, exceptions, repository skeleton)
3. Complete Phase 3: US1 (pipeline consumer + usage query endpoint)
4. **STOP and VALIDATE**: Pipeline ingesting events, rollups computing, `/analytics/usage` returning data
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → infrastructure ready
2. US1 → event pipeline + usage visibility (MVP)
3. US2 → add cost-per-quality analysis (business value layer 1)
4. US3 → add optimization recommendations (business value layer 2)
5. US4 → add budget forecasting (planning capability)
6. US5 → add KPI dashboard endpoint (visualization layer)

---

## Notes

- **Dual storage**: `AnalyticsRepository` uses `clickhouse-connect` client; `CostModelRepository` uses SQLAlchemy — both in `repository.py`
- **ClickHouse queries**: Use `countMerge()`/`sumMerge()`/`avgMerge()` when reading from AggregatingMergeTree materialized views — not `count()`/`sum()`
- **No retroactive cost recalculation**: Cost is computed at ingestion time using pricing active at that moment — pricing changes only affect future events
- **RecommendationEngine is pure Python**: No I/O; all inputs fetched before calling `generate()`; easy to unit test
- **ForecastEngine has no scipy dependency**: Uses only `statistics` stdlib module for mean/stdev; linear algebra done manually
- **analytics.events is a new Kafka topic**: May need `KAFKA_TOPICS` env var update or Strimzi KafkaTopic CR
- [P] tasks = different files, no blocking dependencies between them
- Commit after each checkpoint to preserve working increments
