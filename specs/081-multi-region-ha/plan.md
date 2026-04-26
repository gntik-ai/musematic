# Implementation Plan: Multi-Region High-Availability Deployment

**Branch**: `081-multi-region-ha` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

Stand up the `multi_region_ops/` bounded context that the constitution already names as the owner of UPD-025 (Constitution § "New Bounded Contexts" line 492), backing the already-reserved REST prefixes `/api/v1/regions/*` and `/api/v1/maintenance/*` (lines 798–799), the already-declared Kafka topics `region.replication.lag` / `region.failover.initiated` / `region.failover.completed` / `maintenance.mode.enabled` / `maintenance.mode.disabled` (lines 768–772), and the already-named feature flags `FEATURE_MULTI_REGION` and `FEATURE_MAINTENANCE_MODE` (lines 888–889). The brownfield input is correct that this is fully greenfield: there is no existing `multi_region_ops/` BC, no existing replication-monitoring code anywhere in the control plane (verified), and no existing maintenance-mode gate. **Replication monitoring is per-store**: a single `ReplicationProbe` Protocol with seven adapters (PostgreSQL via `pg_stat_replication`, Kafka via `aiokafka.admin.AIOKafkaAdminClient`, S3-compatible via the generic S3 protocol's replication metrics, ClickHouse via `system.replication_queue`, Qdrant / Neo4j / OpenSearch via their native cluster-status APIs) is invoked by an APScheduler probe runner that writes `replication_statuses` rows and triggers RPO incidents through the existing `IncidentTriggerInterface` from feature 080 (`incident_response/trigger_interface.py:8–48`) when lag crosses the operator-declared threshold. **Maintenance mode is a FastAPI `BaseHTTPMiddleware`** registered at the existing middleware site (`main.py:1298–1302`), gated by `FEATURE_MAINTENANCE_MODE`, that refuses HTTP-mutating verbs (POST / PUT / PATCH / DELETE) with a 503 carrying the active window's reason and `ends_at` while letting GET / HEAD / OPTIONS pass — this preserves the spec's read-only-during-maintenance guarantee (FR-481.4) without per-endpoint annotation. **In-flight executions** are protected because the middleware sees only inbound HTTP requests; running execution work continues to drain through the existing scheduler/worker profiles (FR-481.3, SC-007). **Failover orchestration** is a stepwise plan executor that records per-step outcomes and emits the constitutional `region.failover.initiated` / `region.failover.completed` events; the plan steps themselves are typed (`promote_postgres`, `flip_kafka_mirrormaker`, `update_dns`, `verify_health`, etc.) but the actual cutover work is largely operator-driven via the runbook (`deploy/runbooks/failover.md`) — the platform records, audits, and gates rather than performing every infrastructure step itself. **Capacity planning is a thin surfacing layer**: it reads existing forecast signals from feature 079 (`cost_governance/repository.py:321 get_latest_forecast`) and existing usage-rollups from feature 020 / `analytics/`, applies operator-configured saturation thresholds, and emits capacity alerts. **Helm overlay** lives at `deploy/helm/platform/values-multi-region.yaml` plus a new `deploy/helm/platform/templates/replication-jobs/` subtree following the existing `deploy/helm/control-plane/templates/migration-job.yaml` pattern. **Two new feature-flag fields** (`feature_maintenance_mode`, `feature_multi_region`) are added to `common/config.py` mirroring the existing `FEATURE_COST_HARD_CAPS` pattern (line 1555) — the constitutional names already exist in the registry, this just wires them into Pydantic settings. Frontend extends the existing `apps/web/app/(main)/operator/page.tsx` panel pattern (resolvePanel SearchParams) with three new panels: `regions`, `maintenance`, `capacity`.

## Technical Context

**Language/Version**: Python 3.12+ (control plane). No Go changes.
**Primary Dependencies** (already present): FastAPI 0.115+ (middleware via `BaseHTTPMiddleware`), Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+ (`aiokafka.admin.AIOKafkaAdminClient` for the Kafka replication probe — already shipped with the existing aiokafka version), redis-py 5.x async (active-window cache; failover-plan distributed lock), httpx 0.27+ (Qdrant / Neo4j / OpenSearch / S3 cluster-status HTTP probes), APScheduler 3.x (replication probe runner, capacity projection runner, maintenance-window state-transition runner), `clickhouse-connect 0.8+` (ClickHouse `system.replication_queue` query), asyncpg 0.30+ (PostgreSQL `pg_stat_replication` query — uses the existing async pg connection pool from `common/database.py`). No new top-level dependency.
**Storage**: PostgreSQL — 5 new tables (`region_configs`, `replication_statuses`, `failover_plans`, `failover_plan_runs`, `maintenance_windows`) via Alembic migration `064_multi_region_ops.py`. The brownfield input proposed 4 tables; the fifth (`failover_plan_runs`) splits run-history off the plan row so each rehearsal/production execution is its own auditable record (FR-478.10 — every action MUST be auditable end-to-end; the input's `tested_at` + `last_executed_at` columns alone collapse history into two timestamps and lose per-run-step outcomes). Redis — 2 new key patterns: `multi_region:active_window` (active-maintenance-window cache, TTL = window duration; primed on enable; the maintenance gate middleware is HOT-path so this MUST be sub-ms) and `multi_region:failover_lock:{from_region}:{to_region}` (distributed mutex preventing concurrent failovers on the same region pair per FR-478.12; TTL = max-plan-duration + grace). No new MinIO/S3 buckets — runbook documents are checked into `deploy/runbooks/` per Principle XVI's separation of code from operator documentation.
**Testing**: pytest + pytest-asyncio 8.x. New fixtures: (a) per-store probe mocks (one per data store category — 7 mocks) returning controllable lag values, (b) a fixed-clock window-state-machine harness for maintenance-mode tests, (c) a failover-plan runner harness with mockable step adapters. Existing fixtures for `audit/`, `notifications/`, `incident_response/`, `cost_governance/`, `analytics/` are reused.
**Target Platform**: Linux server (control plane), Kubernetes deployment. The replication probe runner, capacity projection runner, and maintenance-window state-transition runner run on the existing `scheduler` runtime profile only (guarded via `settings.runtime_profile == "scheduler"` per the established pattern from feature 079).
**Project Type**: Web service (FastAPI control plane bounded context — new BC + middleware + a small extension to `common/config.py` to wire the constitutional feature flags).
**Performance Goals**: Maintenance-mode middleware adds ≤ 1 ms p95 to every inbound request when no window is active and ≤ 2 ms p95 when an active window is cached in Redis (the gate is on the hot path; PG must NOT be queried per-request). Replication probes complete per-store in ≤ 5 s p95 (we want lag observable at high frequency; default 30 s probe interval is configurable). Failover-plan rehearsal records per-step outcome within ≤ 100 ms of step return (the timing fidelity matters for SC-003). Capacity dashboard render ≤ 2 s p95 (reads from existing rollups; no new heavy computation).
**Constraints**: The maintenance gate is fail-OPEN on Redis miss (rule 41 inverse — Vault failure fails closed for *authentication*, but the maintenance gate MUST fail open on cache miss because a Redis blip should not falsely block all writes; the PG truth is consulted on miss and the cache is primed; if both Redis AND PG are unreachable, the gate fails open with a structured-log critical so the operator notices). Replication probes are read-only against each store; they MUST NOT mutate. Failover plan execution acquires a Redis-based distributed lock keyed on `(from_region, to_region)` so concurrent initiations are atomically refused (FR-478.12, SC-005). Per-store replication probes MUST log success/failure at INFO/WARN — never log credential-bearing connection strings (rule 23, 40). The capacity surface NEVER re-implements forecasting; it composes existing signals from features 079 and 020 (FR-482.6 — "MUST be referenced from the capacity view rather than re-implemented here"). Active-active configuration is refused at validation time (FR-479.2) — a deployment with two regions both flagged `region_role='primary'` returns a 422 from `POST /api/v1/regions` with a clear pointer to the active-active documentation.
**Scale/Scope**: Up to ~5 regions per deployment (1 primary + 4 secondaries is more than any current operational target). Replication probe writes 7 components × N target regions × 1 row per probe interval — at default 30 s and 1 secondary that's 7 × 1 × 120 = 840 rows/hour, ~7 K rows/day; partition `replication_statuses` by month with a TTL index for cleanup (24 months retained per spec assumption "at least one full annual finance cycle"-equivalent for ops history; here aligned with SC-014 quarterly rehearsal × 4 + buffer). Maintenance windows: < 100/year typically. Failover plans: ≤ 10 per deployment. Failover plan runs (rehearsals + production): ≤ 50/year per plan.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Source | Status | Notes |
|---|---|---|---|
| Brownfield rule 1 — never rewrite | Constitution § Brownfield | ✅ Pass | New BC `multi_region_ops/`. Modifies `common/config.py` (additive feature-flag fields), `main.py` (add one middleware to the existing stack at `:1298–1302`); no file rewritten. |
| Brownfield rule 2 — Alembic only | Constitution § Brownfield | ✅ Pass | Single migration `064_multi_region_ops.py` adds 5 tables. No raw DDL. |
| Brownfield rule 3 — preserve tests | Constitution § Brownfield | ✅ Pass | Existing tests stay green; the new middleware is additive and gated on `FEATURE_MAINTENANCE_MODE` (default OFF — no behaviour change for existing deployments). |
| Brownfield rule 4 — use existing patterns | Constitution § Brownfield | ✅ Pass | New BC follows the standard layout (`models.py`, `schemas.py`, `service.py`, services subfolder, `repository.py`, `router.py`, `events.py`, `exceptions.py`, `dependencies.py`, `middleware/`). Probe Protocol mirrors the `PagingProviderClient` Protocol pattern from feature 080. APScheduler integration follows feature 079's pattern. Helm overlay follows the existing `deploy/helm/control-plane/templates/migration-job.yaml` shape. Feature-flag fields follow `FEATURE_COST_HARD_CAPS` at `common/config.py:1555`. |
| Brownfield rule 5 — cite exact files | Constitution § Brownfield | ✅ Pass | Project Structure below names every file; integration seams cite file:line for all call sites. |
| Brownfield rule 6 — additive enums | Constitution § Brownfield | ✅ Pass | New enums (`RegionRole`, `ReplicationComponent`, `ReplicationHealth`, `FailoverPlanStepKind`, `FailoverPlanRunOutcome`, `MaintenanceWindowStatus`) are owned by this BC. No existing enums mutated. |
| Brownfield rule 7 — backwards-compatible APIs | Constitution § Brownfield | ✅ Pass | A deployment with `FEATURE_MULTI_REGION=false` and `FEATURE_MAINTENANCE_MODE=false` (the defaults) sees no behaviour change. New endpoints are additive. The middleware short-circuits to `call_next()` immediately when `FEATURE_MAINTENANCE_MODE=false`. |
| Brownfield rule 8 — feature flags | Constitution § Brownfield | ✅ Pass | `FEATURE_MULTI_REGION` and `FEATURE_MAINTENANCE_MODE` are constitutional flags (lines 888–889) — defaults OFF; the plan adds the Pydantic field wiring (the names are not new, only the runtime binding). |
| Rule 9 — every PII operation audited | Constitution § Domain | ✅ Pass | This BC writes no user PII. Administrative actions (region create/update, plan create/update/execute, maintenance schedule/enable/disable) emit audit-chain entries via `AuditChainService.append` (`audit/service.py:48`). |
| Rule 10 — every credential goes through Vault | Constitution § Domain | ✅ Pass | Per-store probe credentials (PG replica DSN, Kafka admin client SASL, S3 cross-region keys, ClickHouse cluster keys, etc.) resolve via the existing `SecretProvider.get_current()` pattern from `common/clients/model_router.py:43`. The `region_configs.endpoint_urls` JSONB stores reference paths only — never values. |
| Rule 18 — residency at query time | Constitution § Domain | ✅ Pass | This feature does NOT override residency rules; it observes them. Operator dashboard reads of region config respect existing residency policies. AD-21 is preserved: every workspace has a region; cross-region transfers are governed by existing residency configs, not by this feature's plan execution. |
| Rule 20 — structured JSON logs | Constitution § Domain | ✅ Pass | All new modules use `structlog`. Probe clients log per-probe success/failure with `component`, `source_region`, `target_region`, `lag_seconds` in the JSON payload — credential-bearing connection strings are masked at the structlog processor layer (rule 23, 40). |
| Rule 21 — correlation IDs propagated | Constitution § Domain | ✅ Pass | Replication-lag, failover, maintenance-mode events carry the existing `CorrelationContext`. The constitutional `region.replication.lag` etc. envelopes include `correlation_id`, `trace_id`, and the `region_id` key per the topic registry. |
| Rule 22 — Loki labels low-cardinality only | Constitution § Domain | ✅ Pass | Allowed labels: `service`, `bounded_context=multi_region_ops`, `level`, `component` (bounded set of 7 — postgres / kafka / s3 / clickhouse / qdrant / neo4j / opensearch). `source_region`, `target_region`, `region_id`, `plan_id`, `window_id` go in the JSON payload only. |
| Rule 24 — every BC dashboard | Constitution § Domain | ✅ Pass | New `deploy/helm/observability/templates/dashboards/multi-region-ops.yaml` ConfigMap following the `cost-governance.yaml` / `incident-response.yaml` pattern. Panels: replication lag per (component, source, target) (graph), RPO threshold breaches (counter), failover plan staleness (table), maintenance-window state (single-stat), capacity saturation horizon (graph). |
| Rule 25 — every BC gets E2E suite + journey | Constitution § Domain | ✅ Pass | New `tests/e2e/suites/multi_region_ops/` suite. A new operator journey (configure secondary → observe replication healthy → inject lag → observe RPO alert → schedule maintenance window → enable → in-flight execution drains → disable) added to the journey tree alongside existing journeys (rule 28 — extend, do not parallel). |
| Rule 26 — journeys against real backends | Constitution § Domain | ✅ Pass | E2E uses the kind cluster + Helm chart. Per-store probe mocks deployed as in-cluster pods rather than test-only bypass paths in production code. |
| Rule 29 — admin endpoints segregated | Constitution § Domain | ✅ Pass | All authoring surfaces (region create/update/delete, failover-plan create/update/execute, maintenance-window schedule/enable/disable) live under `/api/v1/admin/regions/*` and `/api/v1/admin/maintenance/*`. The constitutional read prefixes `/api/v1/regions/*` and `/api/v1/maintenance/*` (lines 798–799) carry read-only operator-RBAC endpoints. |
| Rule 30 — admin role gates | Constitution § Domain | ✅ Pass | Every admin method depends on `require_superadmin` — region configuration, plan management, and maintenance mode are platform-operator concerns, not workspace-admin. |
| Rule 32 — audit chain on config changes | Constitution § Domain | ✅ Pass | Region create/update/delete, plan create/update/execute, maintenance schedule/enable/disable each emit audit-chain entries through `AuditChainService.append`. The `failover_plan_runs` table is itself a per-execution audit-grade record; the chain entry references the run id. |
| Rule 33 — region failover risky / test quarterly | Constitution § Critical Reminders | ✅ Pass | SC-014 mandates quarterly rehearsal outcomes are persisted ≥ 1 year. FR-478.13 surfaces stale plans as a dashboard signal. The feature does not auto-trigger production failover (spec § Out of Scope). |
| Rule 36 — UX-impacting FRs documented | Constitution § Domain | ✅ Pass | New `/operator/regions/`, `/operator/maintenance/`, `/operator/capacity/` panels documented in the docs site as part of this PR. The `deploy/runbooks/failover.md` and `deploy/runbooks/zero-downtime-upgrade.md` documents are first-class deliverables (FR-480.5, FR-CC-7) and are committed alongside the code. |
| Rule 39 — every secret resolves via SecretProvider | Constitution § Domain | ✅ Pass | All replication-probe credentials resolve via `SecretProvider.get_current()`. No `os.getenv` for `*_API_KEY` / `*_SECRET` / `*_PASSWORD` patterns inside this BC. |
| Rule 40, 41 — Vault tokens never in logs; Vault failure fails closed for auth | Constitution § Domain | ✅ Pass | Probe clients log component/region/lag — never connection strings or auth tokens. The maintenance gate fails OPEN on Redis miss (this is a deliberate inversion — see Constraints above; this is a gate for cooperative protection during maintenance, NOT an authentication path; rule 41 applies to authentication paths, which this is not). |
| Rule 45 — backend has UI | Constitution § Domain | ✅ Pass | New `regions`, `maintenance`, `capacity` panels added to the existing `apps/web/app/(main)/operator/page.tsx` panel registry following the `resolvePanel()` SearchParams pattern (`page.tsx:39–41`). |
| Rule 48 — platform state visible to users | Constitution § Domain | ✅ Pass | Maintenance-window announcements emit through the existing `<PlatformStatusBanner>` surface (constitutional commitment); this feature is a producer of that surface. The user-facing 503 carries the announcement text directly. |
| Rule 49 — public status page independence | Constitution § Domain | ✅ N/A | Public-facing status page is out of scope (spec § Out of Scope). The user-visible maintenance announcement uses the existing in-shell `<PlatformStatusBanner>`, which is not the public status page. |
| Rule 50 — mock LLM for previews | Constitution § Domain | ✅ N/A | This feature does not invoke an LLM. |
| Principle I — modular monolith | Constitution § Core | ✅ Pass | All work in the Python control plane. New BC `multi_region_ops/` lives under `apps/control-plane/src/platform/`. |
| Principle III — dedicated stores | Constitution § Core | ✅ Pass | PostgreSQL for relational truth (5 tables). Redis for the active-window cache + failover lock. Probes READ from each respective store via that store's native interface — they do not introduce new store types. |
| Principle IV — no cross-BC table access | Constitution § Core | ✅ Pass | `multi_region_ops/` calls into `audit/`, `notifications/`, `incident_response/`, `cost_governance/`, `analytics/` ONLY through their public service interfaces. The capacity-view forecast read goes through `CostGovernanceService` (public), not `cost_governance/repository.py` directly across the BC boundary. |
| Principle V — append-only journal | Constitution § Core | ✅ Pass | This feature reads no execution journal entries; failover plan runs and replication-status rows are append-only by design. |
| AD-21 — region as first-class dimension | Constitution § Architecture Decisions | ✅ Pass | This feature is the canonical implementation of region-as-first-class. Every workspace already has a region (existing privacy compliance); this feature adds the region-config table + the operational surface around it. |
| Constitutional Kafka topics — already declared | Constitution § Kafka Registry lines 768–772 | ✅ Pass | The 5 region/maintenance event types are already in the topic registry. This feature implements their schemas under the topic name `multi_region_ops.events` (consistent with `analytics.events`, `notifications.events`, `incident_response.events`); no topic-registry change. |
| Constitutional REST prefixes — already declared | Constitution § REST Prefix lines 798–799 | ✅ Pass | `/api/v1/regions/*` and `/api/v1/maintenance/*` are already in the prefix registry. Admin authoring surfaces use the segregated `/api/v1/admin/*` prefix per rule 29. |
| Constitutional feature flags — already declared | Constitution § Feature Flag Inventory lines 888–889 | ✅ Pass | `FEATURE_MAINTENANCE_MODE` and `FEATURE_MULTI_REGION` are constitutional names; this plan adds the Pydantic settings binding to `common/config.py` following the existing `FEATURE_COST_HARD_CAPS` (`:1555`) pattern. |

## Project Structure

### Documentation (this feature)

```text
specs/081-multi-region-ha/
├── plan.md                  # This file
├── spec.md                  # Feature spec
├── planning-input.md        # Verbatim brownfield input (preserved as planning artifact)
├── research.md              # Phase 0 — per-store replication-query decisions, RPO/RTO threshold semantics, failover-step-kind taxonomy
├── data-model.md            # Phase 1 — 5 PG tables + Redis keys + the failover plan-step type system
├── quickstart.md            # Phase 1 — local end-to-end walk: declare secondary → observe replication → schedule maintenance → drain → resume
├── contracts/               # Phase 1
│   ├── region-service.md                  # CRUD + active-active validation (FR-479.2)
│   ├── replication-probe.md               # Protocol + per-store adapter contract
│   ├── failover-service.md                # author_plan, rehearse, execute, get_run_history; lock semantics
│   ├── maintenance-mode-service.md        # schedule, enable, disable, drain semantics; window state machine
│   ├── maintenance-gate-middleware.md     # method allowlist; failure-open semantics; cache priming
│   ├── capacity-service.md                # composes feature 079 forecasts + analytics rollups
│   ├── regions-rest-api.md                # /api/v1/regions/* + /api/v1/admin/regions/*
│   └── maintenance-rest-api.md            # /api/v1/maintenance/* + /api/v1/admin/maintenance/*
├── checklists/
│   └── requirements.md
└── tasks.md                 # Created by /speckit.tasks (NOT created here)
```

### Source Code (repository root)

```text
apps/control-plane/
├── migrations/versions/
│   └── 064_multi_region_ops.py                          # NEW — 5 tables (rebase to current head at merge)
└── src/platform/
    ├── multi_region_ops/                                # NEW BOUNDED CONTEXT (Constitution § New BCs line 492)
    │   ├── __init__.py
    │   ├── models.py                                    # NEW — RegionConfig, ReplicationStatus,
    │   │                                                #   FailoverPlan, FailoverPlanRun, MaintenanceWindow
    │   ├── schemas.py                                   # NEW — request/response Pydantic for the two REST
    │   │                                                #   surfaces; FailoverPlanStep typed union
    │   ├── service.py                                   # NEW — MultiRegionOpsService facade exposing
    │   │                                                #   the methods external surfaces (operator dashboard,
    │   │                                                #   middleware) call into
    │   ├── services/
    │   │   ├── __init__.py
    │   │   ├── region_service.py                        # NEW — CRUD; active-active validation
    │   │   │                                            #   refuses two `region_role='primary'` entries
    │   │   │                                            #   (FR-479.2)
    │   │   ├── replication_monitor.py                   # NEW — APScheduler-driven probe runner; iterates
    │   │   │                                            #   secondary regions × probe registry; writes
    │   │   │                                            #   `replication_statuses` rows; on RPO breach,
    │   │   │                                            #   fires through `IncidentTriggerInterface`
    │   │   │                                            #   (incident_response/trigger_interface.py:8–48)
    │   │   ├── failover_service.py                      # NEW — author_plan, rehearse, execute,
    │   │   │                                            #   get_run_history; acquires Redis distributed
    │   │   │                                            #   lock per (from_region, to_region) for FR-478.12
    │   │   ├── maintenance_mode_service.py              # NEW — schedule, enable, disable, get_active_window,
    │   │   │                                            #   list_windows, cancel; manages the Redis active
    │   │   │                                            #   window cache; emits the constitutional
    │   │   │                                            #   maintenance.mode.enabled / disabled events
    │   │   ├── capacity_service.py                      # NEW — composes existing signals: reads forecasts
    │   │   │                                            #   from CostGovernanceService.get_latest_forecast
    │   │   │                                            #   (cost_governance/repository.py:321), reads
    │   │   │                                            #   usage rollups from AnalyticsService; applies
    │   │   │                                            #   operator-configured saturation thresholds;
    │   │   │                                            #   never re-implements forecasting (FR-482.6)
    │   │   └── probes/
    │   │       ├── __init__.py
    │   │       ├── base.py                              # NEW — ReplicationProbe Protocol:
    │   │       │                                        #   async def measure(source: RegionConfig,
    │   │       │                                        #     target: RegionConfig) -> ReplicationMeasurement
    │   │       ├── postgres.py                          # NEW — pg_stat_replication query via the existing
    │   │       │                                        #   asyncpg pool from common/database.py
    │   │       ├── kafka.py                             # NEW — aiokafka.admin.AIOKafkaAdminClient
    │   │       │                                        #   describe_consumer_groups for the MirrorMaker
    │   │       │                                        #   replication-status consumer group
    │   │       ├── s3.py                                # NEW — generic S3 protocol (S3_ENDPOINT_URL etc.)
    │   │       │                                        #   replication metric retrieval via boto3
    │   │       │                                        #   GetBucketReplication / GetMetric — Principle XVI
    │   │       ├── clickhouse.py                        # NEW — system.replication_queue query via the
    │   │       │                                        #   existing AsyncClickHouseClient from
    │   │       │                                        #   common/clients/clickhouse.py
    │   │       ├── qdrant.py                            # NEW — Qdrant cluster info HTTP probe
    │   │       ├── neo4j.py                             # NEW — Neo4j cluster overview procedure
    │   │       └── opensearch.py                        # NEW — OpenSearch _cluster/stats probe
    │   ├── repository.py                                # NEW — PostgreSQL queries for the 5 tables
    │   ├── router.py                                    # NEW — FastAPI routers: read at /api/v1/regions/*
    │   │                                                #   and /api/v1/maintenance/*; admin at
    │   │                                                #   /api/v1/admin/regions/* and
    │   │                                                #   /api/v1/admin/maintenance/* (rule 29)
    │   ├── events.py                                    # NEW — register the 5 constitutional event types
    │   │                                                #   (region.replication.lag,
    │   │                                                #   region.failover.initiated,
    │   │                                                #   region.failover.completed,
    │   │                                                #   maintenance.mode.enabled,
    │   │                                                #   maintenance.mode.disabled — already declared
    │   │                                                #   in constitution lines 768–772; this implements
    │   │                                                #   schemas under topic `multi_region_ops.events`)
    │   ├── exceptions.py                                # NEW — RegionNotFoundError → 404,
    │   │                                                #   ActiveActiveConfigurationRefusedError → 422,
    │   │                                                #   FailoverPlanNotFoundError → 404,
    │   │                                                #   FailoverInProgressError → 409 (FR-478.12),
    │   │                                                #   MaintenanceWindowOverlapError → 409,
    │   │                                                #   MaintenanceWindowInPastError → 422,
    │   │                                                #   MaintenanceModeBlockedError → 503 (raised by
    │   │                                                #   the middleware; carries window reason +
    │   │                                                #   ends_at)
    │   ├── dependencies.py                              # NEW — FastAPI deps; SecretProvider injection;
    │   │                                                #   reuses get_audit_chain_service (UPD-024),
    │   │                                                #   get_alert_service (feature 077),
    │   │                                                #   get_incident_trigger (feature 080)
    │   ├── middleware/
    │   │   ├── __init__.py
    │   │   └── maintenance_gate.py                      # NEW — MaintenanceGateMiddleware extends
    │   │                                                #   starlette.middleware.base.BaseHTTPMiddleware
    │   │                                                #   (same base as the existing AuthMiddleware
    │   │                                                #   at common/auth_middleware.py:90); short-
    │   │                                                #   circuits when FEATURE_MAINTENANCE_MODE=false;
    │   │                                                #   on POST/PUT/PATCH/DELETE and active window,
    │   │                                                #   returns 503 with announcement text;
    │   │                                                #   GET/HEAD/OPTIONS pass through; the active
    │   │                                                #   window is read from Redis (TTL-bounded,
    │   │                                                #   primed at enable time)
    │   └── jobs/
    │       ├── __init__.py
    │       ├── replication_probe_runner.py              # NEW — APScheduler job; iterates secondary
    │       │                                            #   regions × probe registry; writes
    │       │                                            #   replication_statuses + emits
    │       │                                            #   region.replication.lag events; on RPO
    │       │                                            #   breach, calls IncidentTriggerInterface.fire
    │       │                                            #   with condition_fingerprint =
    │       │                                            #   sha256(component + ":" + source_region +
    │       │                                            #   ":" + target_region) so dedup works
    │       │                                            #   (feature 080's fingerprint contract)
    │       ├── capacity_projection_runner.py            # NEW — APScheduler job; reads existing forecasts
    │       │                                            #   + usage rollups; writes capacity-alert rows
    │       │                                            #   into incident_response BC via
    │       │                                            #   IncidentTriggerInterface when projection
    │       │                                            #   crosses operator-configured saturation
    │       │                                            #   horizon (FR-482.3)
    │       └── maintenance_window_runner.py             # NEW — APScheduler job; transitions windows
    │                                                    #   from `scheduled` → `active` at starts_at;
    │                                                    #   from `active` → `completed` at ends_at
    │                                                    #   (the operator can also manually toggle —
    │                                                    #   the runner just enforces the schedule)
    │
    ├── common/
    │   ├── config.py                                    # MODIFIED — add 2 Pydantic feature-flag fields
    │   │                                                #   following the FEATURE_COST_HARD_CAPS pattern
    │   │                                                #   at :1555:
    │   │                                                #     feature_maintenance_mode: bool = Field(
    │   │                                                #       default=False,
    │   │                                                #       validation_alias=AliasChoices(
    │   │                                                #         "FEATURE_MAINTENANCE_MODE",
    │   │                                                #         "feature_maintenance_mode"))
    │   │                                                #     feature_multi_region: bool = Field(
    │   │                                                #       default=False,
    │   │                                                #       validation_alias=AliasChoices(
    │   │                                                #         "FEATURE_MULTI_REGION",
    │   │                                                #         "feature_multi_region"))
    │   │                                                #   plus add the canonical names to the
    │   │                                                #   __FEATURE_FLAGS_RUNTIME_MAPPING__ dict
    │   │                                                #   (≈ :900 per the existing pattern). Add
    │   │                                                #   MultiRegionOpsSettings sub-model:
    │   │                                                #     replication_probe_interval_seconds (60),
    │   │                                                #     rpo_alert_sustained_intervals (3),
    │   │                                                #     failover_lock_max_seconds (3600),
    │   │                                                #     capacity_projection_interval_seconds (3600),
    │   │                                                #     maintenance_announcement_lead_minutes (60).
    │   └── database.py                                  # NO change — the asyncpg pool used by the
    │                                                    #   PostgreSQL probe is the existing one
    │
    └── main.py                                          # MODIFIED — at the existing middleware
                                                         #   registration site (:1298–1302), insert
                                                         #     app.add_middleware(MaintenanceGateMiddleware)
                                                         #   ABOVE AuthMiddleware (so 503 short-circuit
                                                         #   happens before auth — auth-required calls
                                                         #   during maintenance return 503, not 401);
                                                         #   register the 3 APScheduler jobs (guarded
                                                         #   by `settings.runtime_profile == "scheduler"`)

deploy/helm/
├── platform/
│   ├── values-multi-region.yaml                         # NEW — secondary-region overlay (operator
│   │                                                     #   sets `multi_region.enabled: true`,
│   │                                                     #   `multi_region.role: secondary`,
│   │                                                     #   replication endpoint refs)
│   └── templates/
│       └── replication-jobs/                            # NEW — follows the existing
│           ├── postgres-streaming-replica.yaml          #   deploy/helm/control-plane/templates/
│           ├── kafka-mirrormaker.yaml                   #   migration-job.yaml shape (Job /
│           ├── s3-cross-region.yaml                     #   CronJob templates that the secondary
│           ├── clickhouse-replication.yaml              #   region's chart applies)
│           ├── qdrant-replica.yaml
│           ├── neo4j-replica.yaml
│           └── opensearch-replica.yaml
└── observability/templates/dashboards/
    └── multi-region-ops.yaml                            # NEW — Grafana dashboard ConfigMap (rule 24)

deploy/runbooks/
├── failover.md                                          # NEW — operator-procedure runbook for the
│                                                         #   primary→secondary cutover; linked from the
│                                                         #   regions panel (FR-478.14, FR-CC-7);
│                                                         #   referenced from runbook entries seeded by
│                                                         #   feature 080 (the `region_failover` scenario
│                                                         #   in incident_response/seeds/runbooks_v1.py
│                                                         #   if added there)
└── zero-downtime-upgrade.md                             # NEW — expand-migrate-contract pattern
                                                          #   procedure with rollback + rollback-fails
                                                          #   branches (FR-480, FR-480.6); linked from
                                                          #   the operator dashboard (FR-480.5)

apps/web/
├── app/(main)/operator/
│   └── page.tsx                                         # MODIFIED — extend the `PANELS` const at
│                                                         #   :39–41 with `regions`, `maintenance`,
│                                                         #   `capacity`; resolvePanel() picks them up
│                                                         #   via the existing SearchParams pattern
└── components/features/multi-region-ops/                # NEW — RegionsPanel, ReplicationStatusTable,
                                                          #   ReplicationLagChart, FailoverPlanList,
                                                          #   FailoverPlanComposer, FailoverPlanRunHistory,
                                                          #   MaintenancePanel, MaintenanceWindowForm,
                                                          #   MaintenanceWindowList,
                                                          #   ActiveWindowBanner (the operator-side
                                                          #   live status pill — separate from the
                                                          #   user-facing PlatformStatusBanner),
                                                          #   CapacityPanel, CapacityHistoryChart,
                                                          #   CapacityProjectionChart,
                                                          #   CapacityRecommendationCard

tests/control-plane/unit/multi_region_ops/
├── test_region_service.py                               # NEW — CRUD + active-active refusal (FR-479.2)
├── test_replication_monitor.py                          # NEW — probe runner iteration; RPO breach
│                                                         #   triggers IncidentTriggerInterface;
│                                                         #   sustained-interval logic
├── test_failover_service.py                             # NEW — plan authoring; lock acquisition;
│                                                         #   step halting on failure (FR-478.11);
│                                                         #   concurrent refusal (FR-478.12, SC-005)
├── test_maintenance_mode_service.py                     # NEW — schedule / enable / disable;
│                                                         #   window state machine; overlap detection;
│                                                         #   past-window rejection
├── test_maintenance_gate_middleware.py                  # NEW — POST/PUT/PATCH/DELETE return 503 with
│                                                         #   announcement; GET/HEAD/OPTIONS pass;
│                                                         #   feature-flag-off short-circuit; Redis
│                                                         #   miss fail-open behaviour
├── test_capacity_service.py                             # NEW — composes existing signals; never
│                                                         #   re-implements forecasting; saturation
│                                                         #   horizon evaluation
├── test_probes_postgres.py                              # NEW — pg_stat_replication parsing
├── test_probes_kafka.py                                 # NEW — admin-client mock for consumer-group lag
├── test_probes_s3.py                                    # NEW — boto3 mock for replication metrics
├── test_probes_clickhouse.py                            # NEW — system.replication_queue parsing
├── test_probes_qdrant.py                                # NEW — cluster-info HTTP mock
├── test_probes_neo4j.py                                 # NEW — cluster-overview procedure mock
├── test_probes_opensearch.py                            # NEW — _cluster/stats HTTP mock
└── test_event_registration.py                           # NEW — all 5 region/maintenance event types
                                                          #   registered

tests/control-plane/integration/multi_region_ops/
├── test_replication_lag_alerts.py                       # NEW — SC-002 — inject lag, confirm alert
│                                                         #   fires through IncidentTriggerInterface,
│                                                         #   resolves on lag clearing
├── test_failover_plan_rehearsal.py                      # NEW — SC-003 — per-step outcomes recorded;
│                                                         #   broken step halts execution
├── test_failover_plan_concurrent_initiation.py          # NEW — SC-005 — second initiator refused
├── test_failover_plan_staleness_flag.py                 # NEW — SC-004 — non-rehearsed plan flagged
├── test_maintenance_window_lifecycle.py                 # NEW — SC-006 + SC-008 — schedule, enable,
│                                                         #   announcement visible, disable, resume
├── test_maintenance_gate_blocks_writes.py               # NEW — SC-006 — every mutating endpoint
│                                                         #   returns 503; every read endpoint passes
├── test_in_flight_execution_drains.py                   # NEW — SC-007 — execution started before
│                                                         #   enable runs to completion
├── test_capacity_alert_pre_saturation.py                # NEW — SC-012 — alert ahead of saturation;
│                                                         #   recommendation links resolve
├── test_admin_audit_chain_emission.py                   # NEW — SC-013 — every admin action emits
│                                                         #   audit-chain entry
└── test_workspace_archival_preserves_records.py         # NEW — FR-CC-6

tests/e2e/suites/multi_region_ops/
├── test_secondary_region_replication.py                 # NEW — kind cluster with mock secondary;
│                                                         #   end-to-end replication path
├── test_maintenance_drains_cleanly.py                   # NEW — operator journey: schedule, enable,
│                                                         #   in-flight drains, disable, resume
└── test_failover_rehearsal_audited.py                   # NEW — operator journey: rehearse + record
```

**Structure Decision**: One new bounded context (`multi_region_ops/`), aligned with the constitution's existing declaration that `multi_region_ops/` owns UPD-025 (Constitution § "New Bounded Contexts" line 492). One small middleware addition to the existing FastAPI stack at `main.py:1298–1302` (the maintenance gate sits ABOVE auth so 503-during-maintenance short-circuits before auth-required routes return 401 — operationally clearer for callers). Two surgical extensions to `common/config.py` to add the constitutional feature flags as Pydantic settings fields. Helm overlay extends the existing `deploy/helm/platform/` chart additively rather than forking. Frontend extends the existing operator dashboard panel registry following the `resolvePanel()` SearchParams pattern at `apps/web/app/(main)/operator/page.tsx:39–41`. Two operator runbooks (`failover.md`, `zero-downtime-upgrade.md`) are first-class deliverables of this feature, not afterthoughts — the spec explicitly requires them reachable from the operator dashboard (FR-480.5, FR-CC-7).

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Five PostgreSQL tables (the four from the brownfield input + `failover_plan_runs`) | The brownfield input proposed `failover_plans` with two timestamp columns (`tested_at`, `last_executed_at`). Spec FR-478.10 requires every action MUST be auditable end-to-end, and SC-014 requires quarterly rehearsal outcomes reviewable for ≥ 1 year. Two timestamps cannot represent run history with per-step outcomes. The fifth table is the per-execution audit-grade record that links the plan, the actor, the per-step outcome, and the run kind (rehearsal vs production). | Storing run history in `failover_plans.runs` JSONB: rejected — concurrent rehearsals on different plans would race; queryability for the dashboard's "rehearsal history" panel would be poor; row size grows unboundedly. |
| `ReplicationProbe` Protocol with seven adapters instead of one generic probe | Each data store exposes lag through a different native interface — PostgreSQL has `pg_stat_replication`, Kafka has consumer-group lag via the admin client, ClickHouse has `system.replication_queue`, etc. A single "generic probe" would have to embed seven different query mechanisms in one place, conflating concerns. The Protocol keeps each adapter narrow, individually testable, and replaceable. | One large `replication_monitor.py` with all seven probe paths inline: rejected — would couple unrelated concerns and make per-store testing harder. |
| Maintenance gate as FastAPI middleware (not per-endpoint dependency) | Applying maintenance enforcement per-endpoint would require annotating dozens of routers individually, would miss future endpoints by default (a closed safety posture would have to be re-applied to every new router), and would not naturally distinguish HTTP method classes. The middleware sees every request, decides on method (allow GET/HEAD/OPTIONS, block mutating verbs), and is uniform across the entire API surface. | Per-endpoint `Depends(maintenance_gate)`: rejected — coverage gaps as new endpoints land; doubles the surface area. |
| Maintenance gate fails OPEN on Redis miss (NOT closed) | This is a deliberate inversion of the rule-41 fail-closed principle. Rule 41 governs *authentication paths* — Vault failure must not bypass auth. The maintenance gate is *not* an authentication path; it is cooperative infrastructure protection during planned downtime. A Redis blip during normal operation should NOT falsely block all writes (that would be a production outage caused by a cache hiccup). On miss, the middleware queries PG (the truth source) and primes Redis. If both Redis AND PG are unreachable, fails open with a structured-log critical so the operator notices the cache-miss-cascade, but writes continue. The plan documents this inversion explicitly so future reviewers do not "fix" it as a rule-41 violation. | Fail closed on cache miss: rejected — would turn ordinary Redis blips into platform-wide write outages. |
| Maintenance gate registered ABOVE auth in the middleware stack | Stack order is bottom-up evaluation in Starlette — registering above auth means maintenance is checked AFTER auth in execution order. Wait, no: ASGI middleware evaluates in registration order on inbound, so registering ABOVE auth means MaintenanceGate evaluates BEFORE auth. That gives 503-during-maintenance for unauthenticated callers (they see the maintenance message, not a 401-then-503-on-retry). Operationally cleaner: callers don't need credentials to discover the platform is in maintenance. | Registering below auth: rejected — unauthenticated callers would get 401 first, retry with credentials, then get 503; doubles the retry pressure during an outage. |
| Redis distributed lock for failover initiation | Spec FR-478.12 + SC-005 require concurrent attempts to start the same plan return exactly one running plan. A PostgreSQL row lock would serialize per row but does not survive process death (e.g., the operator's browser closing mid-plan). The Redis-based lock has a TTL = `failover_lock_max_seconds` so a crashed initiator's lock auto-expires. | PG advisory lock: rejected — no auto-expiry on initiator crash; would leave the second initiator blocked indefinitely. |
| Capacity surface composes existing signals rather than re-implementing | Spec FR-482.6 explicitly says cost forecasts MUST be referenced from the capacity view rather than re-implemented. Feature 079 already implements forecasting (`cost_governance/repository.py:321`); feature 020 / `analytics/` already implements usage rollups. The capacity service is a thin composer + saturation-threshold evaluator + alert router. | Re-implementing forecasting in this BC: rejected — explicitly forbidden by the spec; would create two divergent forecast paths. |
| Two-table-touch failover plan ⇄ run instead of single-shot RPC | Failover plan execution is multi-second to multi-minute; the operator UI needs progress visibility. A single-shot synchronous RPC would block the request thread for the full duration. Recording the plan run as a row at start and updating per-step lets the dashboard poll progress; the run record is the audit trail for free. | Synchronous in-request execution: rejected — would block the HTTP worker thread for minutes; no progress visibility. |
| Replication-probe runner runs ONLY on the `scheduler` runtime profile | The control-plane is deployed as multiple runtime profiles (api, scheduler, worker, projection-indexer, etc. — Constitution § Core I). Probing every store from every profile would multiply load by the profile count. Running on the dedicated scheduler profile keeps probe load constant regardless of API replica count. | Probe runs on every profile: rejected — would scale probe load with API replica count, hammering the source stores. |

## Dependencies

- **`audit/` BC (existing)** — `AuditChainService.append` at `audit/service.py:48–72` is the canonical write path required by constitution rule 9 + 32 for every administrative action. Confirmed unchanged from UPD-024.
- **`notifications/` BC (feature 077)** — `AlertService` at `notifications/service.py:64–575`; methods `process_attention_request` (`:167`) and `process_state_change` (`:203`) are the routing entry points for the operator-side capacity and replication alerts. The alerts route through these methods rather than introducing a parallel notification path (FR-CC-4).
- **`incident_response/` BC (feature 080)** — `IncidentTriggerInterface` at `incident_response/trigger_interface.py:8–48`; module-level global `_incident_trigger` bound in lifespan at `main.py:461`. RPO/RTO breaches and failover failures fire through `get_incident_trigger().fire(signal)` (FR-CC-5). The fingerprint contract from feature 080 (`sha256(component + ":" + source_region + ":" + target_region)`) ensures dedup works end-to-end.
- **`cost_governance/` BC (feature 079)** — `CostGovernanceService.get_latest_forecast(workspace_id)` at `cost_governance/repository.py:321–328` is the source the capacity view reads forecasts from (FR-482.6).
- **`analytics/` BC (existing)** — usage rollups read by `capacity_service.py` for the historical-trend panel.
- **`workspaces/` BC (existing)** — archival hook on `workspaces/service.py` for FR-CC-6 records preservation.
- **`security_compliance/` BC (UPD-024)** — `SecretProvider.get_current()` (`common/clients/model_router.py:43–44`; `RotatableSecretProvider` at `security_compliance/providers/rotatable_secret_provider.py:21`) resolves all per-store probe credentials.
- **`SecretProvider` Protocol** — frozen contract; injected as a FastAPI dependency.
- **`common/database.py`** — existing asyncpg pool used by the PostgreSQL probe.
- **`common/clients/clickhouse.py`** — existing `AsyncClickHouseClient` used by the ClickHouse probe.
- **Existing FastAPI middleware site** — `main.py:1298–1302` is where `MaintenanceGateMiddleware` registers, ABOVE `AuthMiddleware`.
- **Existing `apps/web/app/(main)/operator/page.tsx`** — the `resolvePanel()` SearchParams pattern at `:39–41` is the extension point for the three new panels (`regions`, `maintenance`, `capacity`).
- **Constitution § Kafka Topics Registry (lines 768–772)** — the 5 region/maintenance event types are already declared. This feature implements their schemas under topic `multi_region_ops.events` (consistent with `analytics.events`, `notifications.events`, `incident_response.events`); no topic-registry change.
- **Constitution § REST Prefix Registry (lines 798–799)** — `/api/v1/regions/*` and `/api/v1/maintenance/*` already declared; admin authoring uses the segregated `/api/v1/admin/*` prefix per rule 29.
- **Constitution § Feature Flag Inventory (lines 888–889)** — `FEATURE_MAINTENANCE_MODE` and `FEATURE_MULTI_REGION` are constitutional names; this plan adds the Pydantic settings binding to `common/config.py` following the existing `FEATURE_COST_HARD_CAPS` pattern (`:1555`).
- **APScheduler** — already in the runtime; the three new jobs (replication probe, capacity projection, maintenance window state-transition) run on the existing `scheduler` profile.
- **Existing Helm chart at `deploy/helm/platform/`** — extended additively. The replication-jobs templates follow the `deploy/helm/control-plane/templates/migration-job.yaml` shape.
- **`aiokafka.admin.AIOKafkaAdminClient`** — already shipped with the existing aiokafka 0.11+ version.

## Wave Placement

**Wave 9** — placed after notifications (feature 077, Wave 5), cost governance (feature 079, Wave 7), and incident response (feature 080, Wave 8) so all three integration-target BCs exist when this feature wires into them. The brownfield input nominated Wave 6, but the spec's Cross-Cutting requirements (FR-CC-4, FR-CC-5, FR-CC-6) explicitly route through features 077 / 079 / 080 — placing this in Wave 6 would either require a fork-and-rejoin in those features' integration paths or re-implementing the cross-cutting concerns locally (which the spec forbids). Wave 9 keeps the dependency graph clean.

**Note on the input's effort estimate** — the planning input estimated 4 story points (~2 days). The plan as designed is materially larger than that:

- **5 PG tables** + Alembic migration
- **2 Pydantic settings fields** + `MultiRegionOpsSettings` sub-model in `common/config.py`
- **1 new BC** with router, service facade, 5 sub-services, repository, schemas, exceptions, events, dependencies, middleware
- **7 per-store replication probes** (PostgreSQL, Kafka, S3, ClickHouse, Qdrant, Neo4j, OpenSearch) — each requires understanding the native lag-query mechanism of that store
- **1 FastAPI middleware** on the hot path (every request) with measured fail-open semantics
- **3 APScheduler jobs** (probe runner, capacity projection runner, window state-transition runner)
- **5 Kafka event schemas** wired to the constitutional topic names
- **2 REST router groups** (read + admin segregation per rule 29) with full CRUD across regions, plans, plan runs, and maintenance windows
- **1 Helm overlay** + **7 replication-job templates** + **1 Grafana dashboard ConfigMap**
- **2 operator runbooks** (`failover.md`, `zero-downtime-upgrade.md`) — first-class deliverables per FR-480.5, FR-CC-7
- **3 frontend panels** under the existing operator dashboard (regions, maintenance, capacity) plus 14 components
- **Unit + integration + E2E test coverage** across all of the above with ≥ 95% line coverage per Constitution § Quality Gates

Realistically this is ~3-4× the input's estimate. The Wave Placement reflects the true scope; consider revising the estimate once `tasks.md` enumerates the work or descoping (e.g., ship Wave 9A with the 3 most-critical probes — PostgreSQL, Kafka, S3 — and Wave 9B with the remaining 4) if the 2-day budget is firm.
