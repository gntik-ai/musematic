---
description: "Task list for UPD-047 — Plans, Subscriptions, and Quotas (Super-Admin Configurable)"
---

# Tasks: UPD-047 — Plans, Subscriptions, and Quotas (Super-Admin Configurable)

**Input**: Design documents in `specs/097-plans-subscriptions-quotas/`
**Prerequisites**: `plan.md` ✅, `spec.md` ✅, `research.md` ✅, `data-model.md` ✅, `contracts/` ✅, `quickstart.md` ✅
**Branch**: `097-plans-subscriptions-quotas`

**Tests**: Tests are included for this feature because (a) the spec lists 10 measurable success criteria covering financial correctness, idempotency under concurrent load, and cross-tier behaviour; (b) constitutional rule SaaS-23 ("synchronous quota check") and SaaS-26 ("active compute time as billing unit") demand automated verification of accounting integrity; (c) FR-040 explicitly requires three-layer enforcement of the subscription scope constraint with a CI integration test as one of the layers.

**Organization**: Tasks are grouped by user story (US1 through US6). User stories US1–US4 are P1 (gating); US5 and US6 are P2 (lifecycle transitions). Phase 1 (Setup) and Phase 2 (Foundational) MUST complete before any user-story phase can begin.

## Format: `[TaskID] [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Story label (US1–US6) — required for user-story phases; absent in Setup, Foundational, and Polish

## Path Conventions

- **Backend**: `apps/control-plane/src/platform/<bc>/...` for bounded contexts; `apps/control-plane/migrations/versions/...` for Alembic; `apps/control-plane/tests/{unit,integration,e2e}/...` for tests
- **Frontend**: `apps/web/app/...` for routes; `apps/web/components/...` for components; `apps/web/lib/hooks/...` for hooks
- **Helm/Ops**: `deploy/helm/...` for charts; `deploy/runbooks/...` for operator docs
- **CI**: `.github/workflows/...` and `apps/control-plane/scripts/lint/...` for static-analysis rules

## Dependency on UPD-046

UPD-046 (`tenants` table, RLS posture, hostname middleware, platform-staff role) MUST be live before any task in this list begins. Subscriptions and usage records are tenant-scoped from day one — every new table follows the UPD-046 conventions (`tenant_id NOT NULL`, RLS policy, `tenant_id` index).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Bring the repository into a state where the feature can begin: configuration plumbing, the new `billing/` BC directory skeleton, Helm value scaffolding, runtime profile gating.

- [X] T001 Confirm working branch is `097-plans-subscriptions-quotas` (`git status` shows clean tree, branch matches) and UPD-046 migrations 096–102 are present at `apps/control-plane/migrations/versions/`.
- [X] T002 [P] Add new Pydantic settings to `apps/control-plane/src/platform/common/config.py`: `BILLING_PERIOD_SCHEDULER_INTERVAL_SECONDS: int = 60`, `BILLING_METERING_TOLERANCE_SECONDS: int = 30`, `BILLING_PAYMENT_PROVIDER: Literal["stub", "stripe"] = "stub"`, `BILLING_QUOTA_CACHE_TTL_SECONDS: int = 60`, `BILLING_QUOTA_IN_FLIGHT_TTL_SECONDS: int = 300`, `BILLING_DEFAULT_QUOTA_PERIOD_ANCHOR: Literal["calendar_month", "subscription_anniversary"] = "calendar_month"`. Document each in the docstring with the constitutional rule reference.
- [X] T003 [P] Add the `billing:` Helm value block to `deploy/helm/platform/values.yaml` mirroring the new settings (periodSchedulerIntervalSeconds, meteringToleranceSeconds, paymentProvider, quotaCacheTtlSeconds, quotaInFlightTtlSeconds, defaultQuotaPeriodAnchor). Mirror to `deploy/helm/platform/values.dev.yaml` and `values.prod.yaml`.
- [X] T004 Create the `billing/` bounded-context directory skeleton: `apps/control-plane/src/platform/billing/__init__.py`, `billing/plans/__init__.py`, `billing/subscriptions/__init__.py`, `billing/quotas/__init__.py`, `billing/providers/__init__.py`. Each `__init__.py` is empty so subsequent tasks can target the modules.
- [X] T005 [P] Create `apps/control-plane/src/platform/billing/exceptions.py` with the BC-wide exception hierarchy: `BillingError(PlatformError)`, plus stable error codes for `PlanNotFoundError`, `PlanVersionImmutableError`, `PlanVersionInProgressError`, `SubscriptionScopeError`, `SubscriptionNotFoundError`, `NoActiveSubscriptionError`, `QuotaExceededError`, `OverageRequiredError`, `OverageCapExceededError`, `ModelTierNotAllowedError`, `PaymentProviderError`, `UpgradeFailedError`, `DowngradeAlreadyScheduledError`, `ConcurrentLifecycleActionError`.
- [X] T006 [P] Add the `billing` BC to the existing OpenAPI tag registry and runtime-profile router-registration table in `apps/control-plane/src/platform/main.py:create_app()` so the new admin/public/workspace routers register at startup. Routers themselves land later — this task is the placeholder import block.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migrations 103 + 104, plan/subscription BC core, PaymentProvider Protocol + StubPaymentProvider, period-rollover scheduler, audit-chain integration. **All user-story phases depend on this phase being complete.**

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Track A — Schema migrations

- [X] T007 Author Alembic migration `apps/control-plane/migrations/versions/103_billing_plans_subscriptions_usage_overage.py`. Sub-steps in a single revision (atomic): (a) create `plans` table with the schema in `data-model.md` (UNIQUE on slug; `tier` CHECK; `is_public` BOOLEAN); (b) create `plan_versions` with composite UNIQUE `(plan_id, version)` and the partial index `plan_versions_plan_published_idx`; (c) create the `plan_versions_immutable_after_publish` BEFORE-UPDATE trigger and `plan_versions_no_delete_published` BEFORE-DELETE trigger per `data-model.md`; (d) create `subscriptions` with `(scope_type, scope_id)` UNIQUE, the composite FK to `plan_versions`, and the four indexes; (e) create the `subscriptions_scope_check` trigger that refuses bad scope-vs-tenant-kind combinations; (f) ENABLE + FORCE RLS on `subscriptions`, `usage_records`, `overage_authorizations` with the standard `tenant_isolation` policy; (g) create `usage_records` with the UNIQUE aggregate index per `data-model.md`; (h) create `overage_authorizations` with `(workspace_id, billing_period_start)` UNIQUE; (i) create the `processed_event_ids` companion table for metering idempotency. Include reverse migration that drops everything in reverse order.
- [X] T008 Author Alembic migration `apps/control-plane/migrations/versions/104_cost_attributions_subscription_id.py`: `ALTER TABLE cost_attributions ADD COLUMN subscription_id UUID NULL REFERENCES subscriptions(id) ON DELETE SET NULL`; `CREATE INDEX cost_attributions_subscription_idx ON cost_attributions (subscription_id)`. Reverse migration drops the index and column.
- [X] T009 Add the seed step to migration 103 that inserts the three default plans (`free`, `pro`, `enterprise`) and their initial published version 1 with the parameter values pinned in `research.md` R1. Use `ON CONFLICT (slug) DO NOTHING` and `ON CONFLICT (plan_id, version) DO NOTHING` for idempotency.
- [X] T010 Add the backfill step to migration 103 that inserts a `Subscription` row for every existing default-tenant workspace, bound to `(plan=free, version=1)`, status `active`, current period anchored at the calendar month containing the migration. `ON CONFLICT (scope_type, scope_id) DO NOTHING` per research R9. Emit a structured log line with the count of inserted subscriptions at the end of the migration.

### Track A — Plans BC

- [X] T011 [P] Author the SQLAlchemy `Plan` and `PlanVersion` models at `apps/control-plane/src/platform/billing/plans/models.py` matching the schemas in `data-model.md`. Use the existing `Base`, `UUIDMixin`, `TimestampMixin` patterns.
- [X] T012 [P] Author Pydantic schemas at `apps/control-plane/src/platform/billing/plans/schemas.py`: `PlanCreate`, `PlanUpdate`, `PlanPublic`, `PlanAdminView`, `PlanVersionPublish`, `PlanVersionView`, `PlanVersionDiff`. Validation rules: every quota integer must be `>= 0`; `price_monthly` must be `>= 0`; `tier` is the literal union; `quota_period_anchor` is the literal union.
- [X] T013 Author `apps/control-plane/src/platform/billing/plans/repository.py` — `PlansRepository` class with async methods: `get_by_slug`, `list_all`, `list_public`, `create_plan`, `update_plan`, `get_published_version`, `list_versions`, `publish_new_version` (atomic — increments `version`, inserts `plan_versions` row with `published_at=now()`, sets `deprecated_at` on the prior published version), `deprecate_version`, `count_subscriptions_on_version`. The `publish_new_version` method acquires `pg_advisory_xact_lock(hash(plan_id))` per research R2.
- [X] T014 Author `apps/control-plane/src/platform/billing/plans/service.py` — `PlansService` with methods: `publish_new_version` (validates parameters; calls repository; emits audit-chain entry with diff via `AuditChainService.append`; publishes `billing.plan.published` Kafka event via outbox), `deprecate_version`, `update_plan_metadata`, `compute_diff_against_prior` (helper used in audit chain payload and admin UI). Service-layer guard refuses any UPDATE that would change a published version's parameters (FR-006).
- [X] T015 Author `apps/control-plane/src/platform/billing/plans/seeder.py` — `provision_default_plans_if_missing(session)` async function. Idempotent: checks for `free`, `pro`, `enterprise` slugs; if missing, inserts via the same SQL the migration uses (so dev databases without the migration applied still self-heal). Wired to `main.py` startup.
- [X] T016 Wire `provision_default_plans_if_missing` into the `create_app()` lifespan startup in `apps/control-plane/src/platform/main.py` (after the tenants seeder from UPD-046).

### Track A — Subscriptions BC

- [X] T017 [P] Author the SQLAlchemy `Subscription` model at `apps/control-plane/src/platform/billing/subscriptions/models.py` per `data-model.md`. Composite FK `(plan_id, plan_version) REFERENCES plan_versions(plan_id, version)`. Include the standard `WorkspaceScopedMixin`/`TenantScopedMixin` patterns.
- [X] T018 [P] Author Pydantic schemas at `apps/control-plane/src/platform/billing/subscriptions/schemas.py`: `SubscriptionView`, `SubscriptionAdminView`, `SubscriptionUpgrade`, `SubscriptionDowngrade`, `SubscriptionMigrate`, `SubscriptionUsageView`, `BillingSummary` per `contracts/workspace-billing-rest.md`.
- [X] T019 Author `apps/control-plane/src/platform/billing/subscriptions/repository.py` — `SubscriptionsRepository` with async methods: `get_by_id`, `get_by_scope` (returns one or none), `list_for_tenant`, `list_all` (cross-tenant — uses platform-staff session), `create`, `update_status`, `update_plan_pinning` (used by upgrade), `set_cancel_at_period_end`, `advance_period` (period-rollover atomic update with `FOR UPDATE SKIP LOCKED` per research R5), `count_by_plan_version`.
- [X] T020 [P] Author `apps/control-plane/src/platform/billing/subscriptions/resolver.py` — `SubscriptionResolver.resolve_active_subscription(workspace_id) -> Subscription`. Per FR-011: if the workspace's tenant is Enterprise, return the tenant-scoped subscription; otherwise return the workspace-scoped subscription. Raise `NoActiveSubscriptionError` if no row is found.
- [X] T021 [P] Author `apps/control-plane/src/platform/billing/subscriptions/events.py` with the canonical `EventEnvelope`-conforming dataclasses for the 14 event types in `contracts/billing-events-kafka.md`.
- [X] T022 Author `apps/control-plane/src/platform/billing/subscriptions/service.py` — `SubscriptionService` with methods: `provision_for_default_workspace` (creates a Free subscription on workspace creation, called from the workspaces BC), `provision_for_enterprise_tenant` (creates a tenant-scoped subscription on Enterprise tenant creation, called from the tenants BC), `upgrade`, `downgrade_at_period_end`, `cancel_scheduled_downgrade`, `suspend`, `reactivate`, `cancel`, `migrate_version` (super-admin only). Each method emits the corresponding Kafka event via outbox and records an audit-chain entry tagged with `tenant_id`.
- [X] T023 Author `apps/control-plane/src/platform/billing/subscriptions/period_scheduler.py` — APScheduler job builder `build_period_rollover_scheduler(app)`. Clones the pattern from `apps/control-plane/src/platform/cost_governance/jobs/anomaly_job.py`: `AsyncIOScheduler.add_job(_run, "interval", seconds=BILLING_PERIOD_SCHEDULER_INTERVAL_SECONDS, id="billing.period_rollover", replace_existing=True)`. The `_run` function selects `subscriptions WHERE current_period_end <= now() AND status NOT IN ('canceled', 'suspended')` with `FOR UPDATE SKIP LOCKED`, advances each row, emits `billing.subscription.period_renewed` events, drives `cancel_at_period_end=true` rows to the downgrade-effective transition.
- [X] T024 Wire `build_period_rollover_scheduler` into the `scheduler` runtime profile in `apps/control-plane/src/platform/main.py:create_app()` next to the existing anomaly and forecast schedulers.

### Track A — Quotas BC core models

- [X] T025 [P] Author the SQLAlchemy `UsageRecord` and `OverageAuthorization` models at `apps/control-plane/src/platform/billing/quotas/models.py` per `data-model.md`. Include the `processed_event_ids` model.
- [X] T026 [P] Author Pydantic schemas at `apps/control-plane/src/platform/billing/quotas/schemas.py`: `UsageView`, `OverageAuthorizationCreate`, `OverageAuthorizationView`, `QuotaCheckResult` (used by the enforcer's return shape).

### Track A — Payment Provider Protocol

- [X] T027 [P] Author the `PaymentProvider` Protocol at `apps/control-plane/src/platform/billing/providers/protocol.py` per `contracts/payment-provider-protocol.md`. Mark with `@runtime_checkable`. Include the `ProviderSubscription`, `ProrationPreview`, `ProviderInvoice` dataclasses.
- [X] T028 [P] Author `apps/control-plane/src/platform/billing/providers/exceptions.py` with `PaymentProviderError` and subclasses (`PaymentMethodInvalid`, `ProviderUnavailable`, `IdempotencyConflict`).
- [X] T029 Author `apps/control-plane/src/platform/billing/providers/stub_provider.py` — `StubPaymentProvider` per the behavioural contract in `contracts/payment-provider-protocol.md` ("Implementations" section). All methods deterministic. `report_usage` records calls via injected logger. `preview_proration` returns `ProrationPreview(prorated_charge_eur=Decimal("0.00"), …)`.
- [X] T030 Wire payment-provider selection in `apps/control-plane/src/platform/main.py:create_app()`: instantiate `StubPaymentProvider` when `settings.billing_payment_provider == "stub"`. The Stripe branch raises `NotImplementedError("StripePaymentProvider lands in UPD-052")` for now.

### Track A — Cost-attribution coupling

- [X] T031 Update `apps/control-plane/src/platform/cost_governance/models.py:CostAttribution` — add `subscription_id: Mapped[UUID | None]` column declaration mirroring migration 104.
- [X] T032 Update `apps/control-plane/src/platform/cost_governance/services/attribution_service.py:_record_step_cost()` — call `subscription_resolver.resolve_active_subscription(workspace_id)` and pass the result as `subscription_id` to the new row. Catch `NoActiveSubscriptionError` and write `NULL` (legacy compatibility per FR-030).

### Foundational tests

- [X] T033 [P] Migration smoke test at `apps/control-plane/tests/integration/migrations/test_103_billing_schema.py`: load a small fixture, run migration 103, assert `plans`, `plan_versions`, `subscriptions`, `usage_records`, `overage_authorizations`, `processed_event_ids` all exist with expected columns; assert RLS active on the four tenant-scoped tables; assert default plans seeded; assert default-tenant workspace backfill produced one subscription per existing workspace.
- [X] T034 [P] Migration smoke test at `apps/control-plane/tests/integration/migrations/test_104_cost_attribution_subscription_link.py`: run migration 104, assert `cost_attributions.subscription_id` column exists with NULL constraint and the index.
- [ ] T035 [P] Unit test `apps/control-plane/tests/unit/billing/plans/test_publish_new_version.py`: publishing version N+1 increments correctly; deprecates prior version atomically; refuses to publish if any quota field is negative; emits audit-chain entry with the diff payload.
- [ ] T036 [P] Unit test `apps/control-plane/tests/unit/billing/plans/test_deprecation.py`: explicit deprecate-version call sets `deprecated_at` once and is idempotent on second call.
- [ ] T037 [P] Unit test `apps/control-plane/tests/unit/billing/plans/test_seeder.py`: idempotent — first call seeds three plans, second call is a no-op.
- [ ] T038 [P] Unit test `apps/control-plane/tests/unit/billing/subscriptions/test_resolver.py`: workspace in default tenant returns workspace-scoped subscription; workspace in Enterprise tenant returns tenant-scoped subscription; raises `NoActiveSubscriptionError` when none exists.
- [ ] T039 [P] Unit test `apps/control-plane/tests/unit/billing/subscriptions/test_state_machine.py`: every documented transition (per `data-model.md`) succeeds; every undocumented transition raises a typed exception; `kind='default'` tenant rejected for tenant-scoped subscription; `kind='enterprise'` tenant rejected for workspace-scoped subscription (validated at service layer).
- [ ] T040 [P] Unit test `apps/control-plane/tests/unit/billing/subscriptions/test_period_rollover.py`: scheduler advances `current_period_*` exactly once per period boundary; idempotent on second invocation; `cancel_at_period_end=true` row transitions to `canceled` and emits `billing.subscription.downgrade_effective`.
- [X] T041 [P] Unit test `apps/control-plane/tests/unit/billing/providers/test_stub_provider.py`: `runtime_checkable` `isinstance(stub, PaymentProvider)` returns True; deterministic outputs; `create_customer` returns distinct IDs; `report_usage` is recorded.
- [ ] T042 [P] Integration test `apps/control-plane/tests/integration/billing/test_subscription_scope_constraint.py` (the three-layer constraint test required by FR-040): full cross-product `{default, enterprise} × {workspace, tenant}` → exactly 2 valid combinations and 2 invalid; both invalid combinations rejected at the application service layer AND at the database trigger.
- [ ] T043 [P] Integration test `apps/control-plane/tests/integration/billing/test_cost_attribution_subscription_link.py`: a new cost record written post-migration carries `subscription_id`; a legacy row with `subscription_id IS NULL` is tagged on first read by the attribution-read path.

**Checkpoint**: Foundation ready. The `billing/` BC core exists; the schema is migrated; default plans are seeded; existing default-tenant workspaces have Free subscriptions; the period-rollover scheduler is wired; the StubPaymentProvider satisfies the Protocol. User-story phases can now begin in parallel.

---

## Phase 3: User Story 1 — Super admin publishes a new Pro plan version (Priority: P1) 🎯 MVP

**Goal**: Super admin can publish a new plan version through `/admin/plans/{slug}/edit`. New subscriptions land on the new version within 60 seconds; existing subscriptions stay pinned to their version with zero exceptions.

**Independent Test**: Per spec User Story 1 — change Pro `price_monthly` from 49 to 59, click "Publish new version". Verify version 2 row exists, version 1 has `deprecated_at` set, existing Pro subscriptions still reference version 1 (SQL count), audit chain entry recorded with the diff.

### Tests for User Story 1

- [ ] T044 [P] [US1] Integration test `apps/control-plane/tests/integration/billing/test_admin_plan_publish.py`: super admin POSTs to `/api/v1/admin/plans/pro/versions` with new parameters; response 201; new `plan_versions` row exists with sequential version; prior version's `deprecated_at` is set; `billing.plan.published` Kafka event published with diff payload; audit chain entry recorded.
- [ ] T045 [P] [US1] Integration test `apps/control-plane/tests/integration/billing/test_admin_plan_immutability.py`: attempt to UPDATE a published `plan_versions` row directly via SQL — DB trigger refuses; attempt to publish via service layer with stale parameters — service-layer guard refuses; admin endpoint returns `409 plan_version_immutable`.
- [ ] T046 [P] [US1] Integration test `apps/control-plane/tests/integration/billing/test_admin_plan_concurrent_publish.py`: two simultaneous publish requests for the same plan slug — exactly one succeeds, the other receives `409 plan_version_in_progress` (advisory lock contention).
- [ ] T047 [US1] E2E test `apps/control-plane/tests/e2e/suites/plans_subscriptions/test_plan_versioning.py` — Journey J30: super admin logs in, opens `/admin/plans/pro/edit`, changes `price_monthly` 49→59, clicks "Publish new version"; verifies version-history page shows the diff; verifies a fresh Pro signup lands on version 2; verifies an existing Pro subscriber stays on version 1.

### Implementation for User Story 1

- [ ] T048 [US1] Author `apps/control-plane/src/platform/billing/plans/admin_router.py` with the endpoints from `contracts/admin-plans-rest.md`: `GET /api/v1/admin/plans` (list), `POST /api/v1/admin/plans` (create), `GET /api/v1/admin/plans/{slug}` (detail), `GET /api/v1/admin/plans/{slug}/versions` (history with diffs), `POST /api/v1/admin/plans/{slug}/versions` (publish new version), `POST /api/v1/admin/plans/{slug}/versions/{version}/deprecate`, `PATCH /api/v1/admin/plans/{slug}` (metadata update). All gated by `require_superadmin`.
- [ ] T049 [US1] Author `apps/control-plane/src/platform/billing/plans/public_router.py` with `GET /api/v1/public/plans` per `contracts/public-plans-rest.md`. No authentication. `Cache-Control: public, max-age=60`.
- [ ] T050 [US1] Wire the audit-chain integration in `PlansService.publish_new_version`: call `AuditChainService.append(audit_event_source="billing.plans", event_type="billing.plan.published", actor_role="super_admin", canonical_payload={diff: ..., new_version: ..., plan_slug: ...})`.
- [ ] T051 [US1] Wire the Kafka outbox publication of `billing.plan.published` event with the canonical envelope including `tenant_id` (set to the default tenant since plans are platform-scoped).
- [ ] T052 [US1] [P] Frontend hook `apps/web/lib/hooks/use-admin-plans.ts` — TanStack Query hooks: `useAdminPlans` (list), `useAdminPlan(slug)` (detail), `useAdminPlanVersions(slug)` (history), `usePublishPlanVersion`, `useDeprecatePlanVersion`, `useUpdatePlanMetadata`.
- [ ] T053 [US1] [P] Frontend component `apps/web/components/features/admin/PlanList.tsx` — TanStack Table reading `useAdminPlans`. Columns: slug, tier badge, current published version, active subscription count, public/active toggles. Row link to detail.
- [ ] T054 [US1] [P] Frontend component `apps/web/components/features/admin/PlanEditForm.tsx` — React Hook Form + Zod for the full parameter set. Pre-populated with the current published version values. Submit button is "Publish new version"; secondary button is "Cancel". Diff preview opens in a modal before final submission.
- [ ] T055 [US1] [P] Frontend component `apps/web/components/features/admin/PlanVersionDiff.tsx` — renders the diff between two versions as a side-by-side parameter table with cell highlighting for changed fields.
- [ ] T056 [US1] [P] Frontend component `apps/web/components/features/admin/PlanVersionHistory.tsx` — vertical timeline of every published version, each row showing the version number, publication timestamp, deprecation timestamp (if any), subscription-count, and a "Show diff against prior" expander.
- [ ] T057 [US1] Frontend page `apps/web/app/(admin)/admin/plans/page.tsx` — replaces the placeholder with `<PlanList />`. Top-right "Create new plan" button (rare path; opens a modal with `PlanEditForm` in create mode).
- [ ] T058 [US1] Frontend page `apps/web/app/(admin)/admin/plans/[slug]/edit/page.tsx` — server-component fetch of the current plan + published version; renders `<PlanEditForm />`. On successful publish, redirects to the history page.
- [ ] T059 [US1] Frontend page `apps/web/app/(admin)/admin/plans/[slug]/history/page.tsx` — renders `<PlanVersionHistory />`. Includes a "Compare versions" UI for arbitrary pairs.

**Checkpoint**: User Story 1 fully functional and testable independently. Super admin can publish new plan versions; existing subscriptions stay pinned; new subscriptions land on the new version.

---

## Phase 4: User Story 2 — Free workspace hits the hard cap (Priority: P1)

**Goal**: A Free workspace at any quota cap (executions/day, executions/month, minutes/day, minutes/month, max workspaces, max agents, max users, premium model tier) is refused synchronously with HTTP 402 and the structured body. No partial state is created.

**Independent Test**: Per spec User Story 2 — pre-fill counter to cap, attempt next chargeable action, verify 402 + body shape, verify no execution row, verify counter resets at period boundary.

### Tests for User Story 2

- [ ] T060 [P] [US2] Integration test `apps/control-plane/tests/integration/billing/test_quota_check_execution.py`: pre-fill `usage_records` to the Free monthly executions cap; attempt `POST /api/v1/executions` from a Free-workspace user; expect HTTP 402 with the FR-017 body shape; assert no `executions` row was created and no `execution.created` Kafka event was emitted.
- [ ] T061 [P] [US2] Integration test `apps/control-plane/tests/integration/billing/test_quota_check_workspace_create.py`: pre-create the Free max_workspaces; attempt `POST /api/v1/workspaces`; expect 402 with `quota_name=max_workspaces`.
- [ ] T062 [P] [US2] Integration test `apps/control-plane/tests/integration/billing/test_quota_check_agent_register.py`: pre-create the Free max_agents_per_workspace; attempt to lifecycle-transition a new agent to active; expect 402 with `quota_name=max_agents_per_workspace`.
- [ ] T063 [P] [US2] Integration test `apps/control-plane/tests/integration/billing/test_quota_check_user_invite.py`: pre-create the Free max_users_per_workspace; attempt to accept an invitation as a new user; expect 402 with `quota_name=max_users_per_workspace`.
- [ ] T064 [P] [US2] Integration test `apps/control-plane/tests/integration/billing/test_allowed_model_tier_enforcement.py`: Free workspace attempts execution with a `model_id` from the `standard` tier in the model catalogue; expect 402 with `code=model_tier_not_allowed`.
- [ ] T065 [P] [US2] Integration test `apps/control-plane/tests/integration/billing/test_quota_check_period_reset.py`: at the period boundary, force the period-rollover scheduler to run; assert monthly counter resets to zero; the previously-blocked Free workspace's next request succeeds.
- [ ] T066 [US2] E2E test `apps/control-plane/tests/e2e/suites/plans_subscriptions/test_free_hard_cap.py` — Journey J37: Free user creates workspace, runs 100 executions, the 101st returns 402 with the structured body, the UI surfaces an "Upgrade to Pro" CTA linking to `/workspaces/{id}/billing/upgrade`.
- [ ] T067 [US2] Stress test `apps/control-plane/tests/integration/billing/test_quota_check_stress.py`: 1000 concurrent overrun attempts on a Free workspace at cap; assert 100% return 402; assert zero execution rows created (SC-002).

### Implementation for User Story 2

- [ ] T068 [US2] Author `apps/control-plane/src/platform/billing/quotas/usage_repository.py` — `UsageRepository` class with idempotent `increment(subscription_id, period_start, metric, quantity, is_overage)` using `INSERT … ON CONFLICT (tenant_id, workspace_id, subscription_id, metric, period_start, is_overage) DO UPDATE SET quantity = usage_records.quantity + EXCLUDED.quantity`. Returns the post-increment quantity. Read methods: `get_current_usage(subscription_id, period_start)`, `get_period_history(subscription_id, limit)`.
- [ ] T069 [US2] Author `apps/control-plane/src/platform/billing/quotas/enforcer.py` — `QuotaEnforcer` class. Public methods: `check_execution(workspace_id, projected_minutes=1.0) -> QuotaCheckResult`, `check_workspace_create(user_id) -> QuotaCheckResult`, `check_agent_publish(workspace_id) -> QuotaCheckResult`, `check_user_invite(workspace_id) -> QuotaCheckResult`, `check_model_tier(workspace_id, model_id) -> QuotaCheckResult`. Each method: (1) resolves the active subscription via `SubscriptionResolver`; (2) reads the pinned plan version; (3) for Enterprise (all-zero caps) short-circuits with `OK`; (4) reads current usage from cache → DB; (5) compares projected usage against caps; (6) returns `OK | HARD_CAP_EXCEEDED | OVERAGE_REQUIRED | OVERAGE_AUTHORIZED | OVERAGE_CAP_EXCEEDED | MODEL_TIER_NOT_ALLOWED | NO_ACTIVE_SUBSCRIPTION | SUSPENDED`.
- [ ] T070 [US2] Implement the two-tier cache for the enforcer per research R3: process-local `cachetools.TTLCache(maxsize=4096, ttl=BILLING_QUOTA_CACHE_TTL_SECONDS)` for `(workspace_id, period_start)`; Redis keys `quota:plan_version:{workspace_id}` and `quota:usage:{subscription_id}:{period_start}`; Redis pub/sub channel `billing:quota:invalidate` published by `UsageRepository.increment` and consumed by every instance to evict their local entries.
- [ ] T071 [US2] Map `QuotaCheckResult` to HTTP responses in a shared helper `apps/control-plane/src/platform/billing/quotas/http.py:quota_result_to_http()` per research R8: `HARD_CAP_EXCEEDED → 402`; `OVERAGE_REQUIRED → 202` with paused-state body; `OVERAGE_CAP_EXCEEDED → 402`; `MODEL_TIER_NOT_ALLOWED → 402`; `NO_ACTIVE_SUBSCRIPTION → 403`; `SUSPENDED → 403`. Body shape matches `contracts/workspace-billing-rest.md` quota-rejection response.
- [ ] T072 [US2] Inject the quota check at `apps/control-plane/src/platform/execution/service.py:ExecutionService.create_execution()` line 127 — call `quota_enforcer.check_execution(workspace_id, projected_minutes=...)` BEFORE the repository write. On `HARD_CAP_EXCEEDED`, raise `QuotaExceededError` so the router returns 402. On `OVERAGE_REQUIRED`, create the `Execution` row with status `paused_quota_exceeded` (US3 territory but the row creation needs the right initial status).
- [ ] T073 [US2] Inject the quota check at `apps/control-plane/src/platform/workspaces/service.py:WorkspacesService.create_workspace()` line 112 — call `quota_enforcer.check_workspace_create(user_id)` BEFORE the repository write.
- [ ] T074 [US2] Inject the quota check at `apps/control-plane/src/platform/registry/service.py:RegistryService.lifecycle_transition()` (the publish path) — call `quota_enforcer.check_agent_publish(workspace_id)` BEFORE flipping `lifecycle_status` to `active`.
- [ ] T075 [US2] Inject the quota check at `apps/control-plane/src/platform/accounts/service.py:AccountsService.accept_invitation()` line 417 — call `quota_enforcer.check_user_invite(workspace_id)` BEFORE consuming the invitation.
- [ ] T076 [US2] Inject the model-tier check in `apps/control-plane/src/platform/common/clients/model_router.py:ModelRouter.route()` — call `quota_enforcer.check_model_tier(workspace_id, model_id)` BEFORE returning the resolved model. On failure raise `ModelTierNotAllowedError`.
- [ ] T077 [US2] Update the FastAPI exception handlers in `apps/control-plane/src/platform/main.py` to map `QuotaExceededError`, `ModelTierNotAllowedError`, `OverageCapExceededError` to HTTP 402 with the canonical body; `NoActiveSubscriptionError` and `SubscriptionSuspendedError` to 403; `OverageRequiredError` to 202 with the paused-state body.
- [ ] T078 [US2] [P] Frontend: update `apps/web/lib/api.ts` (the existing fetch wrapper) to recognise HTTP 402 with `code=quota_exceeded | overage_cap_exceeded | model_tier_not_allowed` and surface the structured body to the React Query layer as a typed `QuotaError`.
- [ ] T079 [US2] [P] Frontend component `apps/web/components/features/billing/QuotaExceededDialog.tsx` — a shadcn/ui Dialog rendered when a `QuotaError` is caught. Shows the failing quota name, current vs limit, reset-at countdown, and an "Upgrade to Pro" CTA linking to `/workspaces/{id}/billing/upgrade`.

**Checkpoint**: User Story 2 fully validated. Free hard cap returns 402 across all four chargeable actions and the model-tier check; UI surfaces the upgrade CTA inline.

---

## Phase 5: User Story 3 — Pro workspace authorises overage (Priority: P1)

**Goal**: Pro workspace at quota receives a paused execution + workspace-admin notification. After authorisation, paused work resumes and subsequent executions in the same period proceed without prompting.

**Independent Test**: Per spec User Story 3 — pre-fill minutes counter to 2400, trigger execution, verify paused state + notification, authorise via the workspace UI, verify execution resumes and subsequent executions don't re-prompt.

### Tests for User Story 3

- [ ] T080 [P] [US3] Integration test `apps/control-plane/tests/integration/billing/test_pro_overage_pause.py`: pre-fill minutes counter to Pro cap; trigger execution; assert response 202 with `status=paused_quota_exceeded`; assert `executions` row exists with status `paused_quota_exceeded`; assert workspace-admin-only notification recorded; assert non-admin members did NOT receive the notification.
- [ ] T081 [P] [US3] Integration test `apps/control-plane/tests/integration/billing/test_overage_authorize.py`: workspace admin POSTs to `/api/v1/workspaces/{id}/billing/overage-authorization` with `max_overage_eur=50`; assert `overage_authorizations` row created; assert previously-paused executions resume (status flips); assert subsequent execution within the period proceeds without prompting.
- [ ] T082 [P] [US3] Integration test `apps/control-plane/tests/integration/billing/test_overage_authorization_idempotent.py` — concurrent admins (SC-007 stress version): 1000 simultaneous-click trials; assert exactly one `overage_authorizations` row in 100% of cases; second admin sees no-op success.
- [ ] T083 [P] [US3] Integration test `apps/control-plane/tests/integration/billing/test_overage_period_expiry.py`: an overage authorisation in period N is no longer in scope in period N+1; the next overage in N+1 requires fresh authorisation.
- [ ] T084 [P] [US3] Integration test `apps/control-plane/tests/integration/billing/test_overage_cap_reached.py`: authorisation has `max_overage_eur=50`; usage reaches the cap; new executions are paused again and a fresh authorisation prompt is sent.
- [ ] T085 [US3] E2E test `apps/control-plane/tests/e2e/suites/plans_subscriptions/test_pro_overage_authorization.py`: full flow per spec acceptance scenarios 1–6.

### Implementation for User Story 3

- [ ] T086 [US3] Author `apps/control-plane/src/platform/billing/quotas/overage.py` — `OverageService` with methods: `authorize(workspace_id, billing_period_start, max_overage_eur, authorising_user_id)` (idempotent insert with `INSERT … ON CONFLICT (workspace_id, billing_period_start) DO NOTHING RETURNING id`; if conflict, return the existing row), `revoke(authorization_id, revoking_user_id)`, `is_authorized_for_period(workspace_id, billing_period_start) -> bool`, `current_overage_eur(subscription_id, billing_period_start) -> Decimal`. Each call to `authorize` and `revoke` resumes/pauses affected executions and emits the corresponding Kafka event + audit-chain entry.
- [ ] T087 [US3] Add `Execution.status='paused_quota_exceeded'` to the existing execution status enum in `apps/control-plane/src/platform/execution/models.py`. Add the corresponding Alembic migration as a sub-step of 103 (or as a follow-up additive migration if 103 is already locked).
- [ ] T088 [US3] Update `apps/control-plane/src/platform/execution/service.py:ExecutionService.create_execution()` — when `quota_enforcer.check_execution()` returns `OVERAGE_REQUIRED`, create the `Execution` row with status `paused_quota_exceeded` AND emit a `billing.overage.required` notification event before returning the 202 response.
- [ ] T089 [US3] Author the resume hook `ExecutionService.resume_paused_quota_exceeded(workspace_id, period_start)` — called by `OverageService.authorize`. Selects all paused executions for the period, transitions them to `pending` so the dispatcher picks them up, emits `execution.resumed` events.
- [ ] T090 [US3] Add the workspace-admin-only notification path: extend `apps/control-plane/src/platform/notifications/service.py:AlertService.create_admin_alert()` (already exists) is the right primitive; add a new `BillingOverageRequiredAlert` template at `apps/control-plane/src/platform/notifications/templates/billing.py` per `research.md` R11. The notification carries a deep-link to `/workspaces/{workspace_id}/billing/overage-authorize`.
- [ ] T091 [US3] Author the workspace billing router `apps/control-plane/src/platform/billing/subscriptions/router.py` per `contracts/workspace-billing-rest.md`: `GET /api/v1/workspaces/{id}/billing` (summary), `GET /api/v1/workspaces/{id}/billing/overage-authorization`, `POST /api/v1/workspaces/{id}/billing/overage-authorization` (workspace-admin only), `DELETE /api/v1/workspaces/{id}/billing/overage-authorization` (workspace-admin only), `GET /api/v1/workspaces/{id}/billing/usage-history`. Workspace-admin gating uses the existing `require_workspace_admin` dependency.
- [ ] T092 [US3] [P] Frontend hook `apps/web/lib/hooks/use-workspace-billing.ts`: `useWorkspaceBilling(id)` (summary), `useOverageAuthorization(id)` (current state), `useUsageHistory(id, periods)`.
- [ ] T093 [US3] [P] Frontend hook `apps/web/lib/hooks/use-overage-authorize.ts`: `useAuthorizeOverage`, `useRevokeOverage`. Mutations invalidate the billing summary query.
- [ ] T094 [US3] [P] Frontend component `apps/web/components/features/billing/QuotaProgressBars.tsx` — four progress bars (executions today/month, minutes today/month) computed from the billing summary. Shows "Approaching cap" amber state at >80%, "At cap" red state at 100%.
- [ ] T095 [US3] [P] Frontend component `apps/web/components/features/billing/BillingDashboardCard.tsx` — workspace billing card combining plan info, quota bars, forecast, payment-method status, and action buttons.
- [ ] T096 [US3] [P] Frontend component `apps/web/components/features/billing/OverageAuthorizationForm.tsx` — React Hook Form + Zod for the authorisation request. Shows current usage, configured overage rate, forecast of period-end overage at current burn rate, and a "Authorise overage" button with optional EUR cap input.
- [ ] T097 [US3] Frontend page `apps/web/app/(main)/workspaces/[id]/billing/page.tsx` — renders `<BillingDashboardCard />`. Surfaces the overage notification banner when the workspace is in paused state.
- [ ] T098 [US3] Frontend page `apps/web/app/(main)/workspaces/[id]/billing/overage-authorize/page.tsx` — renders `<OverageAuthorizationForm />`. Workspace-admin gating; non-admin members see a read-only view with "Ask your workspace admin" message.
- [ ] T099 [US3] Wire notification-center integration: when a `BillingOverageRequiredAlert` appears in the notification bell, render with elevated urgency and the deep-link button "Authorise now".

**Checkpoint**: User Story 3 fully validated. Pro overage flow works end-to-end with idempotent authorisations and proper workspace-admin scoping.

---

## Phase 6: User Story 4 — Enterprise workspace runs unlimited (Priority: P1)

**Goal**: Enterprise tenant subscriptions short-circuit every quota check; no 402; no overage prompt; the database trigger refuses any workspace-scoped subscription on Enterprise tenants.

**Independent Test**: Per spec User Story 4 — provision Enterprise tenant with all-zero plan version, run 10000 executions in a workspace, verify zero rejections, verify enforcer overhead < 1 ms p95.

### Tests for User Story 4

- [ ] T100 [P] [US4] Integration test `apps/control-plane/tests/integration/billing/test_enterprise_unlimited.py`: provision Enterprise tenant + tenant-scoped subscription with all-zero quotas; run 1000 executions in a workspace; assert all succeed; assert quota-enforcer never consulted the usage cache (asserted via mock counter).
- [ ] T101 [P] [US4] Integration test `apps/control-plane/tests/integration/billing/test_enterprise_zero_overhead.py` (SC-004 perf assertion): benchmark `quota_enforcer.check_execution()` against an Enterprise subscription vs a no-op baseline; assert added overhead < 1 ms p95 over 10000 calls.
- [ ] T102 [P] [US4] Integration test `apps/control-plane/tests/integration/billing/test_enterprise_inheritance.py`: Enterprise tenant has a single tenant-scoped subscription; multiple workspaces in the tenant; verify each workspace's resolved subscription is the tenant's subscription (FR-011).
- [ ] T103 [US4] E2E test `apps/control-plane/tests/e2e/suites/plans_subscriptions/test_enterprise_unlimited.py`: full kind-cluster flow per spec acceptance scenarios 1–4.

### Implementation for User Story 4

- [ ] T104 [US4] Verify the zero-cap short-circuit in `QuotaEnforcer` — already implemented in T069, but add an explicit fast-path test: if `plan_version.executions_per_day == 0 AND plan_version.executions_per_month == 0 AND plan_version.minutes_per_day == 0 AND plan_version.minutes_per_month == 0 AND plan_version.max_workspaces == 0 AND plan_version.max_agents_per_workspace == 0 AND plan_version.max_users_per_workspace == 0`, return `OK` without consulting the usage cache.
- [ ] T105 [US4] Hook the Enterprise-tenant provisioning path: when UPD-046's `TenantsService.provision_enterprise_tenant()` succeeds, call `SubscriptionService.provision_for_enterprise_tenant(tenant_id)` to create the tenant-scoped Enterprise subscription. Ensures every newly-provisioned Enterprise tenant has an active subscription on day one.
- [ ] T106 [US4] Hook the default-tenant workspace creation path: when `WorkspacesService.create_workspace()` succeeds for a default-tenant workspace, call `SubscriptionService.provision_for_default_workspace(workspace_id, plan_slug='free')` to create the Free subscription. Ensures every new default-tenant workspace has an active subscription on day one.

**Checkpoint**: User Story 4 fully validated. Enterprise unlimited works with zero measurable overhead.

---

## Phase 7: User Story 5 — Free workspace upgrades to Pro (Priority: P2)

**Goal**: Free→Pro upgrade UI shows prorated preview, captures payment method (stub for now), atomically updates the subscription row, immediately applies Pro quotas.

**Independent Test**: Per spec User Story 5 — Free workspace user clicks Upgrade, sees prorated preview, confirms with stub payment method, verifies Pro quotas apply on next chargeable action.

### Tests for User Story 5

- [ ] T107 [P] [US5] Integration test `apps/control-plane/tests/integration/billing/test_upgrade_free_to_pro.py`: Free workspace user calls `POST /api/v1/workspaces/{id}/billing/upgrade` with `target_plan_slug=pro` and `payment_method_token=stub_pm_test`; assert subscription row updates atomically (single transaction) to `(plan=pro, version=current_published)`; assert `current_period_end` is preserved or extended per the proration rule; assert audit-chain entry recorded.
- [ ] T108 [P] [US5] Integration test `apps/control-plane/tests/integration/billing/test_upgrade_quotas_immediate.py`: after upgrade, the next chargeable action is checked against Pro caps (not Free); the post-upgrade quota cache is invalidated.
- [ ] T109 [P] [US5] Integration test `apps/control-plane/tests/integration/billing/test_upgrade_payment_method_failure.py`: payment-method capture fails; assert subscription stays on Free; no partial-state row; no audit-chain entry for upgrade.
- [ ] T110 [US5] E2E test `apps/control-plane/tests/e2e/suites/plans_subscriptions/test_plan_upgrade_immediate.py`: full UI flow.

### Implementation for User Story 5

- [ ] T111 [US5] Author `SubscriptionService.upgrade(workspace_id, target_plan_slug, payment_method_token)` — atomic transaction: (1) resolve current subscription; (2) call `payment_provider.attach_payment_method` and then `payment_provider.update_subscription`; (3) update the local `subscriptions` row to the new plan + version + period boundaries returned by the provider; (4) emit `billing.subscription.upgraded` Kafka event; (5) invalidate the quota cache for the workspace; (6) record audit-chain entry. On any failure, rollback and surface `UpgradeFailedError`.
- [ ] T112 [US5] Wire the upgrade endpoint `POST /api/v1/workspaces/{id}/billing/upgrade` per `contracts/workspace-billing-rest.md`. Body validation: target plan must be public + active; current subscription's tier must be lower than target tier (no Pro→Free here — that's the downgrade endpoint).
- [ ] T113 [US5] Wire `payment_provider.preview_proration` into the upgrade endpoint so the response carries the prorated preview before/with the actual upgrade. The Stub returns deterministic zero-EUR proration; UPD-052 will return real Stripe proration.
- [ ] T114 [US5] [P] Frontend component `apps/web/components/features/billing/UpgradeForm.tsx` — RHF form. Step 1: select target plan (only "Pro" available from Free; only "Enterprise" from Pro — but Enterprise upgrade is super-admin-only, so it's a contact-sales CTA). Step 2: payment method capture (stub today; Stripe Elements lands in UPD-052). Step 3: prorated preview confirmation. Step 4: submit.
- [ ] T115 [US5] Frontend page `apps/web/app/(main)/workspaces/[id]/billing/upgrade/page.tsx` — renders `<UpgradeForm />`. Workspace-admin or owner gating.
- [ ] T116 [US5] [P] Frontend hook `apps/web/lib/hooks/use-plan-mutations.ts` extension: `useUpgradeSubscription`, `useDowngradeSubscription`, `useCancelDowngrade`, `useCancelSubscription`.

**Checkpoint**: User Story 5 fully validated. Free→Pro upgrade works end-to-end against the Stub provider.

---

## Phase 8: User Story 6 — Pro workspace schedules a downgrade (Priority: P2)

**Goal**: Pro→Free downgrade scheduled at period end. Cancel-downgrade reverses the schedule. At period boundary, the period-rollover scheduler applies the downgrade and surfaces the cleanup banner for data above Free quotas.

**Independent Test**: Per spec User Story 6 — schedule downgrade, verify status transition, verify cancel-downgrade reverts, verify period-boundary effective transition produces the cleanup banner.

### Tests for User Story 6

- [ ] T117 [P] [US6] Integration test `apps/control-plane/tests/integration/billing/test_downgrade_scheduled.py`: Pro workspace POSTs to `/api/v1/workspaces/{id}/billing/downgrade` with `target_plan_slug=free`; assert `status='cancellation_pending'` and `cancel_at_period_end=true`; assert `billing.subscription.downgrade_scheduled` Kafka event published.
- [ ] T118 [P] [US6] Integration test `apps/control-plane/tests/integration/billing/test_downgrade_cancelled.py`: scheduled-downgrade subscription POSTs to `/api/v1/workspaces/{id}/billing/cancel-downgrade`; assert status reverts to `active` and `cancel_at_period_end=false`; assert `billing.subscription.downgrade_cancelled` event.
- [ ] T119 [P] [US6] Integration test `apps/control-plane/tests/integration/billing/test_downgrade_effective.py`: scheduled-downgrade subscription with `current_period_end <= now()`; force the period-rollover scheduler; assert subscription transitions to `(plan=free, version=current_published)` with status `active`; assert `billing.subscription.downgrade_effective` event with the `data_exceeding_free_limits` payload.
- [ ] T120 [P] [US6] Integration test `apps/control-plane/tests/integration/billing/test_downgrade_data_cleanup_flag.py`: post-downgrade, the workspace has more agents than Free allows; verify the cleanup banner data is computed correctly; verify NO data is auto-deleted (FR-014 / spec User Story 6 acceptance scenario 2).
- [ ] T121 [US6] E2E test `apps/control-plane/tests/e2e/suites/plans_subscriptions/test_plan_downgrade_period_end.py`.

### Implementation for User Story 6

- [ ] T122 [US6] Author `SubscriptionService.downgrade_at_period_end(workspace_id, target_plan_slug)` — sets `cancel_at_period_end=true` and `status='cancellation_pending'`; calls `payment_provider.cancel_subscription(at_period_end=True)`; emits the Kafka event + audit-chain entry.
- [ ] T123 [US6] Author `SubscriptionService.cancel_scheduled_downgrade(workspace_id)` — reverts `status='active'` and `cancel_at_period_end=false`; calls `payment_provider.update_subscription(at_period_end=False)`; emits the Kafka event + audit-chain entry.
- [ ] T124 [US6] Extend `period_scheduler._run` (T023) to handle the downgrade-effective transition: when a subscription with `cancel_at_period_end=true` reaches its boundary, atomically (1) update the subscription to the lower-tier plan + current published version, (2) compute `data_exceeding_free_limits` (count workspaces > 1, count agents > 5 in this workspace, count users > 3 in this workspace), (3) emit `billing.subscription.downgrade_effective` event with the data-cleanup payload, (4) record audit-chain entry.
- [ ] T125 [US6] Wire the downgrade endpoint `POST /api/v1/workspaces/{id}/billing/downgrade` and `POST /api/v1/workspaces/{id}/billing/cancel-downgrade` per `contracts/workspace-billing-rest.md`.
- [ ] T126 [US6] [P] Frontend component `apps/web/components/features/billing/DowngradeForm.tsx` — confirmation modal explaining data implications (lists current usage that will exceed Free limits) + "Schedule downgrade" / "Cancel" buttons.
- [ ] T127 [US6] [P] Frontend component `apps/web/components/features/billing/BillingPeriodCountdown.tsx` — when `cancel_at_period_end=true`, renders a countdown timer to the period end with a "Cancel scheduled downgrade" button.
- [ ] T128 [US6] [P] Frontend component `apps/web/components/features/billing/PostDowngradeCleanupBanner.tsx` — rendered on the workspace shell whenever a downgrade has just become effective and the workspace has data exceeding Free limits. Lists affected entities with archive controls; nothing is auto-deleted.
- [ ] T129 [US6] Frontend page `apps/web/app/(main)/workspaces/[id]/billing/downgrade/page.tsx` — renders `<DowngradeForm />`. Workspace-admin or owner gating.

**Checkpoint**: User Story 6 fully validated. Pro→Free downgrade lifecycle works end-to-end including the post-downgrade data-cleanup flow.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Metering pipeline, reconciliation, admin subscriptions UI, observability dashboard, runbook, lint rules, localization.

### MeteringJob — Track B continuation

- [ ] T130 Author `apps/control-plane/src/platform/billing/quotas/metering.py` — `MeteringJob` Kafka consumer subscribed to `execution.compute.end`. For each event: (1) write to `processed_event_ids` (skip if already processed); (2) compute active-compute minutes from `end_ts - start_ts` (the event payload provides only the active processing window per AD-29); (3) call `UsageRepository.increment` for both `executions` (quantity 1) and `minutes` (decimal); (4) determine `is_overage` by comparing post-increment quantity against the pinned plan version's caps; (5) if overage, also call `payment_provider.report_usage(quantity=overage_minutes, idempotency_key=event_id)`. Wired into the worker runtime profile.
- [ ] T131 [P] Author the daily reconciliation job at `apps/control-plane/src/platform/billing/quotas/reconciliation.py` — APScheduler cron job at 02:00 UTC. Re-reads the prior 24 hours of `execution.compute.end` events from Kafka (or the audit-chain projection if Kafka retention is insufficient) and asserts every event has a `processed_event_ids` row; emits structured-log warnings on mismatches; fails loudly into the alerting pipeline if the mismatch rate exceeds 0.1%.
- [ ] T132 [P] Integration test `apps/control-plane/tests/integration/billing/test_metering_pipeline_end_to_end.py`: produce 100 `execution.compute.end` events with varying durations; assert `usage_records` reflects exact counts; assert `processed_event_ids` has 100 rows; replay the same 100 events; assert no double-count.
- [ ] T133 [P] Integration test `apps/control-plane/tests/integration/billing/test_metering_accuracy.py` (SC-006): hand-validated ground truth for 100 executions across durations 5 s to 5 min; assert per-execution error < ±2%; assert zero double-counting under deliberate replay.

### Admin subscriptions UI

- [ ] T134 [P] Author `apps/control-plane/src/platform/billing/subscriptions/admin_router.py` per `contracts/admin-subscriptions-rest.md`: list (cross-tenant, uses platform-staff session), detail, suspend, reactivate, migrate-version, usage. All gated by `require_superadmin`.
- [ ] T135 [P] Frontend hook `apps/web/lib/hooks/use-admin-subscriptions.ts` — TanStack Query: `useAdminSubscriptions` (list, filterable), `useAdminSubscription(id)` (detail), mutations for suspend/reactivate/migrate.
- [ ] T136 [P] Frontend component `apps/web/components/features/admin/SubscriptionList.tsx` — cross-tenant DataTable with columns tenant, plan, version, status, current period end, payment status, trial expiration. Filters in the toolbar.
- [ ] T137 [P] Frontend component `apps/web/components/features/admin/SubscriptionDetailPanel.tsx` — status timeline, usage progress bars, plan version pinning info, payment history (post-UPD-052), action buttons.
- [ ] T138 [P] Frontend component `apps/web/components/features/admin/SubscriptionStatusBadge.tsx` — colored badge per `Subscription.status`.
- [ ] T139 [P] Frontend page `apps/web/app/(admin)/admin/subscriptions/page.tsx` — replaces the placeholder with `<SubscriptionList />`.
- [ ] T140 [P] Frontend page `apps/web/app/(admin)/admin/subscriptions/[id]/page.tsx` — `<SubscriptionDetailPanel />` with cross-tenant data via the platform-staff endpoint.

### CI lint rules

- [ ] T141 [P] CI rule `apps/control-plane/scripts/lint/check_quota_enforcer_coverage.py`: AST-walk the production code; for every method that mutates a chargeable entity (`ExecutionService.create_execution`, `WorkspacesService.create_workspace`, `RegistryService.lifecycle_transition` publish path, `AccountsService.accept_invitation`, `ModelRouter.route`), assert that `quota_enforcer.check_*` is invoked before the mutation. Allow-list maintained for non-chargeable internal flows (e.g., system-initiated executions). Wire into `.github/workflows/ci.yml`.
- [ ] T142 [P] CI rule `apps/control-plane/scripts/lint/check_subscription_scope_constraint.py`: AST-walk for direct `subscriptions` table inserts/updates; assert that every site goes through `SubscriptionService` (which has the scope-vs-tenant-kind guard). Reinforces the FR-040 three-layer requirement.
- [ ] T143 [P] CI rule `apps/control-plane/scripts/lint/check_plan_version_immutable.py`: AST-walk for direct `plan_versions` UPDATE statements; assert that every site is whitelisted (only `PlansRepository.deprecate_version` and the publish path's `deprecated_at` flip).

### Observability and runbook

- [ ] T144 [P] Author Grafana dashboard ConfigMap `deploy/helm/observability/templates/dashboards/billing.yaml` (audit-pass rule 24). Panels: subscriptions by plan tier (count); plan-publish rate; quota-rejection rate by `quota_name`; overage-authorization rate; metering pipeline lag (max time from `execution.compute.end` to `usage_records` increment); period-rollover scheduler heartbeat; reconciliation-mismatch rate; PaymentProvider call-error rate.
- [ ] T145 [P] Add Prometheus metrics in the billing BC: counters `billing_quota_check_total{result, plan_tier}`, `billing_overage_authorize_total{outcome}`, `billing_plan_publish_total`, `billing_subscription_state_transition_total{from_status, to_status}`; histograms `billing_quota_check_seconds` (with `plan_tier` label), `billing_metering_lag_seconds`. Exported via existing OpenTelemetry pipeline.
- [ ] T146 [P] Author operator runbook `deploy/runbooks/plans-subscriptions-quotas.md`: plan publishing, plan deprecation, manual subscription edits via `/api/v1/admin/subscriptions/{id}/migrate-version`, period-rollover incident playbook (scheduler stuck, mass-overrun period boundaries), reconciliation-mismatch troubleshooting, overage-authorization revocation procedure.

### Localization

- [ ] T147 [P] Add localization strings for the billing UI in `apps/web/locales/{en,es,de,fr,it,zh}/billing.json` (per the FR-620 locale set in UPD-089 / audit-pass rule 38). Cover: quota-exceeded dialog, upgrade form, downgrade form, overage authorisation form, billing dashboard card, status badges, post-downgrade cleanup banner.

### Cost-attribution back-tag

- [ ] T148 Update the cost-attribution read path in `apps/control-plane/src/platform/cost_governance/services/attribution_service.py` (any `get_*` method that returns `CostAttribution` rows): on first read, if `subscription_id IS NULL`, call `subscription_resolver.resolve_active_subscription(workspace_id)` and UPDATE the row to set `subscription_id`. Idempotent. Fulfils FR-030 retroactive-tagging.
- [ ] T149 [P] Integration test `apps/control-plane/tests/integration/billing/test_legacy_cost_attribution_back_tag.py`: insert legacy rows (pre-migration shape) with `subscription_id IS NULL`; first read tags them retroactively; second read returns the same rows with `subscription_id` populated.

### CHANGELOG and root-level updates

- [ ] T150 [P] Update root `CHANGELOG.md` to mention UPD-047 — Plans, Subscriptions, and Quotas.
- [ ] T151 [P] Update `docs/system-architecture.md` and `docs/software-architecture.md` to describe the `billing/` BC, the PaymentProvider abstraction, and the quota-enforcement hot path.
- [ ] T152 Validate the quickstart walkthrough end-to-end on a fresh kind cluster against UPD-046's harness; capture any drift and update the doc.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Depends on UPD-046 being live. No other dependencies.
- **Phase 2 (Foundational)**: Depends on Setup. **BLOCKS all user stories**. Within Track A: migration 103 depends on 102 (UPD-046's last); migration 104 depends on 103 + UPD-027's existing `cost_attributions` table; the BC core (T011–T032) depends on the migration shape but the model files can be authored in parallel with the migration.
- **Phase 3 (US1 — plan publishing)**: Depends on Phase 2 (the `plans` table and the audit-chain integration).
- **Phase 4 (US2 — Free hard cap)**: Depends on Phase 2 (subscriptions, quotas, resolver). Most of the test surface is independent; the four enforcement-injection tasks (T072–T076) are mutually parallel.
- **Phase 5 (US3 — Pro overage)**: Depends on Phase 4 (the QuotaEnforcer's `OVERAGE_REQUIRED` path is implemented in Phase 4 but the resume-on-authorize path is implemented here).
- **Phase 6 (US4 — Enterprise unlimited)**: Depends on Phase 2; the Enterprise short-circuit is already in T069. Adds inheritance-resolution test and tenant-creation hook.
- **Phase 7 (US5 — upgrade)**: Depends on Phase 4 (subscriptions service must support state transitions).
- **Phase 8 (US6 — downgrade)**: Depends on Phase 7 (the upgrade path establishes the `payment_provider.update_subscription` contract).
- **Phase 9 (Polish)**: Depends on all user-story phases. The MeteringJob can begin alongside Phase 4 if metering events are emitted during testing; otherwise it lands here.

### User Story Dependencies

- **US1 (Plan publishing)**: Independent once Phase 2 lands. First user story to demonstrate value (the MVP).
- **US2 (Free hard cap)**: Independent once Phase 2 lands.
- **US3 (Pro overage)**: Soft dependency on US2 (the QuotaEnforcer's pause path is shared).
- **US4 (Enterprise unlimited)**: Independent once Phase 2 lands.
- **US5 (Upgrade)**: Independent once US2 lands (needs the QuotaEnforcer for post-upgrade cache invalidation).
- **US6 (Downgrade)**: Soft dependency on US5 (the `payment_provider.update_subscription` and `cancel_subscription` calls share a contract).

### Within Each User Story

- Tests written alongside or before implementation.
- Models and schemas before services; services before routers.
- Frontend hooks → frontend components → frontend pages.

---

## Parallel Execution Opportunities

- **Phase 1**: T002, T003, T005, T006 are mutually parallel.
- **Phase 2**: Track A migrations 103 + 104 are sequential. BC core models/schemas/exceptions/events/repositories (T011–T021, T025–T029) are mutually parallel (different files). Foundational tests (T033–T043) are mutually parallel. Migration 103 must finish before any BC test that needs the schema.
- **Phase 3 (US1)**: T044–T047 (tests), T052–T056 (frontend components/hooks) are mutually parallel after the service skeleton lands.
- **Phase 4 (US2)**: T060–T065 (tests) all parallel. T072–T076 (4 enforcer-injection points) all parallel after T071.
- **Phase 5 (US3)**: T080–T084 (tests), T092–T096 (frontend) all parallel.
- **Phase 7 (US5) + Phase 8 (US6)**: frontend components T114, T116, T126–T128 are mutually parallel.
- **Phase 9 (Polish)**: ~12 mutually parallel tasks across MeteringJob, admin UI, lint rules, dashboard, localization, doc updates.

### Parallel Example — Phase 4 enforcer injection

```bash
# Two engineers can divide the four entry points; the four files are independent.
Engineer A: T072 (execution) + T073 (workspace-create) + T078 (frontend api wrapper)
Engineer B: T074 (agent-publish) + T075 (user-invite) + T076 (model-tier) + T079 (frontend QuotaExceededDialog)
```

---

## Implementation Strategy

### MVP First — User Story 1 only

1. Complete Phase 1 (Setup) — half a day.
2. Complete Phase 2 (Foundational) — ~3 days. **CRITICAL** — blocks every user story.
3. Complete Phase 3 (User Story 1 — plan publishing) — ~1 day.
4. **STOP and VALIDATE**: super admin can publish plan versions on a kind cluster (the J30 journey). Demo to commercial stakeholders if ready.

### Incremental Delivery

1. Foundation ready (Phase 1 + Phase 2).
2. Add User Story 1 (plan publishing) → demo.
3. Add User Story 4 (Enterprise unlimited) → unblocks Enterprise tenant onboarding.
4. Add User Story 2 (Free hard cap) → activates economic protection (constitutional rule SaaS-13).
5. Add User Story 3 (Pro overage) → enables the Pro tier's value proposition.
6. Add User Story 5 (Upgrade) → enables conversion path Free→Pro.
7. Add User Story 6 (Downgrade) → enables exit path Pro→Free.
8. Polish (Phase 9) → MeteringJob + reconciliation + admin UI + dashboard + lint rules + localization + cost-attribution back-tag.

### Parallel Team Strategy (2–3 engineers)

- **Day 0**: All engineers on Phase 1 + Phase 2 Track A migrations (sequential coordination).
- **Days 1–3**: Engineer A finishes the Plans BC and US1; Engineer B finishes the Subscriptions BC + period-rollover scheduler; Engineer C starts the Quotas BC and US2.
- **Days 3–4**: Engineer A on US5 + US6 (upgrade/downgrade); Engineer B on US3 (Pro overage); Engineer C on US4 (Enterprise inheritance hook).
- **Day 5**: All three converge on Phase 9 polish and the E2E suite.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete prior tasks.
- [Story] label maps task to its user story for traceability and for rolling back a story-specific increment cleanly.
- Each user story is independently testable — the journey suite (J23, J30, J37) plus the per-story integration tests cover this.
- Verify tests fail before implementing the production code path.
- Commit after each task or logical group (the git pre-task auto-commit hook is configured).
- Stop at any user-story checkpoint to validate independently.
- The Stub PaymentProvider is the bridge to UPD-052 — every method must remain side-effect-free locally so E2E tests never depend on a real Stripe account.
