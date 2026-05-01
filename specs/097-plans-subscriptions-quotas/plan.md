# Implementation Plan: UPD-047 — Plans, Subscriptions, and Quotas (Super-Admin Configurable)

**Branch**: `097-plans-subscriptions-quotas` | **Date**: 2026-05-02 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/097-plans-subscriptions-quotas/spec.md`

## Summary

UPD-047 is the commercial-layer feature of the SaaS pass. It introduces three primitives — **Plan**, **Subscription**, **Quota** — and the synchronous enforcement, idempotent metering, and admin/workspace UIs that make them visible. The work splits into three parallel tracks (schema + bounded-context core, quota enforcement + metering, admin/workspace UIs) plus an E2E phase. Wave 22, directly after UPD-046 (`tenants` table and RLS posture must already be live so subscriptions are tenant-scoped from day one). Estimated 10 engineering days; ~5–6 wall-clock days with two or three engineers.

The feature establishes a `PaymentProvider` abstraction (constitutional principle SaaS-8 / AD-28) but does NOT yet wire Stripe — UPD-052 owns the Stripe concrete implementation. UPD-047 ships with a `StubPaymentProvider` that returns deterministic prorated previews and never actually charges, so the local SaaS surface is functional end-to-end before the merchant-of-record integration lands.

## Technical Context

**Language/Version**: Python 3.12+ (control plane), TypeScript 5.x strict (Next.js admin + workspace UIs).
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, asyncpg, redis-py 5.x async (resolver + usage cache), aiokafka 0.11+ (subscription events + metering consumer), APScheduler 3.x (period-rollover scheduler), TanStack Query v5 + React Hook Form + Zod (admin UI). All in existing `requirements.txt` / `apps/web/package.json` — **no new packages**.
**Storage**: PostgreSQL 16 — five new tables (`plans`, `plan_versions`, `subscriptions`, `usage_records`, `overage_authorizations`) plus an additive `subscription_id UUID NULL` column on the existing `cost_attributions` table (UPD-027). All tenant-scoped tables get the standard `tenant_id NOT NULL` column + RLS policy (per UPD-046 conventions). One new database trigger enforces the scope-vs-tenant-kind constraint. Redis — three new key families: `quota:plan_version:{workspace_id}` (resolved plan version cache, TTL 60s), `quota:usage:{subscription_id}:{period_start}` (rolling counter cache, TTL 60s, write-through invalidation on usage-record commit), `quota:in_flight:{workspace_id}` (counter for in-flight executions, TTL 5 minutes). Kafka — one new topic `billing.lifecycle` for subscription lifecycle events (additive); existing `execution.compute.end` consumed by the metering job. No MinIO/S3 paths owned by this feature.
**Testing**: pytest + pytest-asyncio 8.x (control plane unit + integration), pytest fixtures simulating quota-boundary workloads, Playwright (admin UI E2E), the existing `tests/e2e/` harness for the `plans_subscriptions` suite.
**Target Platform**: Linux containers on Kubernetes (the same Hetzner Cloud cluster topology established by UPD-046 / UPD-053).
**Project Type**: Web application — Python control plane (`apps/control-plane/`) + Next.js admin/user frontend (`apps/web/`).
**Performance Goals**: Quota-enforcement check p95 < 5 ms cache-resident, < 30 ms cache-miss (consults DB); metering-pipeline lag < 30 seconds p95 (the documented tolerance window); plan-version-history page load < 2 s (SC-005); Enterprise zero-cap path overhead < 1 ms p95 (SC-004).
**Constraints**: Quota enforcement MUST be synchronous and fail-closed (FR-024). Plan versions are immutable once published — only the `deprecated_at` flag flips (FR-006, constitutional rule SaaS-21). Subscription scope-vs-tenant-kind constraint enforced at three layers: service, DB trigger, CI test (FR-040). Metering MUST be idempotent on Kafka event ID (FR-026, constitutional Critical Reminder for Stripe webhook idempotency mirrored here). The PaymentProvider abstraction is opaque to business logic — bounded contexts call `payment_provider.charge()` etc., never Stripe APIs directly (constitutional rule SaaS-17 / AD-28).
**Scale/Scope**: Plans count is bounded (3 default seeded; super admin may add more — typical deployments stay under 10). Plan versions accumulate over time (typically <50 per plan over a year). Subscriptions count equals workspace count (default tenant) plus Enterprise tenant count — typically a few thousand. Usage records grow at ~one row per `(subscription, period, metric, is_overage)` so volumes are very modest.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The constitution at v2.0.0 governs this work. This plan complies with each applicable rule:

| Rule | Application in this plan |
|---|---|
| Brownfield-1 (never rewrite) | All work extends existing files (`cost_governance/services/attribution_service.py`, `execution/service.py`, `workspaces/service.py`, `accounts/service.py`, `registry/service.py`, `common/clients/model_router.py`). New `billing/` BC follows the standard layout. |
| Brownfield-2 (every change is an Alembic migration) | One main migration 103 plus an additive 104 for `cost_attributions.subscription_id`. No raw DDL. |
| Brownfield-3 (preserve existing tests) | Existing pytest + E2E suites continue to pass. New tests added under `tests/unit/billing/`, `tests/integration/billing/`, `tests/e2e/suites/plans_subscriptions/`. |
| Brownfield-7 (backward-compatible APIs) | All new tables, columns, JWT claims, and event types are additive. The `cost_attributions.subscription_id` column is `NULL` on legacy rows; the read path tags retroactively. |
| Brownfield-8 (feature flags) | No global feature flag is needed — the rollout is per-workspace at subscription-creation time (Free is the default; quota enforcement is always-on but Free quotas are the baseline). |
| SaaS-4 (plan tier determines features and quotas) | `Plan.tier` field; `PlanVersion` parameter set is the source of truth for quotas; `plan.allowed_model_tier` controls model routing. |
| SaaS-5 (quotas configurable by super admin) | All parameters live in `plan_versions`; admin UI at `/admin/plans/{slug}/edit` publishes new versions. No hardcoded quotas in code. |
| SaaS-6 / SaaS-25 (hard cap Free, opt-in Pro, no cap Enterprise) | `QuotaEnforcer` decision tree in `billing/quotas/enforcer.py`. Free → HTTP 402; Pro → pause + notify; Enterprise (zero quotas) → short-circuit OK. |
| SaaS-7 / SaaS-29 / SaaS-30 / AD-27 (subscription scope) | `subscriptions.scope_type` ∈ {`workspace`, `tenant`}; DB trigger refuses bad combinations. |
| SaaS-8 / SaaS-17 / AD-28 (PaymentProvider abstraction) | `apps/control-plane/src/platform/billing/providers/` directory; `PaymentProvider` Protocol; `StubPaymentProvider` shipped in this feature, `StripePaymentProvider` lands in UPD-052. |
| SaaS-13 (Free is economically protected) | `allowed_model_tier=cheap_only` enforced in `ModelRouter.route()`. |
| SaaS-16 / SaaS-21 / AD-26 (plan versioning) | Append-only `plan_versions` table; service-layer guard refuses in-place mutation; deprecation flag does not rewrite history. |
| SaaS-22 (plan version fixed for period) | Subscriptions reference `(plan_id, version)`; renewal stays on pinned version unless the user explicitly upgrades. |
| SaaS-23 (synchronous quota check) | `QuotaEnforcer.check_*()` methods are synchronous and fail-closed. |
| SaaS-24 (per-period overage authorization for Pro) | `OverageAuthorization` rows scoped to billing period; expire automatically at next period boundary. |
| SaaS-26 / AD-29 (active compute time as billing unit) | `MeteringJob` consumes `execution.compute.end` events; `minutes` quantity computed from `end_ts - start_ts` of the active processing window only (excludes approval gate waits, attention waits, sandbox provisioning, queue wait). |
| SaaS-27 (agent count = with at least one active revision) | Quota check on agent registration counts only revisions whose `lifecycle_status='active'`. |
| SaaS-28 (workspace count = not archived) | Quota check on workspace creation counts only workspaces whose `archived_at IS NULL`. |
| SaaS-41 (trial periods per plan) | `plan_versions.trial_days` field; subscription created in `trial` status when `trial_days > 0`. |
| SaaS-42 (card on file Free=no Pro=optional) | Free subscriptions never reference a `payment_method_id`; Pro stores one only if the user opts in (handled by UPD-052). |
| SaaS-43 (failed payments → grace → downgrade) | Subscription state machine includes `past_due` status; the period-rollover scheduler drives the transition. UPD-052 owns the Stripe-side retry policy. |
| Audit-pass rule 9 (every state change → audit chain) | `audit_chain_service.append()` invoked on every plan publish, every subscription transition, every overage authorization. `tenant_id` already in chain hash post-UPD-046. |
| Audit-pass rule 24 (every new BC gets a dashboard) | Track C adds `deploy/helm/observability/templates/dashboards/billing.yaml` (subscription tier breakdown, quota-rejection rate, overage-authorization rate, metering lag). |
| Audit-pass rule 25 (every new BC gets E2E + journey) | Phase 4 authors `tests/e2e/suites/plans_subscriptions/` and the J23 Quota Enforcement journey + J30 Plan Versioning journey + J37 Free Cost Protection journey. |

**Result**: PASS. No violations. The Complexity Tracking section is intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/097-plans-subscriptions-quotas/
├── plan.md              # This file (/speckit-plan output)
├── spec.md              # Feature spec
├── research.md          # Phase 0 — resolved unknowns + technical decisions
├── data-model.md        # Phase 1 — Plan, PlanVersion, Subscription, UsageRecord, OverageAuthorization
├── quickstart.md        # Phase 1 — local-dev validation walkthrough
├── contracts/           # Phase 1 — REST + Kafka + JWT contract specs
│   ├── admin-plans-rest.md
│   ├── admin-subscriptions-rest.md
│   ├── workspace-billing-rest.md
│   ├── public-plans-rest.md
│   ├── billing-events-kafka.md
│   └── payment-provider-protocol.md
├── checklists/
│   └── requirements.md  # Spec quality checklist (already present)
└── tasks.md             # Phase 2 — generated by /speckit-tasks (NOT created by this command)
```

### Source Code (repository root)

```text
apps/control-plane/
├── src/platform/
│   ├── billing/                                 # NEW bounded context
│   │   ├── __init__.py
│   │   ├── plans/
│   │   │   ├── models.py                        # Plan + PlanVersion SQLAlchemy
│   │   │   ├── schemas.py                       # Pydantic schemas
│   │   │   ├── service.py                       # PlanService.publish_new_version, deprecate_version
│   │   │   ├── repository.py
│   │   │   ├── admin_router.py                  # /api/v1/admin/plans/*
│   │   │   ├── public_router.py                 # /api/v1/public/plans
│   │   │   └── seeder.py                        # Free + Pro + Enterprise default plans (idempotent)
│   │   ├── subscriptions/
│   │   │   ├── models.py                        # Subscription SQLAlchemy
│   │   │   ├── schemas.py
│   │   │   ├── service.py                       # SubscriptionService — provision, upgrade, downgrade, suspend, reactivate, cancel; period rollover trigger
│   │   │   ├── repository.py
│   │   │   ├── router.py                        # /api/v1/workspaces/{id}/billing
│   │   │   ├── admin_router.py                  # /api/v1/admin/subscriptions/*
│   │   │   ├── resolver.py                      # resolve_active_subscription(workspace_id) — workspace-scoped or tenant-scoped per FR-011
│   │   │   ├── period_scheduler.py              # APScheduler period-rollover job
│   │   │   └── events.py                        # Kafka envelopes for billing.lifecycle
│   │   ├── quotas/
│   │   │   ├── enforcer.py                      # QuotaEnforcer (synchronous check)
│   │   │   ├── metering.py                      # MeteringJob (Kafka consumer)
│   │   │   ├── usage_repository.py              # UsageRecord CRUD with idempotent increment
│   │   │   ├── overage.py                       # OverageService — authorize, revoke
│   │   │   ├── models.py                        # UsageRecord + OverageAuthorization SQLAlchemy
│   │   │   └── exceptions.py                    # QuotaExceededError, OverageRequiredError, NoActiveSubscriptionError
│   │   ├── providers/                           # PaymentProvider abstraction (constitutional rule SaaS-8 / AD-28)
│   │   │   ├── __init__.py
│   │   │   ├── protocol.py                      # PaymentProvider Protocol
│   │   │   ├── stub_provider.py                 # StubPaymentProvider — deterministic prorated previews; no actual charge
│   │   │   └── (stripe_provider.py owned by UPD-052)
│   │   └── exceptions.py                        # PlanNotFoundError, PlanVersionImmutableError, SubscriptionScopeError, …
│   ├── execution/service.py                     # MODIFY: inject quota check at create_execution() line 127
│   ├── workspaces/service.py                    # MODIFY: inject quota check at create_workspace() line 112
│   ├── registry/service.py                      # MODIFY: inject agent-count quota check at lifecycle_transition() (publish path)
│   ├── accounts/service.py                      # MODIFY: inject user-count quota check at accept_invitation() line 417
│   ├── common/clients/model_router.py           # MODIFY: inject allowed_model_tier check in ModelRouter.route()
│   ├── cost_governance/services/attribution_service.py   # MODIFY: pass subscription_id to _record_step_cost()
│   └── cost_governance/models.py                # MODIFY: CostAttribution gains subscription_id additive column
└── migrations/versions/
    ├── 103_billing_plans_subscriptions_usage_overage.py  # NEW: full schema for the new BC
    └── 104_cost_attributions_subscription_id.py          # NEW: additive column on existing cost_attributions table
└── tests/
    ├── unit/billing/
    │   ├── plans/test_publish_new_version.py
    │   ├── plans/test_deprecation.py
    │   ├── plans/test_seeder.py
    │   ├── subscriptions/test_resolver.py
    │   ├── subscriptions/test_state_machine.py
    │   ├── subscriptions/test_period_rollover.py
    │   ├── quotas/test_enforcer_free_hard_cap.py
    │   ├── quotas/test_enforcer_pro_overage.py
    │   ├── quotas/test_enforcer_enterprise_unlimited.py
    │   ├── quotas/test_metering_idempotency.py
    │   ├── quotas/test_overage_authorization.py
    │   └── providers/test_stub_provider.py
    ├── integration/billing/
    │   ├── test_quota_check_execution.py
    │   ├── test_quota_check_agent_register.py
    │   ├── test_quota_check_workspace_create.py
    │   ├── test_quota_check_user_invite.py
    │   ├── test_allowed_model_tier_enforcement.py
    │   ├── test_subscription_scope_constraint.py        # 3 layers per FR-040
    │   ├── test_metering_pipeline_end_to_end.py
    │   ├── test_period_rollover.py
    │   └── test_cost_attribution_subscription_link.py
    └── e2e/suites/plans_subscriptions/
        ├── test_plan_versioning.py                       # Journey J30
        ├── test_free_hard_cap.py                         # Journey J37
        ├── test_pro_overage_authorization.py
        ├── test_enterprise_unlimited.py
        ├── test_plan_upgrade_immediate.py
        ├── test_plan_downgrade_period_end.py
        ├── test_quota_period_reset.py
        ├── test_subscription_scope_constraint.py
        └── test_quota_enforcement_journey.py             # Journey J23

apps/web/
├── app/
│   ├── (admin)/admin/
│   │   ├── plans/
│   │   │   ├── page.tsx                                  # Plan list
│   │   │   ├── [slug]/
│   │   │   │   ├── edit/page.tsx                         # Version-edit form
│   │   │   │   └── history/page.tsx                      # Version diff viewer
│   │   │   └── help.tsx
│   │   └── subscriptions/
│   │       ├── page.tsx                                  # Cross-tenant subscription list
│   │       ├── [id]/page.tsx                             # Per-subscription detail
│   │       └── help.tsx
│   └── (main)/workspaces/[id]/
│       └── billing/
│           ├── page.tsx                                  # Workspace billing dashboard
│           ├── overage-authorize/page.tsx                # Authorization form
│           ├── upgrade/page.tsx                          # Upgrade flow
│           └── downgrade/page.tsx                        # Downgrade scheduling
├── components/features/admin/
│   ├── PlanList.tsx
│   ├── PlanEditForm.tsx
│   ├── PlanVersionDiff.tsx
│   ├── PlanVersionHistory.tsx
│   ├── SubscriptionList.tsx
│   ├── SubscriptionDetailPanel.tsx
│   └── SubscriptionStatusBadge.tsx
├── components/features/billing/
│   ├── QuotaProgressBars.tsx
│   ├── BillingDashboardCard.tsx
│   ├── OverageAuthorizationForm.tsx
│   ├── UpgradeForm.tsx
│   ├── DowngradeForm.tsx
│   └── BillingPeriodCountdown.tsx
└── lib/hooks/
    ├── use-admin-plans.ts
    ├── use-admin-subscriptions.ts
    ├── use-workspace-billing.ts
    ├── use-overage-authorize.ts
    └── use-plan-mutations.ts                             # publish, deprecate, upgrade, downgrade, cancel

deploy/helm/
├── platform/values.yaml                                  # MODIFY: add `billing.*` block (period-scheduler interval, metering-tolerance window, paymentProvider key)
└── observability/templates/dashboards/
    └── billing.yaml                                      # NEW: Grafana dashboard ConfigMap (audit-pass rule 24)

deploy/runbooks/
└── plans-subscriptions-quotas.md                         # NEW: operator runbook (plan publishing, deprecation, manual subscription edits, period-rollover incidents)

.github/workflows/
└── ci.yml                                                # MODIFY: add `lint:quota-enforcer-coverage`, `lint:subscription-scope-constraint`, `lint:plan-version-immutable` jobs
```

**Structure Decision**: Web-application layout. New `billing/` bounded context follows the standard BC layout established in CLAUDE.md (`models.py`, `service.py`, `repository.py`, `router.py`, `admin_router.py`, `events.py`, `exceptions.py`). The BC is split into four sub-modules (`plans/`, `subscriptions/`, `quotas/`, `providers/`) because the surface is large and the four sub-areas have natural cohesion boundaries (plans = catalogue, subscriptions = lifecycle, quotas = enforcement and metering, providers = payment-provider abstraction). Migrations are sequential Alembic Python files (103 main schema + 104 additive cost-attribution column). RLS is automatically applied to every new tenant-scoped table per the UPD-046 conventions. Quota enforcement is a synchronous fail-closed check with a Redis-cache hot path and the database as authoritative on tie.

## Phased Execution Plan

This feature is medium-sized, so the speckit two-phase model (Phase 0 research, Phase 1 design) is supplemented with the user-provided four-track build plan. Phases 0 and 1 produce the artifacts under `specs/097-plans-subscriptions-quotas/`; the build phases (Track A through Track D) are scheduled in `tasks.md` by `/speckit-tasks`.

### Phase 0 — Outline & Research

Output: `research.md` resolves outstanding decisions:

- Plan-version locking strategy during concurrent subscription creation (advisory locks vs `SELECT … FOR SHARE` vs serializable isolation).
- Quota check caching strategy (Redis with write-through invalidation; database as authoritative).
- Period boundary semantics for executions that span the boundary.
- Period-rollover scheduler frequency and idempotency (every 60 seconds; idempotent on `(subscription_id, period_start)` advance).
- Metering pipeline idempotency on Kafka event ID and reconciliation cadence.
- Default plan parameter values (the seed values for free / pro / enterprise on first install).
- PaymentProvider Protocol shape — what methods does UPD-052's Stripe implementation need to fill?
- HTTP 402 vs 429 vs 403 return-code mapping for different quota failure modes.

### Phase 1 — Design & Contracts

Outputs:

- `data-model.md` — `Plan`, `PlanVersion`, `Subscription`, `UsageRecord`, `OverageAuthorization` schemas; the `cost_attributions.subscription_id` additive column; the database trigger for scope-vs-tenant-kind; the seed values for default plans; state machines for `Subscription.status`.
- `contracts/` — REST contracts for `/api/v1/admin/plans/*`, `/api/v1/admin/subscriptions/*`, `/api/v1/workspaces/{id}/billing`, `/api/v1/public/plans`. Kafka envelope for `billing.lifecycle` topic. PaymentProvider Protocol contract.
- `quickstart.md` — local-dev walkthrough (kind cluster) for: super admin publishes a new Pro version, Free workspace hits hard cap, Pro workspace authorizes overage, Enterprise unlimited, Free→Pro upgrade, Pro→Free downgrade.
- Update agent context file (`CLAUDE.md`) with a pointer to this plan between `<!-- SPECKIT START -->` and `<!-- SPECKIT END -->` markers.

### Phase 2 — Tasks

`/speckit-tasks` reads this plan and the artifacts under `specs/097-plans-subscriptions-quotas/` and produces `tasks.md` ordered by the build tracks below.

### Build Tracks (executed after `/speckit-tasks`)

- **Track A — Schema + plan/subscription bounded-context core** (3 days, 1 engineer). Migrations 103 + 104. `billing/plans/`, `billing/subscriptions/`, `billing/providers/` skeletons. Default-plan seeder (idempotent, called from `main.py` startup). `SubscriptionResolver` per FR-011. State machine. Period-rollover APScheduler job (clones the `cost_governance/jobs/anomaly_job.py` pattern). Kafka publisher for `billing.lifecycle` events.
- **Track B — Quota enforcement + metering** (3 days, 1 engineer). `QuotaEnforcer` decision tree. Redis-backed two-tier cache for plan version + usage counters. Synchronous injection at four entry points (execution, workspace, agent registration, user invitation). `allowed_model_tier` check in `ModelRouter.route()`. `MeteringJob` Kafka consumer with idempotent aggregation. `OverageService.authorize()` / `revoke()`. Reconciliation job (daily, compares `usage_records` against `execution.compute.end` event log). CI lint rules.
- **Track C — Admin and workspace UIs** (3 days, 1 engineer). `/admin/plans` list + edit + history. `/admin/subscriptions` list + detail. `/workspaces/{id}/billing` dashboard with quota gauges. `/workspaces/{id}/billing/overage-authorize` form. Notification center integration (workspace-admin-only for Pro overage prompt; all-members for Free hard cap). Localization for all new pages.
- **Phase 4 — E2E + observability** (1 day, 1 engineer). E2E suite under `tests/e2e/suites/plans_subscriptions/`. Journeys J23 (Quota Enforcement), J30 (Plan Versioning), J37 (Free Cost Protection). Grafana dashboard ConfigMap. Runbook.

## Risk Posture

Risks tracked in `spec.md` Background and `research.md`. Mitigations:

| Risk | Mitigation |
|---|---|
| Quota check overhead per execution | Two-tier cache (process LRU + Redis); usage records authoritative on tie; benchmark suite asserts p95 < 5 ms cache-resident; Enterprise zero-cap path short-circuits without consulting cache. |
| Metering accuracy under Kafka redelivery | Idempotent aggregation via `UNIQUE (subscription_id, period_start, metric, is_overage)`; daily reconciliation job rebuilds from the execution-event log; SC-006 asserts ±2% error and zero double-counting under deliberate replay. |
| Period boundary edge cases | Documented attribution rule: minutes attributed to the period in which `execution.compute.end` fires (single attribution, no double-count). Boundary test case in the E2E suite. |
| Plan-version schema evolution | `extras_json` column on `plan_versions` allows forward-compatible parameter additions without schema migration. |
| Concurrent overage authorizations | UNIQUE on `(workspace_id, billing_period_start)` with `INSERT … ON CONFLICT DO NOTHING`; second admin sees idempotent no-op. SC-007 stress test asserts 100% single-row outcome. |
| Plan version edit during active subscription creation | Subscription-creation transaction acquires `SELECT … FOR SHARE` on the target plan version; plan-publish acquires advisory lock that conflicts with the share lock. |
| Stripe webhook arriving before local subscription | Webhook handler (UPD-052) idempotent on Stripe event ID; if no local row exists, retry. UPD-047 ships the StubPaymentProvider so this risk only materializes when UPD-052 lands. |
| Subscription scope constraint missed by application code | Three-layer enforcement (FR-040): service-layer guard, DB trigger, CI integration test that runs the full cross-product of (tenant kind × scope type) — SC-010. |
| Default tenant has no Free subscription on existing workspaces post-migration | Migration 103 creates a `Subscription` row for every existing default-tenant workspace, bound to `(plan=free, version=1)` with the current month as the billing period. Idempotent on `(scope_type, scope_id)`. |

## Complexity Tracking

> No constitutional violations. The Complexity Tracking table is intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | — | — |
