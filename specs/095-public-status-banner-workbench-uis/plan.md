# Implementation Plan: UPD-045 — Public Status Page, Platform State Banner, and Remaining Workbench UIs

**Branch**: `095-public-status-banner-workbench-uis` | **Date**: 2026-04-28 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

UPD-045 makes the platform's state visible to the people affected by it — across an operationally-independent public status surface, an in-shell `<PlatformStatusBanner>`, graceful maintenance UX — and closes the remaining UI gaps in the simulation and scientific-discovery workbenches. The planning input partitions the work into three independent tracks; brownfield research confirms two non-trivial corrections that the plan adopts:

1. **Discovery is frontend-only**, not "extends backend". `apps/control-plane/src/platform/discovery/router.py:62-361` already exposes session CRUD, hypothesis listing/detail, hypothesis→experiment trigger, experiment execute/get, critiques, and proximity graph endpoints. Track C does NOT add discovery backend code.
2. **Simulation digital-twin endpoints already exist** (`POST /api/v1/simulations/twins`, `…/predict`, `POST /api/v1/simulations/{run_id}/compare`); only **scenario CRUD** is greenfield. `<DigitalTwinPanel>` is frontend-only on top of the existing twin/comparison routes.

Three parallel tracks (the user's planning-input ordering, kept):

- **Track A — Public status surface + subscription** (~3 dev-days). NEW `status_page/` bounded context (`apps/control-plane/src/platform/status_page/`) owning: (a) public endpoints (auth-exempt via the established `EXEMPT_PATHS` mechanism — NOT a separate `/api/public/` router-tree, per spec brownfield reconciliation #9); (b) Kafka consumer for `multi_region_ops.events` (maintenance) + `incident_response.events` + a 60-second poll of platform component health; (c) `PlatformStatusSnapshot` projection in PostgreSQL + Redis hot-cache; (d) RSS/Atom feed generation; (e) email subscription (confirm-opt-in) + webhook subscription (HMAC via the existing `notifications/deliverers/webhook_deliverer.py` pattern — Rule 17). NEW `apps/web-status/` Next.js static-export site deployed in `platform-edge` namespace as a tiny independent pod with its own Ingress (Rule 49).

- **Track B — In-shell banner + maintenance UX** (~2 dev-days). NEW `<PlatformStatusBanner>` global component injected into `apps/web/app/(main)/layout.tsx:51` (above `<Header />`). NEW `<MaintenanceBlockedAction>` modal triggered by 503 responses with a maintenance-aware error envelope. Extends `apps/web/lib/ws.ts` `WsChannel` type union with `"platform-status"`; backend extends the `ws_hub/subscription.py` `ChannelType` enum with the matching value. WebSocket fan-out from `multi_region_ops.events` and `incident_response.events` to the new channel. Falls back to polling `/api/v1/me/platform-status` on WS disconnect.

- **Track C — Simulation scenario editor + discovery workbench completion** (~3 dev-days). Backend: 5 NEW REST endpoints under `/api/v1/simulations/scenarios/*` consumed by NEW `simulation_scenarios` table (existing `simulation_runs` reused unchanged for launches). Frontend: 3 new simulation pages (`scenarios/`, `scenarios/new/`, `scenarios/[id]/`) + `<DigitalTwinPanel>` extension to existing run detail page; 5 new discovery pages (session detail, hypotheses, experiments list + new, evidence inspector). The existing `/discovery/{session_id}/network/page.tsx` is reused unchanged via the new tabbed session-detail view (no Cytoscape introduced — XYFlow + Dagre is canonical per spec reconciliation #8 and `apps/web/components/features/discovery/HypothesisNetworkGraph.tsx`).

- **Integration — E2E coverage** (~1 dev-day). NEW `tests/e2e/journeys/test_j21_platform_state.py` (synthetic-incident-driven full-loop). NEW journey skeletons `test_j07_evaluator.py` and `test_j09_scientific_discovery.py` (per spec reconciliation #11 — these journeys are net-new, not extensions, despite the planning-input's wording). NEW E2E suite directories `tests/e2e/suites/platform_state/`, `tests/e2e/suites/simulation_ui/`, `tests/e2e/suites/discovery_ui/` (the harness has integration tests under `apps/control-plane/tests/integration/` but no `tests/e2e/` tree yet — first feature in this UPD cycle to seed it; if UPD-035 lands first, we inherit it).

**Total effort estimate: 9 dev-days** (planning-input said 6 days; reasons for the +3 are documented under "Effort Reconciliation" below). With 3 devs in parallel, wall-clock is **~4 days**.

## Effort Reconciliation vs Planning Input

| Item | Input estimate | Plan estimate | Delta rationale |
|---|---:|---:|---|
| Track A | 2 d | 3 d | +1d for the operationally-independent topology (Rule 49) — separate `apps/web-status/` Next.js project, separate Ingress, separate pod, separate cache fallback. The input under-weights "page must stay up when the platform is down". |
| Track B | 1.5 d | 2 d | +0.5d for `<MaintenanceBlockedAction>` modal wiring across the existing fetch wrapper (`apps/web/lib/api.ts`) — must intercept 503 with a maintenance envelope and surface the modal globally without per-button instrumentation. |
| Track C | 2.5 d | 3 d | +0.5d for the **scenarios → runs** plumbing: launching a scenario with N iterations queues N existing `simulation_runs` rows; the linkage requires a new FK column (`simulation_runs.scenario_id`, additive nullable) per Brownfield Rule 7. The input under-weights this. |
| E2E | 1 d | 1 d | unchanged |
| **Total** | **6 d** | **9 d** | matches the v1.3.0 cohort sizing observed in features 087, 092–094 (consistent under-estimate in planning inputs). |

## Constitutional Anchors

| Anchor | Citation | Implementation tie |
|---|---|---|
| **Rule 4 — use existing patterns** | `.specify/memory/constitution.md:84-87` | Track A reuses `notifications/deliverers/webhook_deliverer.py:43-89` for HMAC subscription delivery; reuses the auth-middleware exempt-paths pattern (`auth_middleware.py:13-32`) instead of a parallel router-tree. |
| **Rule 9 — every PII operation emits audit chain** | `.specify/memory/constitution.md:118-121` | Email subscription confirmation, unsubscribe events, webhook subscription registration all emit audit-chain entries via `security_compliance/services/audit_chain_service.py`. |
| **Rule 13 — every user-facing string via `t()`** | `.specify/memory/constitution.md:136-138` | Track B + Track C add ~120 i18n keys × 6 locales (en, es, de, fr, it, zh-CN — the FR-620 canonical set). See Phase 0 R3 for the `apps/web/messages/ja.json` artifact note. |
| **Rule 17 — outbound webhooks HMAC-signed** | `.specify/memory/constitution.md:149-152` | Status-page subscription webhooks reuse `webhook_deliverer.send_signed()` with the existing `OutboundWebhook` table and `webhook_deliveries` retry envelope; no new signing primitive. |
| **Rule 21 — correlation IDs in middleware** | `.specify/memory/constitution.md:163-167` | New public endpoints have correlation IDs generated at ingress (visitor has no `user_id`; `correlation_id` + `trace_id` only). |
| **Rule 28 / Rule 41 — accessibility AA tested** | `.specify/memory/constitution.md:190-192, 1042-1044` | Banner, modal, scenario editor, hypothesis library, evidence inspector all pass axe-core AA in J21/J07/J09; CI fails build on any serious/critical violation. |
| **Rule 45 — every backend capability has UI** | `.specify/memory/constitution.md:258-262` | Subscriptions get an authenticated management surface at `/settings/status-subscriptions` — anonymous-visitor confirmation tokens are not the only mechanism for managing them. |
| **Rule 48 — platform state is user-visible** | `.specify/memory/constitution.md:274-277` | THE canonical anchor for Track B. `<PlatformStatusBanner>` replaces silent 503s and "errors out of nowhere". |
| **Rule 49 — public status page operationally independent** | `.specify/memory/constitution.md:278-281` | THE canonical anchor for Track A's topology. The `apps/web-status/` site is a separate Next.js static export, deployed as a separate Deployment with its own Ingress, in `platform-edge` namespace; serves a "last known state" fallback page when its own pod cannot reach the status API. |
| **Rule 50 — mock LLM for creator previews** | `.specify/memory/constitution.md:282-286` | Scenario preview defaults to the `MockLLMProvider` introduced by UPD-044 (feature 094). Real-LLM preview reuses `<RealLLMOptInDialog>` from `apps/web/app/(main)/agent-management/[fqn]/contract/_components/RealLLMOptInDialog.tsx` (the "USE_REAL_LLM" confirmation-text gate). NO new dialog primitive. |
| **Principle V — append-only journal** | `.specify/memory/constitution.md:346-349` | Scenario launches produce normal `simulation_runs` rows; we add an additive `scenario_id` FK column — never mutate existing run rows. |
| **Principle VII — simulation isolation** | `.specify/memory/constitution.md:358-364` | Scenario runs continue to execute in the existing `platform-simulation` namespace via the existing `simulation_controller`; scenario CRUD only touches control-plane PostgreSQL. |
| **Principle XI — secrets never in LLM context** | `.specify/memory/constitution.md:391-397` | Scenario inputs that reference workspace secrets continue to flow through the runtime controller's secret injection — scenario JSON itself MUST NOT embed plaintext secrets (validation rejects). |
| **FR-675 → FR-682 (Section 118)** | `docs/functional-requirements-revised-v6.md:3594-3618` | Each spec FR-695-XX rolls up to one of FR-675…FR-682 (see spec.md "Functional Requirements" section). |

**Verdict: gate passes.** No declared variances.

## Technical Context

| Item | Value |
|---|---|
| **Languages** | Python 3.12+ (control plane — NEW `status_page/` BC + `simulation/` extension + Alembic migration); TypeScript 5.x (in-shell additions to `apps/web/` + NEW `apps/web-status/` static-export site); YAML (Helm overlay for the new `web-status` Deployment + Ingress + RBAC for the new CronJob). NO Go changes. |
| **Primary Dependencies (existing — reused)** | FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+, redis-py 5.x async, httpx 0.27+ (status snapshot poller), APScheduler 3.x (60s snapshot generator + 30d uptime rollup), `feedgen` (RSS/Atom — NEW dep, ~50KB pure-Python — see Phase 0 R2). Frontend reuses next-intl (apps/web), `@xyflow/react` 12+ (HypothesisNetworkGraph reused unchanged), shadcn/ui, React Hook Form + Zod, TanStack Query v5, Zustand 5.x, Lucide React. |
| **Primary Dependencies (NEW)** | Backend: `feedgen` (Atom + RSS 2.0 producer; reviewed for stdlib-only fallback in R2). Frontend: NONE — `apps/web-status/` reuses the existing Next.js + Tailwind + shadcn stack from `apps/web/`. Infra: NONE — no new operator. |
| **Storage** | PostgreSQL — Alembic migration `095_status_page_and_scenarios.py` (next available slot — UPD-044 owns 094 per neighbour plan; verified in Phase 0 R5): (a) NEW `platform_status_snapshots` table (id UUID PK, generated_at timestamptz, overall_state varchar(32), payload JSONB, source_kind varchar(32) — `kafka`/`poll`/`fallback`); (b) NEW `status_subscriptions` table (id UUID PK, channel varchar(16) — `email`/`rss`/`atom`/`webhook`/`slack`, target text, scope_components text[], confirmation_token_hash bytea, confirmed_at timestamptz NULL, health varchar(16), workspace_id UUID NULL — populated for authenticated subscriptions, user_id UUID NULL, created_at, updated_at); (c) NEW `subscription_dispatches` table (id UUID PK, subscription_id FK ON DELETE CASCADE, event_kind varchar(32) — `incident.created`/`incident.updated`/`incident.resolved`/`maintenance.scheduled`/`maintenance.started`/`maintenance.ended`, dispatched_at timestamptz, outcome varchar(16), webhook_signature_kid varchar(64) NULL, error_summary text NULL); (d) NEW `simulation_scenarios` table (id UUID PK, workspace_id FK, name varchar(255), description text, agents_config JSONB, workflow_template_id UUID FK NULL, mock_set_config JSONB, input_distribution JSONB, twin_fidelity JSONB, success_criteria JSONB, run_schedule JSONB NULL, archived_at timestamptz NULL, created_by FK, created_at, updated_at); (e) NEW additive nullable column `simulation_runs.scenario_id` (FK ON DELETE SET NULL). Redis — 3 NEW key patterns: `status:snapshot:current` (TTL 90s — hot read for public endpoints), `status:fallback:lastgood` (TTL 24h — last-known-good for outage fallback), `status:subscribe:rate:{ip}` (sliding window, TTL 1h — rate limit). Kafka — NO new topics; consumes existing `multi_region_ops.events`, `incident_response.events`. NO Vault paths owned by this feature — webhook signing secrets continue to live in `OutboundWebhook.signing_secret_ref` per UPD-028. |
| **Testing** | pytest 8.x + pytest-asyncio (control-plane unit + integration tests for `status_page/` BC, scenario CRUD, snapshot generator, subscription dispatch — ~80 cases); Vitest + RTL for `<PlatformStatusBanner>`, `<MaintenanceBlockedAction>`, `<DigitalTwinPanel>`, `<SimulationScenarioEditor>`, hypothesis library, experiment launcher, evidence inspector; Playwright for the in-app journeys; pytest E2E suites at `tests/e2e/suites/{platform_state,simulation_ui,discovery_ui}/` (NEW directories — see Phase 0 R6); axe-core CI gate per Rule 41. |
| **Target Platform** | Linux x86_64, Kubernetes 1.28+, Python 3.12, Node 20+ (Next.js 14). The `apps/web-status/` static export targets any S3-compatible bucket + Nginx, or a vanilla pod serving `out/`. |
| **Project Type** | Cross-stack feature: control-plane Python + frontend TypeScript + new tiny static site + Helm overlay. NO Go service work. |
| **Performance Goals** | Public `/api/v1/public/status` p95 ≤ 200ms (Redis hot path); page first-paint ≤ 2s p95 from cold cache (SC-001); banner reflects state changes ≤ 5s p95 via WebSocket (SC-002), ≤ 60s polling fallback; subscription dispatch ≤ 2 minutes p95 from incident lifecycle event (SC-003); RSS/Atom freshness ≤ 60s p95 (SC-003); status endpoint sustains 10× burst from edge cache without origin degradation (SC-013). |
| **Constraints** | Rule 49 — `apps/web-status/` deployment topology MUST NOT share a single point of failure with the main platform; Rule 48 — banner replaces silent 503s; Rule 50 — scenario preview defaults to mock LLM; Principle VII — scenario runs stay in `platform-simulation` namespace; Brownfield Rule 7 — `simulation_runs.scenario_id` MUST be additive nullable. |
| **Scale / Scope** | Track A: 1 NEW BC (~600 LOC Python including consumer, snapshot generator, subscription service, dispatch worker, RSS/Atom builders), 1 Alembic migration (~80 LOC for 4 tables + 1 column), ~12 new endpoints (4 public + 5 authenticated subscription mgmt + 1 internal-cron-trigger + 2 admin-debug), 1 new auth-exempt path family (5 paths), 1 new WS channel, NEW `apps/web-status/` Next.js project (~400 LOC TS — pages: index, components/[id], history, subscribe, confirm, unsubscribe), NEW Helm overlay for `web-status` Deployment + Ingress (~80 LOC YAML); ~30 unit + ~10 integration tests. Track B: ~10 new components + 4 new hooks (~1200 LOC TS) in `apps/web/`, ~80 i18n keys × 6 locales. Track C: 5 new endpoints + 1 service class (~200 LOC Python), 8 new pages + ~15 components (~2000 LOC TS), ~140 i18n keys × 6 locales. E2E: 3 new journey files + 12 new suite test files (~1200 LOC pytest). **Total: ~6500 LOC across Python + TS + YAML + ~220 i18n entries × 6 locales = ~1320 catalog entries.** |

## Constitution Check

> **GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.**

| Check | Verdict | Rationale |
|---|---|---|
| Brownfield Rule 1 — never rewrite | ✅ Pass | Discovery backend untouched. Simulation backend extended additively (1 nullable column on existing `simulation_runs`, NEW `simulation_scenarios` table). Maintenance and incident backends untouched (consumer-only). Existing `/discovery/{session_id}/network/page.tsx` reused as tab content unchanged. |
| Brownfield Rule 2 — Alembic-only DDL | ✅ Pass | Single migration `095_status_page_and_scenarios.py` covers all schema work. |
| Brownfield Rule 4 — use existing patterns | ✅ Pass | Auth-exempt list extension (R1), `OutboundWebhook` reuse for status webhooks (R7), `RealLLMOptInDialog` reuse (R8), XYFlow reuse for hypothesis network (R9), bounded-context structure for `status_page/` (R10). |
| Rule 9 — audit chain | ✅ Pass | Subscription confirm/unsubscribe + admin status overrides emit audit-chain entries. |
| Rule 17 — HMAC webhooks | ✅ Pass | Status webhook subscriptions reuse the existing `webhook_deliverer.send_signed()` path. |
| Rule 28 / Rule 41 — axe-core AA | ✅ Pass | J21/J07/J09 each include axe-core assertions on the new pages and components. |
| Rule 45 — backend capability has UI | ✅ Pass | Subscription mgmt at `/settings/status-subscriptions` covers the authenticated user surface; anonymous-visitor flow on the public site covers the visitor surface. |
| Rule 48 — platform state user-visible | ✅ Pass | `<PlatformStatusBanner>` injected into the authenticated shell layout; `<MaintenanceBlockedAction>` replaces 503 error pages. |
| Rule 49 — public status independence | ✅ Pass | `apps/web-status/` is a separate Next.js project, separate Deployment, separate Ingress, separate namespace; runs a "last known good" service-worker-cached fallback when its own status API is unreachable. |
| Rule 50 — mock LLM for creator previews | ✅ Pass | Scenario preview defaults to `MockLLMProvider` (UPD-044). Real-LLM preview reuses `<RealLLMOptInDialog>` — no new gate primitive. |
| Principle V — append-only journal | ✅ Pass | No journal mutation; scenario runs are normal `simulation_runs` rows. |
| Principle VII — simulation isolation | ✅ Pass | Scenario execution remains in `platform-simulation` namespace. |
| Principle XI — secrets never in LLM context | ✅ Pass | Scenario JSON validation rejects plaintext secrets in `mock_set_config` / `input_distribution`. |

**Verdict: gate passes. No declared variances.**

## Project Structure

### Documentation (this feature)

```text
specs/095-public-status-banner-workbench-uis/
├── plan.md                # this file (Phase 2 output)
├── spec.md                # already authored
├── planning-input.md      # original user planning input (verbatim)
├── research.md            # Phase 0 — research findings (R1..R12)
├── data-model.md          # Phase 1 — entities + relationships
├── quickstart.md          # Phase 1 — developer guide
├── contracts/             # Phase 1 — public + authenticated endpoint contracts + WS envelope
│   ├── public-status-api.openapi.yaml
│   ├── public-subscription-api.openapi.yaml
│   ├── authenticated-subscription-api.openapi.yaml
│   ├── simulation-scenarios-api.openapi.yaml
│   ├── platform-status-ws.md
│   └── feed-formats.md
├── checklists/
│   └── requirements.md    # spec quality checklist (already authored)
└── tasks.md               # Phase 3 — produced by /speckit.tasks (NOT by this command)
```

### Source Code (repository root) — files this feature creates or modifies

```text
# === Track A — Public status surface + subscription ===
apps/control-plane/migrations/versions/095_status_page_and_scenarios.py        # NEW — 4 tables + 1 nullable FK column
apps/control-plane/src/platform/status_page/__init__.py                        # NEW
apps/control-plane/src/platform/status_page/models.py                          # NEW (~140 LOC) — PlatformStatusSnapshot, StatusSubscription, SubscriptionDispatch
apps/control-plane/src/platform/status_page/schemas.py                         # NEW (~120 LOC) — Pydantic request/response
apps/control-plane/src/platform/status_page/repository.py                      # NEW (~110 LOC) — async SQLAlchemy queries
apps/control-plane/src/platform/status_page/service.py                         # NEW (~220 LOC) — snapshot composition (maintenance + incidents + component health), subscription confirm/unsubscribe, dispatch fan-out, RSS/Atom builders
apps/control-plane/src/platform/status_page/router.py                          # NEW (~180 LOC) — public + authenticated endpoints, gated by auth-middleware exempt list for the public ones
apps/control-plane/src/platform/status_page/events.py                          # NEW (~50 LOC) — internal event types for dispatch worker
apps/control-plane/src/platform/status_page/exceptions.py                      # NEW (~30 LOC) — SubscriptionNotFound, ConfirmationTokenInvalid, RateLimitExceeded
apps/control-plane/src/platform/status_page/dependencies.py                    # NEW (~40 LOC) — FastAPI dependencies (rate-limit, snapshot fetcher)
apps/control-plane/src/platform/status_page/projections.py                     # NEW (~120 LOC) — Kafka consumer for multi_region_ops.events + incident_response.events; APScheduler 60s health poller; APScheduler daily 30d-uptime rollup
apps/control-plane/src/platform/status_page/feed_builders.py                   # NEW (~80 LOC) — RSS/Atom assembly via feedgen
apps/control-plane/src/platform/common/auth_middleware.py                      # MODIFY — append public status paths to EXEMPT_PATHS (lines 13-32)
apps/control-plane/src/platform/main.py                                        # MODIFY — register status_page router (after incident_response_router at line 1650)
apps/control-plane/src/platform/notifications/webhooks_service.py              # MODIFY — extend OutboundWebhook subscriber registration to accept the status_page event_kinds (additive — preserves existing event types)
apps/control-plane/tests/unit/status_page/test_service.py                      # NEW (~250 LOC, ~30 cases)
apps/control-plane/tests/unit/status_page/test_feed_builders.py                # NEW (~80 LOC, ~6 cases)
apps/control-plane/tests/integration/status_page/test_public_endpoints.py     # NEW (~150 LOC, ~10 cases)
apps/control-plane/tests/integration/status_page/test_subscription_flow.py    # NEW (~180 LOC, ~10 cases — includes confirm/unsubscribe)

apps/web-status/                                                               # NEW — separate Next.js 14 static-export project (Rule 49)
apps/web-status/package.json                                                   # NEW — minimal deps: next, react, react-dom, tailwindcss, lucide-react, date-fns
apps/web-status/next.config.mjs                                                # NEW — output: 'export'
apps/web-status/app/page.tsx                                                   # NEW — overall status page (server-static + client-hydrated)
apps/web-status/app/components/[id]/page.tsx                                   # NEW — per-component history
apps/web-status/app/history/page.tsx                                           # NEW — 30d incident archive
apps/web-status/app/subscribe/page.tsx                                         # NEW — subscribe form (email + RSS/Atom URL display + webhook + Slack)
apps/web-status/app/subscribe/confirm/page.tsx                                 # NEW — opt-in confirmation
apps/web-status/app/unsubscribe/page.tsx                                       # NEW — unsubscribe via tokenized link
apps/web-status/components/StatusBanner.tsx                                    # NEW — overall-state banner
apps/web-status/components/ComponentRow.tsx                                    # NEW
apps/web-status/components/IncidentTimeline.tsx                                # NEW
apps/web-status/components/SubscribeForm.tsx                                   # NEW — RHF + Zod
apps/web-status/lib/status-client.ts                                           # NEW — fetch wrapper for /api/v1/public/status (with last-known-good fallback)
apps/web-status/public/last-known-good.json                                    # NEW — generated at build time, served when status API unreachable
apps/web-status/Dockerfile                                                     # NEW — multi-stage: build → nginx serve out/
deploy/helm/platform/templates/web-status-deployment.yaml                      # NEW — separate Deployment in platform-edge namespace
deploy/helm/platform/templates/web-status-ingress.yaml                         # NEW — separate Ingress for status.* hostname
deploy/helm/platform/values.yaml                                               # MODIFY — add webStatus: { enabled, image, host } block
deploy/helm/platform/templates/status-snapshot-cronjob.yaml                    # NEW — runs every 60s, hits internal cron endpoint to pre-cache last-known-good
deploy/helm/platform/templates/configmap-status-routes.yaml                    # NEW — declares public status route exemptions for the Ingress

# === Track B — In-shell banner + maintenance UX ===
apps/control-plane/src/platform/ws_hub/subscription.py                         # MODIFY — add ChannelType.PLATFORM_STATUS = "platform-status"; CHANNEL_TOPIC_MAP entry mapping to multi_region_ops.events + incident_response.events
apps/control-plane/src/platform/ws_hub/router.py                               # MODIFY — auto-subscribe authenticated connections to platform-status channel on connect (similar to ATTENTION/ALERTS)
apps/control-plane/src/platform/status_page/me_router.py                       # NEW — /api/v1/me/platform-status authenticated endpoint (user-specific affected-features context)
apps/web/types/websocket.ts                                                    # MODIFY — add "platform-status" to WsChannel union
apps/web/lib/api.ts                                                            # MODIFY — intercept 503 with maintenance envelope; throw MaintenanceBlockedError handled by global modal
apps/web/lib/hooks/use-platform-status.ts                                      # NEW — TanStack Query hook for /api/v1/me/platform-status with WS-driven invalidation
apps/web/components/features/platform-status/PlatformStatusBanner.tsx          # NEW — variant-aware banner; uses shadcn Alert primitive
apps/web/components/features/platform-status/MaintenanceBlockedActionModal.tsx # NEW — shadcn Dialog; cites window-end time
apps/web/components/features/platform-status/StatusIndicator.tsx               # NEW — reusable severity dot+icon+text (also re-exported to apps/web-status via shared UI package OR copied — see R12 decision)
apps/web/components/features/platform-status/MaintenanceModalProvider.tsx      # NEW — global modal subscriber to MaintenanceBlockedError events
apps/web/app/(main)/layout.tsx                                                 # MODIFY — inject <PlatformStatusBanner /> above <Header /> at line 51; mount <MaintenanceModalProvider />
apps/web/app/(main)/settings/status-subscriptions/page.tsx                     # NEW — authenticated subscription mgmt (Rule 45)
apps/web/components/features/platform-status/StatusSubscriptionList.tsx        # NEW
apps/web/components/features/platform-status/AddSubscriptionForm.tsx           # NEW — RHF + Zod
apps/web/__tests__/platform-status/                                            # NEW — Vitest + RTL specs
apps/web/messages/en.json                                                      # MODIFY — add platform-status namespace
apps/web/messages/es.json /de.json /fr.json /zh-CN.json                        # MODIFY — same keys; ja.json kept temporarily (see R3)

# === Track C — Simulation scenario editor + discovery workbench completion ===
apps/control-plane/src/platform/simulation/models.py                           # MODIFY — add NEW SimulationScenario model + scenario_id FK on SimulationRun (matching migration 095)
apps/control-plane/src/platform/simulation/schemas.py                          # MODIFY — add ScenarioCreate, ScenarioUpdate, ScenarioRead, ScenarioRunRequest
apps/control-plane/src/platform/simulation/scenarios_service.py                # NEW (~180 LOC) — CRUD + validation (no plaintext secrets, agents exist, workflow exists, twin fidelity bounds)
apps/control-plane/src/platform/simulation/router.py                           # MODIFY — add 5 new routes: GET/POST /scenarios, GET/PUT/DELETE /scenarios/{id}, POST /scenarios/{id}/run
apps/control-plane/tests/unit/simulation/test_scenarios_service.py             # NEW (~180 LOC, ~14 cases)
apps/control-plane/tests/integration/simulation/test_scenario_endpoints.py    # NEW (~120 LOC, ~8 cases)

apps/web/app/(main)/evaluation-testing/simulations/scenarios/page.tsx          # NEW — scenario library list
apps/web/app/(main)/evaluation-testing/simulations/scenarios/new/page.tsx      # NEW — scenario editor (create)
apps/web/app/(main)/evaluation-testing/simulations/scenarios/[id]/page.tsx     # NEW — scenario detail + edit + launch
apps/web/components/features/simulations/SimulationScenarioEditor.tsx          # NEW — full RHF+Zod editor; Monaco for inline JSON schema; mock-LLM preview default; <RealLLMOptInDialog> for real LLM
apps/web/components/features/simulations/ScenarioLibraryTable.tsx              # NEW — TanStack Table
apps/web/components/features/simulations/ScenarioRunDialog.tsx                 # NEW — N-iterations confirmation
apps/web/components/features/simulations/DigitalTwinPanel.tsx                  # NEW — mock/real lists, divergence highlights, time comparison, link to ref-prod-execution; "no reference available" empty state
apps/web/app/(main)/evaluation-testing/simulations/[runId]/page.tsx            # MODIFY — embed <DigitalTwinPanel runId={runId} />
apps/web/lib/hooks/use-simulation-scenarios.ts                                 # NEW — TanStack Query hooks
apps/web/lib/hooks/use-digital-twin.ts                                         # NEW — TanStack Query hooks for /twins + /comparisons

apps/web/app/(main)/discovery/[session_id]/page.tsx                            # NEW — session detail; shadcn Tabs (overview/hypotheses/experiments/evidence/network)
apps/web/app/(main)/discovery/[session_id]/hypotheses/page.tsx                 # NEW — library list
apps/web/app/(main)/discovery/[session_id]/experiments/page.tsx                # NEW — experiments list
apps/web/app/(main)/discovery/[session_id]/experiments/new/page.tsx            # NEW — experiment launcher form
apps/web/app/(main)/discovery/[session_id]/evidence/[evidence_id]/page.tsx     # NEW — evidence inspector
apps/web/components/features/discovery/HypothesisCard.tsx                      # NEW
apps/web/components/features/discovery/HypothesisFilterBar.tsx                 # NEW
apps/web/components/features/discovery/HypothesisDetailPanel.tsx               # NEW
apps/web/components/features/discovery/ExperimentLauncherForm.tsx              # NEW — RHF+Zod against the existing experiment endpoint contract
apps/web/components/features/discovery/EvidenceInspectorView.tsx               # NEW
apps/web/lib/hooks/use-discovery-session.ts                                    # NEW
apps/web/lib/hooks/use-discovery-evidence.ts                                   # NEW
# NOTE: existing apps/web/app/(main)/discovery/[session_id]/network/page.tsx and HypothesisNetworkGraph.tsx kept verbatim; reused as tab content via the new session-detail page

# === E2E coverage ===
tests/e2e/journeys/test_j21_platform_state.py                                  # NEW — full visibility-loop journey
tests/e2e/journeys/test_j07_evaluator.py                                       # NEW — simulation scenario authoring + digital twin journey (skeleton — first time landing in this repo)
tests/e2e/journeys/test_j09_scientific_discovery.py                            # NEW — discovery hypotheses + experiment + evidence journey
tests/e2e/suites/platform_state/test_public_status_page.py                     # NEW
tests/e2e/suites/platform_state/test_status_banner_rendering.py                # NEW
tests/e2e/suites/platform_state/test_maintenance_mode_ux.py                    # NEW
tests/e2e/suites/platform_state/test_email_subscription.py                     # NEW
tests/e2e/suites/platform_state/test_rss_feed.py                               # NEW
tests/e2e/suites/platform_state/test_webhook_subscription.py                   # NEW
tests/e2e/suites/simulation_ui/test_scenario_editor.py                         # NEW
tests/e2e/suites/simulation_ui/test_digital_twin_panel.py                      # NEW
tests/e2e/suites/discovery_ui/test_session_detail.py                           # NEW
tests/e2e/suites/discovery_ui/test_hypothesis_library.py                       # NEW
tests/e2e/suites/discovery_ui/test_experiment_launcher.py                      # NEW
tests/e2e/suites/discovery_ui/test_evidence_inspector.py                       # NEW
```

**Structure Decision**: Cross-stack feature spanning the Python control plane (NEW `status_page/` BC + `simulation/` extension), the existing Next.js app (in-shell banner, settings page, scenario + discovery pages), a NEW separate `apps/web-status/` Next.js static-export project, and a Helm overlay for the new Deployment + Ingress + CronJob. Discovery backend is unchanged; simulation backend gets one additive nullable column + one new table.

## Phase 0 (Research) → see `research.md`

Twelve research items resolve all open questions:

- **R1** — Auth-exempt list extension vs separate router-tree
- **R2** — RSS/Atom builder library choice
- **R3** — Locale list reconciliation (`apps/web/messages/ja.json` artifact vs FR-620's `it`)
- **R4** — Public status snapshot generation strategy (Kafka consumer + APScheduler poll + Redis hot cache)
- **R5** — Alembic migration slot allocation (verify 095 is free)
- **R6** — E2E directory bootstrap (`tests/e2e/journeys/` and `tests/e2e/suites/` first-touch)
- **R7** — Reuse `OutboundWebhook` table for status webhook subscriptions (vs new dedicated table)
- **R8** — Reuse `<RealLLMOptInDialog>` from UPD-044 for scenario preview opt-in
- **R9** — XYFlow + Dagre confirmation (no Cytoscape)
- **R10** — `status_page/` BC structure conformance to constitution
- **R11** — Static-site fallback strategy when `apps/web-status/` cannot reach the status API
- **R12** — Shared component package vs duplication for `<StatusIndicator>` across `apps/web/` and `apps/web-status/`

## Phase 1 (Design) → see `data-model.md`, `contracts/`, `quickstart.md`

Phase 1 deliverables produced alongside this plan:

- **`data-model.md`** — entity relationships for `PlatformStatusSnapshot`, `StatusSubscription`, `SubscriptionDispatch`, `SimulationScenario`, plus the additive `simulation_runs.scenario_id` FK and the conceptual `DigitalTwinDivergenceReport` (derived view, no new table — composed from the existing `simulation_comparison_reports`).
- **`contracts/`** — six contract files: public status API, public subscription API, authenticated subscription API, simulation scenarios API, platform-status WebSocket envelope, and feed format reference (RSS/Atom shape).
- **`quickstart.md`** — developer guide: how to run the in-cluster smoke test, how to trigger a synthetic incident for J21, how to test the static-site fallback.

## Complexity Tracking

> No declared variances. The single notable additive complexity (a separate Next.js static-export project at `apps/web-status/`) is mandated by Constitution Rule 49 (operational independence of the public status surface) and is therefore not a discretionary cost.

| Item | Why allowed | Simpler alternative rejected because |
|---|---|---|
| New `apps/web-status/` Next.js project | Rule 49 requires the public status surface to remain reachable when the main platform is down. Co-locating in `apps/web/` would tie its uptime to the main shell's bundle pipeline. | A single shared `apps/web/` route was rejected because (a) it shares the same build artefact and same Ingress as the authenticated app — single point of failure; (b) Next.js auth middleware would still execute on visitor requests adding an outage surface. |
| New `feedgen` dependency | RSS 2.0 + Atom 1.0 spec compliance and proper namespace handling are non-trivial; `feedgen` is pure-Python (~50KB), MIT-licensed, no transitive deps. | Hand-rolled XML rejected because validators (Feed Validator, FeedBurner) routinely reject hand-rolled feeds for namespace-qualified-element edge cases. |
| Additive `simulation_runs.scenario_id` FK | Lets us trace runs back to scenarios for the run-list-by-scenario UX in the editor. | A separate junction table rejected because the relationship is strictly 1-scenario-N-runs; junction adds query complexity for zero ownership benefit. |

---

**End of Plan.** Phase 2 is `/speckit-tasks` (NOT executed by this command). Proceed with `/speckit-clarify` if any open questions surfaced — none currently — or directly with `/speckit-tasks`.
