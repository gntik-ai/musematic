# Implementation Plan: Cost Governance and Chargeback

**Branch**: `079-cost-governance-chargeback` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/079-cost-governance-chargeback/spec.md`

## Summary

Stand up the `cost_governance/` bounded context that the constitution already names as the owner of UPD-027 (Constitution § "New Bounded Contexts" line 491). Per-execution attribution is computed at execution-step commit using token counts from `common/clients/model_router.py` (`ModelRouterResponse.tokens_in/out`) and pricing from the existing `model_catalog/` (`ModelCatalogEntry.input_cost_per_1k_tokens` / `output_cost_per_1k_tokens`). Attribution writes go to PostgreSQL (system-of-record) AND to ClickHouse `cost_events` (analytics), reusing the `AsyncClickHouseClient` and the `clickhouse_setup.py` DDL pattern from `analytics/`. Workspace budgets and hard-cap enforcement plug into the existing `policies/gateway.py` 4-check chain as a new check between Purpose and tool-budget. Soft-alert and anomaly delivery routes through the multi-channel notification service from feature 077. Forecasting and anomaly detection run as APScheduler async jobs (constitution § Integration Constraints — "Anomaly detection runs as an async job, not per request"). The two existing helpers in `analytics/service.py` (`get_workspace_cost_summary`, `check_budget_thresholds`) are migrated to thin pass-throughs that delegate into `cost_governance/` so feature 020 callers keep working without churn (rule 7 — backwards-compatible APIs). Frontend `/costs/` is a fresh route distinct from the existing `/analytics/` page (feature 049). Hard-cap enforcement is gated by the constitution's existing `FEATURE_COST_HARD_CAPS` flag (default OFF).

## Technical Context

**Language/Version**: Python 3.12+ (control plane). No Go changes.
**Primary Dependencies** (already present): FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+, redis-py 5.x async, clickhouse-connect 0.8+ (via `common.clients.clickhouse.AsyncClickHouseClient`), APScheduler 3.x (forecast + anomaly jobs), numpy ≥ 1.26 + scipy ≥ 1.13 (existing — used by trend regression and outlier-resilient baseline). No new top-level dependency.
**Storage**: PostgreSQL — 5 new tables (`cost_attributions`, `workspace_budgets`, `budget_alerts`, `cost_forecasts`, `cost_anomalies`) via Alembic migration `062_cost_governance.py`. ClickHouse — 1 new table `cost_events` added to `cost_governance/clickhouse_setup.py` following the `analytics/clickhouse_setup.py` pattern (`CREATE TABLE IF NOT EXISTS`, monthly partition, TTL ≥ 2 years to satisfy spec assumption "at least one full annual finance cycle"). Redis — 2 new key patterns: `cost:budget:{workspace_id}:{period_type}:{period_start}` (period spend hot counter, TTL = period length + 1d) and `cost:override:{workspace_id}:{nonce}` (single-shot admin override token, TTL ≤ 5 min). No Vault paths.
**Testing**: pytest + pytest-asyncio 8.x. Existing fixtures for `analytics`, `policies/gateway`, `execution`, `workspaces` are reused. New fixtures only for the cost-attribution input shape and a deterministic anomaly time-series.
**Target Platform**: Linux server (control plane), Kubernetes deployment. Forecasting + anomaly jobs run on the existing `scheduler` runtime profile.
**Project Type**: Web service (FastAPI control plane bounded context — new BC + extensions to `execution`, `policies`, `analytics`, `workspaces`).
**Performance Goals**: Attribution write adds ≤ 30 ms p95 to step commit (synchronous PostgreSQL insert + ClickHouse async-batched). Budget pre-check at the tool gateway adds ≤ 5 ms p95 (Redis hot counter; PostgreSQL only on cache miss). Chargeback report for one workspace × one month renders in ≤ 3 s p95 against ClickHouse rollups. Forecast + anomaly jobs complete in ≤ 60 s per workspace per scheduled run.
**Constraints**: Cost data is cumulative — attribution rows are write-once; corrections happen via additive credit entries (constitution § Critical Reminders rule 31). Budget pre-check is fast-path Redis; PostgreSQL is the system of record on cache miss (constitution § Integration Constraints — "Budget checks are cached but invalidated on every attribution write"). Hard-cap blocks ONLY new execution starts; in-flight executions complete (spec FR-503.4). Concurrent starts near the cap MUST be admitted-or-refused atomically (spec FR-503.6 → Redis Lua atomic decrement + PostgreSQL `INSERT … RETURNING` lease pattern). Override audit entries flow through `security_compliance/services/audit_chain_service.py` (constitution rule 9). Workspace-cost-data leakage prevention: visibility filtering happens in the SQL/ClickHouse query, not in the response serializer (spec FR-502.4, SC-009).
**Scale/Scope**: Up to ~5 K active workspaces × ~1 K executions/workspace/month = 5 M attribution rows/month → ClickHouse for analytics, PostgreSQL `cost_attributions` partitioned by month with retention rule deferred to operator config. Up to 4 budget periods per workspace (3 period types × ≤ 1 active each + transitional rollover). Forecast horizon = current period end. Anomaly evaluation window = configurable (default hourly).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Source | Status | Notes |
|---|---|---|---|
| Brownfield rule 1 — never rewrite | Constitution § Brownfield | ✅ Pass | New BC `cost_governance/`. Modifies `execution/service.py`, `policies/gateway.py`, `analytics/service.py`, `workspaces/models.py` additively; no file rewritten. |
| Brownfield rule 2 — Alembic only | Constitution § Brownfield | ✅ Pass | Single migration `062_cost_governance.py` adds 5 tables + 1 `WorkspaceSettings` JSONB key. No raw DDL. ClickHouse DDL is idempotent `CREATE TABLE IF NOT EXISTS` invoked by `cost_governance/clickhouse_setup.py` at startup, matching `analytics/clickhouse_setup.py:159–167`. |
| Brownfield rule 3 — preserve tests | Constitution § Brownfield | ✅ Pass | Existing `analytics/`, `policies/gateway`, `execution/service` tests stay green; the analytics `get_workspace_cost_summary` / `check_budget_thresholds` become thin delegations whose external contract is unchanged. |
| Brownfield rule 4 — use existing patterns | Constitution § Brownfield | ✅ Pass | New BC follows the standard layout (`models.py`, `schemas.py`, `service.py` per service file, `repository.py`, `router.py`, `events.py`, `exceptions.py`, `dependencies.py`). Event registration follows `analytics/events.py:43–52` pattern. ClickHouse DDL follows `analytics/clickhouse_setup.py`. |
| Brownfield rule 5 — cite exact files | Constitution § Brownfield | ✅ Pass | Project Structure below names every file with file:line for every integration seam. |
| Brownfield rule 6 — additive enums | Constitution § Brownfield | ✅ Pass | No mutation of existing enums. New enums (`CostType`, `BudgetPeriodType`, `AnomalySeverity`, `AnomalyType`) are owned by this BC. `block_reason="workspace_cost_budget_exceeded"` is added as a new string literal in `policies/gateway.py` — block reasons are not enum-typed (verified at `policies/gateway.py:164`). |
| Brownfield rule 7 — backwards-compatible APIs | Constitution § Brownfield | ✅ Pass | Workspaces with no budget configured see no behaviour change. `/api/v1/costs/*` endpoints (constitution § REST Prefix line 797) are additive. Feature 020's `AnalyticsService.get_workspace_cost_summary()` and `.check_budget_thresholds()` keep their public signatures and return shapes; internals delegate to `cost_governance/`. |
| Brownfield rule 8 — feature flags | Constitution § Brownfield | ✅ Pass | Hard-cap enforcement gated by `FEATURE_COST_HARD_CAPS` (default OFF — already in constitution § Feature Flag Inventory line 885). Soft alerts, attribution, forecasting, anomaly detection are always-on (additive read paths). |
| Rule 9 — every PII operation audited | Constitution § Domain | ✅ Pass | Override issuance, budget config CRUD, and admin-initiated chargeback exports emit audit-chain entries via `security_compliance.audit_chain_service`. Attribution rows themselves are not PII operations (no user-data export). |
| Rule 11 — every LLM call through model_router | Constitution § Domain | ✅ Pass | This feature performs no LLM calls. Token counts are consumed from `ModelRouterResponse` (`common/clients/model_router.py:68–75`) — never from provider SDKs. |
| Rule 12 — every cost-incurring action records attribution | Constitution § Domain | ✅ Pass | This feature IS the canonical implementation of `cost_governance/services/attribution_service.py` that rule 12 requires callers to use. The hook into `execution/service.py:record_runtime_event` (line ~570) closes the loop. |
| Rule 18 — residency at query time | Constitution § Domain | ✅ Pass | Cost queries respect the workspace's residency on read. ClickHouse cost rollups are workspace-scoped; no cross-workspace aggregation crosses regions in single-region default deployments. |
| Rule 20 — structured JSON logs | Constitution § Domain | ✅ Pass | All new modules use `structlog`. No `print()`. |
| Rule 21 — correlation IDs propagated | Constitution § Domain | ✅ Pass | Attribution writes carry the existing `CorrelationContext` (`workspace_id`, `execution_id`, `correlation_id`, `trace_id`). Budget-block error envelopes carry the same. |
| Rule 22 — Loki labels low-cardinality only | Constitution § Domain | ✅ Pass | Allowed label set: `service`, `bounded_context=cost_governance`, `level`. `workspace_id`, `execution_id`, `agent_id`, `user_id` go in JSON payload only — never as Loki labels. |
| Rule 24 — every BC dashboard | Constitution § Domain | ✅ Pass | New `deploy/helm/observability/templates/dashboards/cost-governance.json` ConfigMap with the `grafana_dashboard: "1"` label (rule 27). Panels: attribution write rate, budget threshold crossings/period, hard-cap blocks, anomaly count by severity, forecast vs actual delta. |
| Rule 25 — every BC gets E2E suite + journey | Constitution § Domain | ✅ Pass | New `tests/e2e/suites/cost_governance/` suite. Existing "workspace owner manages costs" journey extended (or new journey added) to cross the boundary at the budget-block path. |
| Rule 32 — audit chain on config changes | Constitution § Domain | ✅ Pass | Budget create/update/delete and hard-cap toggles emit audit-chain entries. Override issuance is double-audited (rule 34) — both the issuing admin AND the workspace context. |
| Rule 36 — UX-impacting FRs documented | Constitution § Domain | ✅ Pass | New `/costs/` page documented in the docs site as part of this PR; auto-doc covers env vars (`FEATURE_COST_HARD_CAPS` is already documented in the feature flag inventory). |
| Rule 38 — cost is cumulative; never modify past attributions | Constitution § Critical Reminders 31 | ✅ Pass | `cost_attributions` rows are write-once; the late-arriving signal (spec FR-501.5) appends a credit-entry row referencing the original via `correction_of` FK rather than mutating the original. Reports sum `correction_of IS NULL` + `correction_of IS NOT NULL` together to get the net. |
| Rule 45 — backend has UI | Constitution § Domain | ✅ Pass | New `/costs/` page is included in this feature (User Story 3 + 4 surfaces). Workspace-admin budget config is additionally surfaced in the existing workspace owner workbench (UPD-043) via a small section — coordinated with that feature, not blocking this one. |
| Rule 50 — mock LLM for previews | Constitution § Domain | ✅ Pass | Forecasting / anomaly preview never invokes an LLM. N/A in spirit. |
| Principle I — modular monolith | Constitution § Core | ✅ Pass | All work in the Python control plane. New BC `cost_governance/` lives under `apps/control-plane/src/platform/`. |
| Principle III — dedicated stores | Constitution § Core | ✅ Pass | PostgreSQL for relational truth (attribution, budgets, alerts, forecasts, anomalies). ClickHouse for time-series rollups (`cost_events`, materialized views). Redis for hot budget counters and override nonces. No vector / FTS use. |
| Principle IV — no cross-BC table access | Constitution § Core | ✅ Pass | `cost_governance/` calls into `analytics/`, `model_catalog/`, `workspaces/`, `notifications/`, `policies/` ONLY through their public service interfaces. Reverse direction: `analytics/service.py` migrated to delegate the two cost helpers to `cost_governance/` via a new `CostGovernanceService.get_workspace_cost_summary` / `.evaluate_thresholds` interface — no SQL boundary crossing. |
| AD-20 — per-execution cost attribution synchronous at commit | Constitution § Architecture Decisions | ✅ Pass | Attribution write is synchronous in `execution.service.record_runtime_event` (PostgreSQL row + Kafka event); ClickHouse insertion is async-batched via the existing `AnalyticsRepository.insert_usage_events_batch` pattern adapted for `cost_events`. |

## Project Structure

### Documentation (this feature)

```text
specs/079-cost-governance-chargeback/
├── plan.md              # This file
├── spec.md              # Feature spec
├── research.md          # Phase 0 — pricing-source decision, baseline-method choice, override-token shape
├── data-model.md        # Phase 1 — 5 PG tables + ClickHouse cost_events + materialized views
├── quickstart.md        # Phase 1 — local end-to-end walk: configure budget → run synthetic load → observe alert
├── contracts/           # Phase 1
│   ├── attribution-service.md           # record_step_cost, record_correction, get_execution_cost
│   ├── budget-service.md                # configure, evaluate_thresholds, check_budget_for_start, issue_override
│   ├── chargeback-service.md            # generate_report, export_report
│   ├── forecast-service.md              # compute_forecast, get_latest_forecast
│   ├── anomaly-service.md               # detect, acknowledge, resolve
│   ├── tool-gateway-cost-check.md       # the new check between Purpose and tool-budget
│   └── costs-rest-api.md                # /api/v1/costs/* endpoints
├── checklists/
│   └── requirements.md
└── tasks.md             # Created by /speckit.tasks
```

### Source Code (repository root)

```text
apps/control-plane/
├── migrations/versions/
│   └── 062_cost_governance.py                          # NEW (5 tables; +1 JSONB key on workspace_settings;
│                                                       #   rebase to current head at merge time)
└── src/platform/
    ├── cost_governance/                                # NEW BOUNDED CONTEXT (Constitution § New BCs line 491)
    │   ├── __init__.py
    │   ├── models.py                                   # NEW — CostAttribution, WorkspaceBudget,
    │   │                                               #   BudgetAlert, CostForecast, CostAnomaly,
    │   │                                               #   OverrideRecord
    │   ├── schemas.py                                  # NEW — request/response Pydantic for /costs/*
    │   ├── service.py                                  # NEW — CostGovernanceService facade exposing the
    │   │                                               #   methods that analytics + workspaces call into
    │   ├── services/
    │   │   ├── __init__.py
    │   │   ├── attribution_service.py                  # NEW — record_step_cost, record_correction
    │   │   ├── chargeback_service.py                   # NEW — generate_report, export_report
    │   │   ├── budget_service.py                       # NEW — configure, evaluate_thresholds,
    │   │   │                                           #   check_budget_for_start, issue_override,
    │   │   │                                           #   redeem_override
    │   │   ├── forecast_service.py                     # NEW — APScheduler job; trend + outlier-resilient
    │   │   │                                           #   confidence range
    │   │   └── anomaly_service.py                      # NEW — APScheduler job; baseline + sustained-
    │   │                                               #   deviation rule; suppression of duplicate alerts
    │   ├── repository.py                               # NEW — PostgreSQL queries for the 5 tables
    │   ├── clickhouse_setup.py                         # NEW — `cost_events` DDL + materialized views,
    │   │                                               #   invoked at startup (mirrors
    │   │                                               #   analytics/clickhouse_setup.py:159–167)
    │   ├── clickhouse_repository.py                    # NEW — async batch insert + rollup queries via
    │   │                                               #   AsyncClickHouseClient
    │   ├── router.py                                   # NEW — /api/v1/costs/* (REST prefix per
    │   │                                               #   Constitution § REST Prefix line 797)
    │   ├── events.py                                   # NEW — register cost.execution.attributed,
    │   │                                               #   cost.budget.threshold.reached,
    │   │                                               #   cost.budget.exceeded, cost.anomaly.detected,
    │   │                                               #   cost.forecast.updated (constitution § Kafka
    │   │                                               #   Registry lines 763–767 — already declared
    │   │                                               #   there; this file implements the schemas +
    │   │                                               #   register_cost_governance_event_types())
    │   ├── exceptions.py                               # NEW — BudgetNotConfiguredError,
    │   │                                               #   WorkspaceCostBudgetExceededError (subclass of
    │   │                                               #   BudgetExceededError → HTTP 429 already in
    │   │                                               #   PlatformError chain), OverrideExpiredError,
    │   │                                               #   OverrideAlreadyRedeemedError
    │   ├── dependencies.py                             # NEW — FastAPI deps: get_attribution_service,
    │   │                                               #   get_budget_service, etc.
    │   └── jobs/
    │       ├── __init__.py
    │       ├── forecast_job.py                         # NEW — APScheduler hook
    │       └── anomaly_job.py                          # NEW — APScheduler hook
    │
    ├── execution/
    │   └── service.py                                  # MODIFIED — in record_runtime_event() at
    │                                                   #   line ~570, after the existing event append,
    │                                                   #   call attribution_service.record_step_cost(
    │                                                   #     execution_id, step_id,
    │                                                   #     workspace_id=execution.workspace_id,
    │                                                   #     agent_id=execution.agent_id,
    │                                                   #     user_id=execution.initiator_user_id,
    │                                                   #     payload=payload  # tokens, model_id, duration
    │                                                   #   )
    │                                                   #   inside the same DB transaction so attribution
    │                                                   #   commits atomically with the journal append.
    │
    ├── policies/
    │   └── gateway.py                                  # MODIFIED — between Purpose check (line 154) and
    │                                                   #   the existing tool-invocation budget check
    │                                                   #   (line 156), insert _check_workspace_cost_budget()
    │                                                   #   that calls into BudgetService.check_budget_for_start.
    │                                                   #   On block, returns GateResult with
    │                                                   #   block_reason="workspace_cost_budget_exceeded".
    │                                                   #   Result envelope includes the override_endpoint
    │                                                   #   URL so clients can surface the recovery path
    │                                                   #   (spec FR-503.3).
    │
    ├── analytics/
    │   └── service.py                                  # MODIFIED — get_workspace_cost_summary() at
    │                                                   #   :181–203 and check_budget_thresholds() at :205+
    │                                                   #   become thin delegations to
    │                                                   #   CostGovernanceService.get_workspace_cost_summary
    │                                                   #   and .evaluate_thresholds. Public signature
    │                                                   #   unchanged (rule 7). Existing analytics tests
    │                                                   #   continue to pass.
    │
    ├── workspaces/
    │   ├── models.py                                   # MODIFIED — WorkspaceSettings JSONB at :207–240
    │   │                                               #   gains a `cost_budget` key for the operator UI
    │   │                                               #   default budget hint (the source of truth for
    │   │                                               #   active budgets is workspace_budgets table; the
    │   │                                               #   JSONB hint is a UX convenience, not an
    │   │                                               #   enforcement source).
    │   └── service.py                                  # MODIFIED — on workspace archival, call into
    │                                                   #   CostGovernanceService.handle_workspace_archived()
    │                                                   #   so cost history is preserved (spec FR-CC-3).
    │
    └── common/
        └── config.py                                   # MODIFIED — add CostGovernanceSettings sub-model:
                                                        #   anomaly_evaluation_interval_seconds (default 3600),
                                                        #   forecast_evaluation_interval_seconds (default 3600),
                                                        #   override_token_ttl_seconds (default 300),
                                                        #   minimum_history_periods_for_forecast (default 4),
                                                        #   default_alert_thresholds=[50, 80, 100],
                                                        #   default_currency="USD".

deploy/helm/observability/templates/dashboards/
└── cost-governance.json                                # NEW — Grafana dashboard ConfigMap (rule 24)

apps/web/
├── app/(main)/costs/                                   # NEW ROUTE — /costs/ (fresh; distinct from
│   │                                                   #   /analytics/ which is feature 049)
│   ├── page.tsx                                        # NEW — dashboard: spend-by-period, top-N
│   │                                                   #   workspaces/agents/users, anomaly feed,
│   │                                                   #   forecast chart
│   ├── budgets/page.tsx                                # NEW — budget configuration (workspace admin)
│   ├── reports/page.tsx                                # NEW — chargeback report builder + export
│   └── anomalies/[id]/page.tsx                         # NEW — anomaly detail + acknowledge/resolve
└── components/features/cost-governance/                # NEW — BudgetConfigForm, BudgetThresholdGauge,
                                                        #   CostBreakdownChart, ForecastChart,
                                                        #   AnomalyCard, OverrideDialog,
                                                        #   ChargebackReportBuilder, ExportDialog

tests/control-plane/unit/cost_governance/
├── test_attribution_service.py                         # NEW — token→cost math, partial costs on failure,
│                                                       #   late-arriving correction, allocation rule
├── test_budget_service.py                              # NEW — threshold-once-per-period semantics,
│                                                       #   period rollover, budget-changed-mid-period
├── test_chargeback_service.py                          # NEW — reconciliation, RBAC scoping, export shape
├── test_forecast_service.py                            # NEW — outlier resilience, low-confidence flag,
│                                                       #   no-history workspace
├── test_anomaly_service.py                             # NEW — duplicate-suppression, ack/resolve,
│                                                       #   no-history skip
└── test_event_registration.py                          # NEW — all 5 cost.* event types registered

tests/control-plane/integration/cost_governance/
├── test_execution_records_attribution.py               # NEW — exec finishes → attribution row + ClickHouse
│                                                       #   cost_events row + Kafka cost.execution.attributed
├── test_tool_gateway_cost_check.py                     # NEW — hard cap blocks new start; in-flight not
│                                                       #   blocked; override admits next start
├── test_concurrent_starts_at_cap.py                    # NEW — atomic admit-or-refuse under contention
├── test_budget_alerts_api.py                           # NEW — /api/v1/costs/budgets, /alerts
├── test_chargeback_report_api.py                       # NEW — group-by, RBAC scoping, export
├── test_anomaly_lifecycle_api.py                       # NEW — detect → ack → resolve
└── test_workspace_archival_preserves_costs.py          # NEW — spec FR-CC-3

tests/e2e/suites/cost_governance/
├── test_attribution_visible_during_run.py              # NEW — spec acceptance scenario US1.3
├── test_hard_cap_blocks_then_override.py               # NEW — spec acceptance scenario US2.3 + US2.4
└── test_anomaly_alert_routes_to_admin.py               # NEW — alert delivery integrates with feature 077
```

**Structure Decision**: One new bounded context (`cost_governance/`), aligned with the constitution's existing declaration that `cost_governance/` owns UPD-027 (Constitution § "New Bounded Contexts" line 491). Five surgical extensions: `execution/service.py` (the attribution hook), `policies/gateway.py` (the budget pre-check), `analytics/service.py` (delegation of two helpers introduced by feature 020), `workspaces/models.py` + `workspaces/service.py` (settings hint + archival hook), `common/config.py` (settings sub-model). Frontend is a fresh `/costs/` route — `apps/web/app/(main)/analytics/` (feature 049) covers analytics/usage and remains untouched. Dashboard ships in the unified observability Helm bundle per rule 27.

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Five PostgreSQL tables (one per concept) | Each has a distinct lifecycle: attribution rows are write-once cumulative ledgers; budgets are versionable config; alerts are per-(budget, threshold, period) idempotency markers; forecasts are point-in-time snapshots; anomalies are stateful (open/ack/resolved). Conflating them produces sparse columns and ambiguous query paths. | Single polymorphic `cost_records` table: rejected — sparse columns, conflicting indexes, alert-deduplication harder to express. |
| Both PostgreSQL `cost_attributions` AND ClickHouse `cost_events` | PostgreSQL is the immutable system of record (audit, drill-down to a specific row, FK from corrections to originals). ClickHouse is the analytical store (rollups, group-by reports, anomaly baselines over millions of rows). The constitution § Architecture Decision AD-20 explicitly mandates ClickHouse for cost; § Critical Reminder 31 mandates write-once cumulative records — neither alone satisfies both. | PostgreSQL only: rejected — chargeback rollups across 5 M rows/month would degrade unacceptably (Constitution § Core III — never compute analytics in PostgreSQL). ClickHouse only: rejected — no FK integrity for credit corrections, no transactional insert with the execution journal. |
| Redis hot counter for budget pre-check | Spec FR-503.6 (concurrent-start atomicity) and the perf goal (≤ 5 ms p95 at the gateway) require a hot path. PostgreSQL on every gateway call would add tens of milliseconds and risk contention. Constitution § Integration Constraints explicitly says budget checks are cached but invalidated on every attribution write. | PostgreSQL on every check: rejected — too slow for the gateway hot path; contention under burst. |
| Override token (Redis nonce, single-use, ≤ 5 min TTL) instead of permanent override flag | Spec FR-503.5 requires bounded overrides. A permanent flag would silently disable enforcement (spec edge case "admin override scope"). The nonce design forces every use to be a fresh, audited authorisation. | A boolean override flag on `workspace_budgets`: rejected — too easy to leave on; violates spec FR-503.5. |
| Anomaly + forecast as APScheduler jobs (not per-request) | Constitution § Integration Constraints explicitly: "Anomaly detection runs as an async job, not per request." Per-request anomaly evaluation would couple read latency to time-series scans. | On-read evaluation: rejected — constitution prohibits and it would not scale. |
| Migrate `analytics.get_workspace_cost_summary` and `.check_budget_thresholds` to delegations rather than rip them out | Feature 020 already added these helpers (`analytics/service.py:181–203` and following). Removing them would break callers; leaving them with their own logic creates two cost paths. The thin-delegation pattern preserves caller compatibility (rule 7) while making `cost_governance/` the canonical owner (rule 12). | Rip out and migrate every caller in this PR: rejected — out of scope and risky. Leave both implementations: rejected — two cost paths violate constitution rule 12 and SC-005 (reconciliation). |
| Frontend `/costs/` as a fresh route, NOT extending `/analytics/` | `/analytics/` (feature 049) is the analytics/usage page. Cost governance has a distinct user persona (finance/platform owner) and a distinct verb set (configure, alert, override, export). Cramming both into one page conflates roles and complicates RBAC (workspace-admin-only sub-pages would have to be hidden inside an analytics page). | One combined `/analytics/` page: rejected — role conflation, RBAC complexity, IA confusion. |

## Dependencies

- **`model_catalog/` (UPD-026, already implemented)** — required for per-model pricing. `cost_governance/services/attribution_service.py` calls into `model_catalog` to resolve `input_cost_per_1k_tokens` / `output_cost_per_1k_tokens` for the model used by each step (`apps/control-plane/src/platform/model_catalog/models.py:61–62`). The user's brownfield input correctly identifies this dependency; it is satisfied today.
- **`common/clients/model_router.py` (feature 075)** — token counts (`tokens_in`, `tokens_out`) are read from `ModelRouterResponse` (`:68–75`) — never from provider SDKs (rule 11 / 37).
- **`execution/service.py`** — `record_runtime_event` (≈ line 570) is the attribution hook. Cost write is in the same DB transaction as the journal append (atomic per execution step).
- **`policies/gateway.py`** — the cost budget pre-check inserts between Purpose (`:154`) and the existing tool-invocation budget (`:156`). Reuses the existing `_blocked()` envelope.
- **`analytics/`** — `AnalyticsService.get_workspace_cost_summary` (`:181–203`) and `.check_budget_thresholds` (≈ `:205`) become thin delegations. ClickHouse client wrapper `common/clients/clickhouse.py:AsyncClickHouseClient` is reused. ClickHouse DDL pattern from `analytics/clickhouse_setup.py:159–167` is reused.
- **`notifications/` (feature 077)** — soft-alert and anomaly delivery routes through `AlertService.process_state_change` (`notifications/service.py:203–256`). Workspace admin recipients resolved via `workspaces/service.py:182` (`WorkspacesRepository.list_members(role=WorkspaceRole.admin)`).
- **`security_compliance/services/audit_chain_service.py` (UPD-024)** — required by rules 9, 32, 34 for budget config CRUD, override issuance/redemption, and chargeback exports.
- **`workspaces/`** — `WorkspaceSettings` JSONB at `models.py:207–240` for the operator-UI hint; archival hook on `workspaces/service.py` for spec FR-CC-3.
- **Constitution § Kafka Topics Registry (lines 763–767)** — the 5 cost event types are already declared in the constitution; this feature implements their schemas and registration. Topic name: `cost-governance.events` (following the `{bc-name}.events` convention used by `analytics.events`, `notifications.events`).
- **Constitution § Feature Flag Inventory (line 885)** — `FEATURE_COST_HARD_CAPS` already exists; this feature wires it into the gateway check.
- **APScheduler** — already in the runtime; forecast + anomaly jobs run on the `scheduler` profile.

## Wave Placement

Wave 7 — placed after the model catalog (UPD-026, Wave 6) so per-model pricing is reliably available. Compatible with feature 077 (notifications, Wave 5) and feature 078 (content safety, Wave 6) which are already merged. Downstream UPD-043 (Workspace Owner Workbench) consumes the budget-config form via a coordinated section; that workbench is not blocking and lands in its own wave.
