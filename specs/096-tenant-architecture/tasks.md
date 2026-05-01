---
description: "Task list for UPD-046 — Tenant Architecture (Subdomain + RLS + Default-Plus-Enterprise)"
---

# Tasks: UPD-046 — Tenant Architecture (Subdomain + RLS + Default-Plus-Enterprise)

**Input**: Design documents in `specs/096-tenant-architecture/`
**Prerequisites**: `plan.md` ✅, `spec.md` ✅, `research.md` ✅, `data-model.md` ✅, `contracts/` ✅, `quickstart.md` ✅
**Branch**: `096-tenant-architecture`

**Tests**: Tests are included for this feature because (a) the spec lists 10 measurable success criteria covering security, isolation, and migration correctness; (b) the constitutional defense-in-depth posture (SaaS-11) requires automated verification; (c) cross-tenant isolation is the existential security failure mode and must be validated end-to-end.

**Organization**: Tasks are grouped by user story (US1 through US8). User stories US1–US5 are P1 (gating); US6–US8 are P2 (hardening + lifecycle). Phase 1 (Setup) and Phase 2 (Foundational) MUST complete before any user-story phase can begin.

## Format: `[TaskID] [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Story label (US1–US8) — required for user-story phases; absent in Setup, Foundational, and Polish

## Path Conventions

- **Backend**: `apps/control-plane/src/platform/<bc>/...` for bounded contexts; `apps/control-plane/migrations/versions/...` for Alembic; `apps/control-plane/tests/{unit,integration,e2e}/...` for tests
- **Frontend**: `apps/web/app/...` for routes; `apps/web/components/...` for components; `apps/web/lib/hooks/...` for hooks
- **Helm/Ops**: `deploy/helm/...` for charts; `deploy/runbooks/...` for operator docs; `apps/ops-cli/...` for CLI utilities
- **CI**: `.github/workflows/...` and `apps/control-plane/scripts/lint/...` for static-analysis rules

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Bring the repository into a state where the feature can begin: configuration plumbing, shared dataclasses, reserved-slug source of truth, and Helm value scaffolding.

- [X] T001 Confirm working branch is `096-tenant-architecture` (`git status` shows clean tree, branch matches)
- [X] T002 [P] Add new Pydantic settings to `apps/control-plane/src/platform/common/config.py`: `PLATFORM_DOMAIN: str` (default `"musematic.ai"`, override per environment), `PLATFORM_TENANT_ENFORCEMENT_LEVEL: Literal["lenient", "strict"]` (default `"lenient"`), `TENANT_RESOLVER_CACHE_TTL_SECONDS: int = 60`, `TENANT_DELETION_GRACE_HOURS: int = 72`, `TENANT_MIGRATION_ROLLBACK_WINDOW_HOURS: int = 24`. Document each in the docstring.
- [X] T003 [P] Create reserved-slug source of truth at `apps/control-plane/src/platform/tenants/reserved_slugs.py` exporting `RESERVED_SLUGS: frozenset[str] = frozenset({"api", "grafana", "status", "www", "admin", "platform", "webhooks", "public", "docs", "help"})`. Include a module docstring referencing constitution rule SaaS-9 and FR-003.
- [X] T004 [P] Create `apps/control-plane/src/platform/common/tenant_context.py` with the `TenantContext` frozen dataclass (per `contracts/tenant-resolution-context.md`), the `current_tenant: ContextVar[TenantContext | None]` declaration, and the `get_current_tenant()` / `set_current_tenant()` helpers; include `TenantContextNotSetError` exception.
- [X] T005 [P] Add the `tenancy:` Helm value block to `deploy/helm/platform/values.yaml` with the keys from `plan.md` (defaultTenantSlug, defaultTenantSubdomain, reservedSlugs list, cacheTtlSeconds, hostnameMiddlewareEnabled). Mirror to `deploy/helm/platform/values.dev.yaml` and `values.prod.yaml`.
- [X] T006 Create the placeholder `tenants/` bounded-context directory with empty `__init__.py` so subsequent tasks can target it: `apps/control-plane/src/platform/tenants/__init__.py`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema migrations, the tenants BC core, hostname middleware, and database role / session segregation. **All user-story phases depend on this phase being complete.**

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Track A — Schema migrations

- [X] T007 Author Alembic migration `apps/control-plane/migrations/versions/096_tenant_table_and_seed.py`: create `tenants` table per `data-model.md` (all columns, partial unique index `tenants_one_default`, indexes `tenants_kind_status_idx` and `tenants_scheduled_deletion_at_idx`); create `tenants_reserved_slug_check` trigger sourcing the slug list from `reserved_slugs.py`; create `tenants_default_immutable` trigger refusing delete/update of slug/subdomain/kind/status on the default row; seed the default tenant with hardcoded UUID `00000000-0000-0000-0000-000000000001`, slug `default`, subdomain `app`. Include reverse migration.
- [X] T008 Author Alembic migration `apps/control-plane/migrations/versions/097_tenant_id_columns_nullable.py`: add `tenant_id UUID NULL` column to every table catalogued in `data-model.md` (~41 tables across 35 BCs); create the checkpoint table `_alembic_tenant_backfill_checkpoint(table_name TEXT PRIMARY KEY, completed_phase TEXT NOT NULL, completed_at TIMESTAMPTZ NOT NULL DEFAULT now())`. Reverse migration drops the column from each table and the checkpoint table.
- [X] T009 Author Alembic migration `apps/control-plane/migrations/versions/098_tenant_id_backfill_default.py`: for each table in the catalogue, `UPDATE <table> SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL` and write the checkpoint row. Make the operation idempotent (skip if checkpoint row exists). For tables larger than 1M rows, use batched updates of 50000 rows. Reverse migration deletes the checkpoint rows (data is preserved).
- [X] T010 Author Alembic migration `apps/control-plane/migrations/versions/099_tenant_id_not_null_and_indexes.py`: for each catalogued table, `ALTER TABLE <table> ALTER COLUMN tenant_id SET NOT NULL` and `CREATE INDEX <table>_tenant_id_idx ON <table> (tenant_id)`. Reverse migration drops the index and removes the NOT NULL constraint.
- [X] T011 Author Alembic migration `apps/control-plane/migrations/versions/100_tenant_rls_policies.py`: for each catalogued table, `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and `CREATE POLICY tenant_isolation ON <table> USING (tenant_id = current_setting('app.tenant_id', true)::uuid)`. Reverse migration drops policy and disables RLS.
- [X] T012 Author Alembic migration `apps/control-plane/migrations/versions/101_platform_staff_role.py`: `CREATE ROLE musematic_platform_staff LOGIN BYPASSRLS`, set search_path, grant `USAGE` on schema and `SELECT, INSERT, UPDATE, DELETE` on all tables, set default privileges. Reverse migration drops the role.

### Track A — Tenants BC core skeleton

- [X] T013 [P] Author the SQLAlchemy `Tenant` model at `apps/control-plane/src/platform/tenants/models.py` matching the `tenants` table schema. Use the existing `Base`, `UUIDMixin`, `TimestampMixin` patterns from CLAUDE.md.
- [X] T014 [P] Author Pydantic schemas at `apps/control-plane/src/platform/tenants/schemas.py`: `TenantBranding`, `TenantCreate`, `TenantUpdate`, `TenantSuspend`, `TenantScheduleDeletion`, `TenantPublic`, `TenantAdminView`, `TenantPlatformView` per the contracts under `contracts/admin-tenants-rest.md` and `contracts/platform-tenants-rest.md`.
- [X] T015 [P] Author `apps/control-plane/src/platform/tenants/exceptions.py` with: `TenantNotFoundError`, `ReservedSlugError`, `SlugTakenError`, `SlugInvalidError`, `DefaultTenantImmutableError`, `TenantSuspendedError`, `TenantPendingDeletionError`, `DPAMissingError`, `RegionInvalidError`, `ConcurrentLifecycleActionError`, `DnsAutomationFailedError`. Each subclasses `PlatformError` and carries a stable error code.
- [X] T016 [P] Author `apps/control-plane/src/platform/tenants/events.py` with the canonical `EventEnvelope`-conforming dataclasses for the seven event types in `contracts/tenant-events-kafka.md` (`tenants.created`, `tenants.suspended`, `tenants.reactivated`, `tenants.scheduled_for_deletion`, `tenants.deletion_cancelled`, `tenants.deleted`, `tenants.branding_updated`).
- [X] T017 [P] Author `apps/control-plane/src/platform/tenants/vault_paths.py` with helpers `tenant_vault_path(env, tenant_slug, domain, resource) -> str`, `platform_vault_path(env, domain, resource) -> str`, and the legacy-compatible `legacy_vault_path(env, domain, resource) -> str`. All return validated paths.
- [X] T018 Author `apps/control-plane/src/platform/tenants/repository.py` — `TenantsRepository` class with async methods `get_by_id`, `get_by_slug`, `get_by_subdomain`, `list_all` (cross-tenant — uses platform-staff session), `create`, `update`, `delete`. Read methods use the regular session (default tenant lookup must work pre-resolution); cross-tenant write methods require platform-staff session (CI rule enforces).
- [X] T019 Author `apps/control-plane/src/platform/tenants/seeder.py` — `provision_default_tenant_if_missing(session)` async function: idempotent `INSERT INTO tenants … ON CONFLICT DO NOTHING` with the hardcoded UUID. Wired to be called from migration 096 AND from `main.py` startup so local-dev databases self-heal.
- [X] T020 Update `apps/control-plane/src/platform/main.py` startup hook: import and call `provision_default_tenant_if_missing` inside the lifespan startup block (after database engine init).

### Track B — Hostname middleware + DB session binding

- [X] T021 Author `apps/control-plane/src/platform/tenants/resolver.py` — `TenantResolver` with two-tier cache per research R5: process-local `cachetools.TTLCache` (max 1024, TTL = `TENANT_RESOLVER_CACHE_TTL_SECONDS`) and Redis key `tenants:resolve:{normalized_host}`. Method `resolve(host: str) -> TenantContext | None` normalizes host, checks tier 1, falls back to tier 2, falls back to DB query through the regular session. On miss, caches the negative result for half the TTL.
- [X] T022 Author `apps/control-plane/src/platform/common/middleware/tenant_resolver.py` — `TenantResolverMiddleware(BaseHTTPMiddleware)` per `contracts/tenant-resolution-context.md`. Extracts and normalizes `Host`, calls `TenantResolver.resolve()`, returns opaque 404 on miss, sets `current_tenant` ContextVar and `request.state.tenant`, handles `pending_deletion` opacity for non-platform-staff requests.
- [X] T023 Author `_build_opaque_404_response()` helper inside the middleware module: pre-built JSONResponse `{"detail":"Not Found"}`, fixed Content-Length, no Set-Cookie, no X-Request-ID echo. Add a `_apply_timing_floor()` async helper that yields `await asyncio.sleep(0)` plus optional jitter.
- [X] T024 Update `apps/control-plane/src/platform/main.py:create_app()` middleware registration: register `TenantResolverMiddleware` as the LAST `add_middleware` call (Starlette runs registered middleware in reverse, so last-added is first-executed). Verify the existing eight middleware are pushed back; the resolver becomes the outermost layer. Update the inline comment listing middleware order.
- [X] T025 Refactor `apps/control-plane/src/platform/common/database.py` to expose two engines: `regular_engine` (existing role `musematic_app`) and `platform_staff_engine` (new role `musematic_platform_staff`). Provide two async session factories and two FastAPI dependencies: `get_session()` (default) and `get_platform_staff_session()` (used only under `/api/v1/platform/*`).
- [X] T026 Add the SQLAlchemy `before_cursor_execute` event listener in `apps/control-plane/src/platform/common/database.py` on `regular_engine.sync_engine`: read `current_tenant.get(None)`, if set, execute `SET LOCAL app.tenant_id = '<uuid>'`. The platform-staff engine has no listener (BYPASSRLS bypasses any policy).
- [X] T027 [P] Author `apps/control-plane/src/platform/tenants/router.py` — `GET /api/v1/me/tenant` introspection endpoint that returns `request.state.tenant` as a `TenantPublic` schema. Read-only; no body. Used by frontend for SSR tenant context injection.

### Foundational tests

- [X] T028 [P] Author migration smoke test at `apps/control-plane/tests/integration/migrations/test_096_to_101.py`: load a small fixture, run migrations 096→101, assert tenants table populated, assert each catalogued table has the column / index / policy. Use the existing migration test harness.
- [X] T029 [P] Author `apps/control-plane/tests/unit/tenants/test_resolver.py` per `contracts/tenant-resolution-context.md` test contract: default-tenant lookup, enterprise-tenant lookup, unknown subdomain, case-insensitive, port strip, suspended-tenant resolves, pending-deletion-tenant 404s for non-staff.
- [X] T030 [P] Author `apps/control-plane/tests/unit/tenants/test_seeder.py` — idempotent calls; second call is a no-op; seeder runs without an existing transaction context.
- [X] T031 [P] Author `apps/control-plane/tests/unit/tenants/test_vault_paths.py` — assert path-builders produce the documented patterns; legacy helper continues to validate (dual-read window).
- [X] T032 Author `apps/control-plane/tests/integration/tenants/test_hostname_middleware.py` — full middleware integration: cache miss queries DB; cache hit skips DB (mock query counter); pub/sub invalidation rebuilds cache; latency p95 cache-resident under 5 ms (per SC-005); platform-staff request bypasses opacity for `pending_deletion`.
- [X] T033 Author `apps/control-plane/tests/integration/tenants/test_db_session_binding.py` — query against a tenant-scoped table without setting `app.tenant_id` returns zero rows; query with `app.tenant_id` set returns only that tenant's rows; platform-staff session returns all rows.

**Checkpoint**: Foundation ready. User story implementation can now begin. Migrations 096→101 applied; the default tenant is provisioned; the resolver middleware is wired; the regular and platform-staff engines are segregated.

---

## Phase 3: User Story 1 — Super admin provisions a new Enterprise tenant (Priority: P1) 🎯 MVP

**Goal**: Super admin can provision an Enterprise tenant from `/admin/tenants/new` and within five minutes the subdomain is reachable, branded, and the first-admin invitation has landed.

**Independent Test**: Per spec User Story 1 — submit `/admin/tenants/new` with valid inputs; navigate to `acme.musematic.ai`; receive invitation; complete first sign-in.

### Tests for User Story 1

- [X] T034 [P] [US1] Integration test `apps/control-plane/tests/integration/tenants/test_provision_enterprise.py`: end-to-end provisioning happy path; assert tenant row created with `active`, DPA hash recorded, audit chain entry, Kafka event published, DNS automation called, first-admin invite sent.
- [X] T035 [P] [US1] Integration test `apps/control-plane/tests/integration/tenants/test_provision_validation.py`: reserved slugs rejected by all three layers (Zod, service, trigger); duplicate slug returns 409; invalid region returns 422; missing DPA returns 422.
- [X] T036 [US1] E2E test `apps/control-plane/tests/e2e/suites/tenant_architecture/test_enterprise_tenant_provisioning.py` — Journey J22: super admin logs in, provisions Acme, the first-admin email is delivered (using the dev SMTP relay), the invite link lands at `acme.localtest.me/setup`, and the tenant admin completes first sign-in.

### Implementation for User Story 1

- [X] T037 [P] [US1] Author `apps/control-plane/src/platform/tenants/dns_automation.py` — `DnsAutomationClient` Protocol; `HetznerDnsAutomationClient` calling `POST https://dns.hetzner.com/api/v1/records` with `A` and `AAAA` records (returns within five-minute SLA or raises `DnsAutomationFailedError`); `MockDnsAutomationClient` returning success and emitting structured log. Choose implementation based on `PLATFORM_PROFILE` setting.
- [X] T038 [US1] Author `apps/control-plane/src/platform/tenants/service.py` — `TenantsService` with method `provision_enterprise_tenant(actor, request: TenantCreate) -> Tenant`. Sequence: validate slug (regex + reserved + uniqueness), insert tenant row, write audit-chain entry (post-commit outbox), publish Kafka `tenants.created`, call `dns_automation.ensure_records(slug)`, send first-admin invite via notifications BC. All within an outbox-pattern transaction so partial failure is recoverable.
- [X] T039 [US1] Add `apps/control-plane/src/platform/tenants/admin_router.py` with the endpoints from `contracts/admin-tenants-rest.md`: `GET /api/v1/admin/tenants` (list), `POST /api/v1/admin/tenants` (provision), `GET /api/v1/admin/tenants/{id}` (detail), `PATCH /api/v1/admin/tenants/{id}` (update), `POST /api/v1/admin/tenants/dpa-upload`. All gated by `require_superadmin` (audit-pass rule 30).
- [X] T040 [US1] Add the DPA-upload endpoint and S3 wiring: write the multipart file to bucket `tenant-dpas` at path `pending/{uuid}.pdf`, return `dpa_artifact_id`; on subsequent provisioning the artifact is moved to `{tenant_slug}/{dpa_version}-{timestamp}.pdf` and its SHA-256 is recorded on the tenant row.
- [X] T041 [US1] Wire audit-chain entry inclusion of `tenant_id` and the schema-version-boundary anchor: update `apps/control-plane/src/platform/audit/service.py:_canonical_hash()` to include `tenant_id` in the hashed canonical bytes; on the first new-format entry written post-migration, emit a `audit.schema.tenant_id_added` boundary entry whose `previous_hash` is the last v1 entry hash.
- [X] T042 [US1] [P] Add notifications BC integration: `apps/control-plane/src/platform/notifications/service.py` gains `send_first_admin_invitation(tenant, email)` constructing the invite URL `https://{subdomain}.{platform_domain}/setup?token=…`. The token is a single-use signed JWT bound to the tenant.
- [X] T043 [US1] Frontend: `apps/web/app/(admin)/admin/tenants/new/page.tsx` — provisioning form using React Hook Form + Zod. Field validation matches the server (regex slug, reserved-slug check, region enum, required DPA upload).
- [X] T044 [US1] [P] Frontend component: `apps/web/components/features/admin/TenantProvisionForm.tsx` — RHF form, file upload to `/api/v1/admin/tenants/dpa-upload`, then submit POST to `/api/v1/admin/tenants`. On success: toast + redirect to `/admin/tenants/{id}`.
- [X] T045 [US1] [P] Frontend hook: `apps/web/lib/hooks/use-admin-tenants.ts` — TanStack Query mutation hooks `useProvisionTenant`, `useDpaUpload`, `useUpdateTenant`. Query hooks `useAdminTenants` (list, paginated), `useAdminTenant(id)` (detail).
- [X] T046 [US1] Frontend: `apps/web/app/(admin)/admin/tenants/page.tsx` — replace the existing stub with a TanStack Table reading `useAdminTenants`. Columns: slug, kind, status, member_count, active_workspace_count, created_at. Row link to detail page. Top-right "Provision new tenant" button.
- [X] T047 [US1] Frontend: `apps/web/app/(admin)/admin/tenants/[id]/page.tsx` — replace stub with `TenantDetailPanel` showing branding preview, DPA metadata, contract metadata, recent lifecycle audit entries, and action buttons (Edit, Suspend, Schedule Deletion).
- [X] T048 [US1] [P] Frontend component: `apps/web/components/features/admin/TenantDetailPanel.tsx` rendering the detail layout.
- [X] T049 [US1] [P] Frontend component: `apps/web/components/features/admin/TenantStatusBadge.tsx` — colored badge for `active|suspended|pending_deletion`.
- [X] T050 [US1] Frontend: `apps/web/app/(auth)/setup/page.tsx` — first-admin onboarding landing page; reads invite token from query string, calls `/api/v1/auth/setup-tenant-admin` to bind the user record.
- [X] T051 [US1] CI rule: add lint check at `apps/control-plane/scripts/lint/check_reserved_slug_parity.sh` that hashes the three sources of reserved slugs (`reserved_slugs.py`, the trigger SQL in migration 096, and the Zod schema in `TenantProvisionForm.tsx`) and fails if they diverge.

**Checkpoint**: User Story 1 fully functional and testable independently. Super admin can provision Enterprise tenants via UI; provisioning completes within the five-minute SLA; the first-admin invite arrives.

---

## Phase 4: User Story 2 — Existing data migrates to default tenant (Priority: P1)

**Goal**: Operators can apply the upgrade migration on an audit-pass database and every existing row migrates intact to the default tenant; interrupted runs resume cleanly; reverse migration restores the pre-upgrade state.

**Independent Test**: Per spec User Story 2 — apply migration to a database with realistic audit-pass data; verify default tenant exists, all rows backfilled, RLS active, reverse migration works.

### Tests for User Story 2

- [X] T052 [P] [US2] Build a realistic fixture set at `apps/control-plane/tests/fixtures/audit_pass_realistic.sql` containing representative data across all 35 BCs (workspaces, users, agents, executions, audit-chain entries, costs, conversations, fleets, etc.) — at least one row per tenant-scoped table, plus three large tables (executions, audit-chain entries, costs) seeded with 100K rows to exercise the batched backfill path.
- [X] T053 [P] [US2] Migration test `apps/control-plane/tests/integration/migrations/test_full_upgrade_from_audit_pass.py`: load the fixture, run migrations 096→101, assert (a) `tenants.id = default UUID` exists, (b) every catalogued table has `tenant_id NOT NULL` and every pre-existing row holds the default UUID, (c) row counts match pre-upgrade per table, (d) RLS policy active on every table.
- [X] T054 [P] [US2] Migration test `apps/control-plane/tests/integration/migrations/test_resumable_after_interrupt.py`: simulate interruption mid-098 (kill transaction at random checkpoint); re-run migrations; assert convergence to the same end state and zero double-applied updates.
- [X] T055 [P] [US2] Migration test `apps/control-plane/tests/integration/migrations/test_reverse_migration.py`: apply 096→101, then run the reverse path (`alembic downgrade`), assert the database state matches the pre-upgrade snapshot. Run within `TENANT_MIGRATION_ROLLBACK_WINDOW_HOURS`.

### Implementation for User Story 2

- [X] T056 [US2] Operator runbook `deploy/runbooks/tenant-migration.md`: step-by-step upgrade procedure including pre-migration database snapshot, lenient-mode default for first run, `tenant_enforcement_violations` monitoring guidance, rollback procedure within 24h window, troubleshooting common interruption modes.
- [X] T057 [US2] Add `tenant_enforcement_violations` side table via Alembic migration metadata or directly in 096 — schema: `(id BIGSERIAL PK, occurred_at TIMESTAMPTZ DEFAULT now(), table_name TEXT, query_text TEXT, expected_tenant_id UUID, observed_violation TEXT)`. Used by lenient-mode telemetry per research R10.
- [X] T058 [US2] Implement lenient-mode logging: when `PLATFORM_TENANT_ENFORCEMENT_LEVEL=lenient` and a query against a tenant-scoped table returns zero rows where the application expected at least one (detected by the service-layer caller), write a row to `tenant_enforcement_violations` and emit a structlog warning. Strict mode skips this side path.

**Checkpoint**: User Story 2 fully verified. Operators can upgrade existing platforms; the migration is idempotent, reversible, and produces zero data loss.

---

## Phase 5: User Story 3 — Cross-tenant access opaquely refused (Priority: P1)

**Goal**: A user in tenant A querying a tenant-B resource UUID receives HTTP 404 with a generic body; RLS catches the cross-tenant read even when application code forgets to filter; platform-staff endpoints can still operate cross-tenant.

**Independent Test**: Per spec User Story 3 — provision two tenants; cross-tenant request returns 404 with no information leak; platform-staff endpoint succeeds; no audit-chain entry for the failed probe.

### Tests for User Story 3

- [ ] T059 [P] [US3] Integration test `apps/control-plane/tests/integration/tenants/test_rls_isolation.py` — provision two tenants, populate workspaces in each; cross-tenant read attempts return 404; query the `pg_policies` view to assert `tenant_isolation` policy exists on every catalogued table; assert no audit-chain entry was emitted for the probe.
- [ ] T060 [P] [US3] Integration test `apps/control-plane/tests/integration/tenants/test_platform_staff_bypass.py` — same scenario as above, but using `/api/v1/platform/workspaces/{id}` while authenticated as platform staff; assert the response succeeds and an audit-chain entry IS emitted (`platform.tenants.workspace_read`).
- [ ] T061 [US3] E2E test `apps/control-plane/tests/e2e/suites/tenant_architecture/test_cross_tenant_isolation.py` — Journey J31: full cross-tenant probe matrix across at least eight resource types; byte-identity assertion across responses.

### Implementation for User Story 3 — Bounded-context refactor (parallelizable by BC)

These tasks add explicit `tenant_id` filtering to every existing repository query path AND `tenant_id` to outgoing Kafka event envelopes. Each BC is one task and can run in parallel with the others (different files). The pattern is: read `current_tenant.get()` in the repository constructor or per-method; add `WHERE tenant_id = :tenant_id` to every read query; populate `tenant_id` on every insert; include `tenant_id` in every Kafka event envelope.

- [X] T062 [P] [US3] Refactor `apps/control-plane/src/platform/workspaces/` — add tenant_id filtering to `repository.py` queries; add tenant_id to `events.py` envelopes; remove the placeholder `/tenants/{tenant_id}/...` stub handlers from `admin_router.py` and replace with delegation to `tenants_service`.
- [ ] T063 [P] [US3] Refactor `apps/control-plane/src/platform/accounts/` — `users`, `user_profiles`, `organizations`, `invitations`, `approval_queue` queries all carry tenant_id filter; events include tenant_id.
- [ ] T064 [P] [US3] Refactor `apps/control-plane/src/platform/auth/` — `user_credentials`, `mfa_enrollments`, `auth_attempts`, `password_reset_tokens`, `oauth_links`, `oauth_provider_rate_limits`, `ibor_*` queries carry tenant_id. (OAuth providers tenancy refactor is Track E, separate task.)
- [ ] T065 [P] [US3] Refactor `apps/control-plane/src/platform/audit/` — `audit_chain_entries` queries carry tenant_id; canonical-payload hash includes tenant_id (per T041); chain verification tooling notes appended to runbook.
- [ ] T066 [P] [US3] Refactor `apps/control-plane/src/platform/registry/` — `agent_namespaces`, `agent_profiles`, `agent_revisions`, `capability_models` queries; events include tenant_id.
- [ ] T067 [P] [US3] Refactor `apps/control-plane/src/platform/execution/` — `execution_records`, `execution_steps`, `approval_requests`, `compensation_records`, `scheduled_triggers`; events include tenant_id.
- [ ] T068 [P] [US3] Refactor `apps/control-plane/src/platform/cost_governance/` — all five tables; ClickHouse cost-events insertion includes tenant_id (per constitutional reminder).
- [ ] T069 [P] [US3] Refactor `apps/control-plane/src/platform/interactions/` — five tables.
- [ ] T070 [P] [US3] Refactor `apps/control-plane/src/platform/governance/`, `apps/control-plane/src/platform/policies/`, `apps/control-plane/src/platform/composition/` — group of three small BCs touched together.
- [ ] T071 [P] [US3] Refactor `apps/control-plane/src/platform/connectors/`, `apps/control-plane/src/platform/context_engineering/`, `apps/control-plane/src/platform/discovery/`, `apps/control-plane/src/platform/evaluation/` — group of four medium BCs.
- [ ] T072 [P] [US3] Refactor `apps/control-plane/src/platform/fleets/`, `apps/control-plane/src/platform/fleet_learning/`, `apps/control-plane/src/platform/incident_response/`, `apps/control-plane/src/platform/marketplace/` — group of four BCs.
- [ ] T073 [P] [US3] Refactor `apps/control-plane/src/platform/memory/`, `apps/control-plane/src/platform/model_catalog/`, `apps/control-plane/src/platform/multi_region_ops/` — group of three BCs (memory_entries, model_provider_credentials, region/replication tables).
- [ ] T074 [P] [US3] Refactor `apps/control-plane/src/platform/notifications/`, `apps/control-plane/src/platform/privacy_compliance/`, `apps/control-plane/src/platform/security_compliance/` — group of three BCs.
- [ ] T075 [P] [US3] Refactor `apps/control-plane/src/platform/simulation/`, `apps/control-plane/src/platform/status_page/`, `apps/control-plane/src/platform/testing/`, `apps/control-plane/src/platform/trust/` — group of four BCs.
- [ ] T076 [P] [US3] Refactor `apps/control-plane/src/platform/two_person_approval/`, `apps/control-plane/src/platform/workflows/`, `apps/control-plane/src/platform/agentops/`, `apps/control-plane/src/platform/analytics/`, `apps/control-plane/src/platform/localization/`, `apps/control-plane/src/platform/a2a_gateway/` — group of six remaining BCs.

### CI rules for User Story 3

- [X] T077 [P] [US3] Add CI rule `apps/control-plane/scripts/lint/check_rls_coverage.py`: parse Alembic migrations and SQLAlchemy models; for every model class with a `tenant_id` field, assert that some migration creates a `tenant_isolation` policy on the corresponding table. Wire into `.github/workflows/ci.yml`.
- [ ] T078 [P] [US3] Add CI rule `apps/control-plane/scripts/lint/check_tenant_filter_coverage.py`: AST-walk repository modules; for every `select(...)` against a tenant-scoped table, assert either an explicit `where(Model.tenant_id == ...)` clause OR documented opt-out comment `# RLS-only: rationale` (allowed only in admin/platform paths). Wire into CI.
- [X] T079 [P] [US3] Add CI rule `apps/control-plane/scripts/lint/check_platform_staff_role_scope.py`: AST-walk for `get_platform_staff_session` references; fail if found outside `apps/control-plane/src/platform/tenants/platform_router.py` or any other router file under `/api/v1/platform/*`. Wire into CI.

**Checkpoint**: User Story 3 fully validated. Cross-tenant access is refused at three layers (application filter, RLS, opaque 404). CI gates protect the invariant going forward.

---

## Phase 6: User Story 4 — Hostname routing to default and Enterprise tenants (Priority: P1)

**Goal**: Every HTTP request resolves to its tenant before any other middleware; hostname normalization handles port, case, and subdomain shapes; cache hits keep the p95 below 5 ms.

**Independent Test**: Per spec User Story 4 — issue requests with `Host: app.musematic.ai`, `acme.musematic.ai`, `acme.api.musematic.ai`, `acme.grafana.musematic.ai`; each resolves correctly; cache hit metrics confirm cache-resident lookups.

### Tests for User Story 4

- [ ] T080 [P] [US4] Unit test `apps/control-plane/tests/unit/tenants/test_hostname_normalization.py`: `app.musematic.ai`, `APP.MUSEMATIC.AI`, `app.musematic.ai:443`, `app.musematic.ai:8080` all resolve identically; `<slug>.api.musematic.ai` resolves to slug's tenant API surface; `<slug>.grafana.musematic.ai` resolves to slug's tenant Grafana surface; bare apex `musematic.ai` resolves per the deterministic landing rule.
- [ ] T081 [P] [US4] Performance test `apps/control-plane/tests/integration/tenants/test_resolver_performance.py`: 10000 requests against the same hostname; p95 latency under 5 ms cache-resident; p95 under 50 ms cache-miss (DB round trip).
- [ ] T082 [P] [US4] Integration test `apps/control-plane/tests/integration/tenants/test_resolver_invalidation.py`: mutate a tenant's `branding_config_json` via PATCH; subsequent request to that tenant's subdomain reflects the new branding within the cache TTL; pub/sub invalidation triggers immediate eviction across instances.

### Implementation for User Story 4

- [ ] T083 [US4] Wire Redis pub/sub invalidation in `tenants/service.py`: after every successful tenant update, publish to channel `tenants:invalidate` with the updated tenant's ID. Subscribe in `tenants/resolver.py` and evict matching tier-1 LRU entries; tier-2 Redis key is `DEL`-eted in the same publish operation.
- [ ] T084 [US4] Add resolver health metrics: Prometheus counters `tenant_resolver_lookups_total{result}`, `tenant_resolver_latency_seconds` (histogram), `tenant_resolver_cache_hits_total{tier}`. Exported via existing OpenTelemetry pipeline (UPD-047 observability).
- [ ] T085 [US4] E2E test `apps/control-plane/tests/e2e/suites/tenant_architecture/test_hostname_routing.py` — validates the full set of hostname patterns against a kind cluster running the platform.

**Checkpoint**: User Story 4 fully validated. Hostname routing meets the latency SLA; cache invalidation propagates across instances within seconds.

---

## Phase 7: User Story 5 — Per-tenant branding (Priority: P1)

**Goal**: Pages on `acme.musematic.ai` render Acme's logo / accent / display name; default tenant retains the default Musematic visual identity; super-admin branding updates propagate within the cache TTL.

**Independent Test**: Per spec User Story 5 — provision Acme with non-default branding; navigate to `/login` and `/setup` on Acme subdomain; default branding still renders for `app.musematic.ai`.

### Tests for User Story 5

- [ ] T086 [P] [US5] Frontend Vitest test `apps/web/components/features/shell/__tests__/TenantBrandingProvider.test.tsx` — provider injects branding context; `useTenantContext()` returns expected shape; missing fields fall back to defaults.
- [ ] T087 [P] [US5] Playwright test `apps/web/tests/e2e/tenant-branding.spec.ts` — visit `acme.localtest.me/login`, assert custom logo and accent color render; visit `app.localtest.me/login`, assert default branding renders.

### Implementation for User Story 5

- [ ] T088 [US5] Frontend component: `apps/web/components/features/shell/TenantBrandingProvider.tsx` — React context provider reading SSR-injected tenant context; exposes `useTenantContext()` hook returning `{ id, slug, displayName, kind, branding, status }`.
- [ ] T089 [US5] Frontend hook: `apps/web/lib/hooks/use-tenant-context.ts` — thin wrapper over `useTenantContext()` plus `useTenantBranding()` returning resolved branding (with defaults filled in).
- [ ] T090 [US5] Update `apps/web/app/(main)/layout.tsx` — server component fetches `/api/v1/me/tenant`, passes the result to `TenantBrandingProvider`. Apply CSS custom properties for the accent color from `branding.accent_color_hex`.
- [ ] T091 [US5] Update `apps/web/app/(auth)/login/page.tsx` — read tenant context, render branded logo and display name; refuse login for users not bound to the resolved tenant (FR per spec).
- [ ] T092 [US5] [P] Add `apps/web/components/features/admin/TenantBrandingPreview.tsx` — admin-side preview of how a tenant's branding will render; used in the tenant detail page.
- [ ] T093 [US5] [P] Frontend hook: `apps/web/lib/hooks/use-tenant-mutations.ts` — TanStack Query mutations for `useUpdateBranding`, `useSuspendTenant`, `useReactivateTenant`, `useScheduleDeletion`, `useCancelDeletion`. Used by detail-panel actions.
- [ ] T094 [US5] Cookie scoping: update `apps/control-plane/src/platform/auth/jwt_service.py` and any session-cookie issuance path to set `Domain={tenant.subdomain}.{platform_domain}` rather than a global cookie domain. Verify in integration test that cookies issued by `app.musematic.ai` are not accepted by `acme.musematic.ai` and vice versa.
- [ ] T095 [US5] Add `tenant_id`, `tenant_slug`, `tenant_kind` claims to JWT issuance per `contracts/jwt-claim-additions.md`. Validate the `tenant_id` claim matches the resolved tenant in `auth_middleware.py`; mismatch returns 401 with `code=tenant_mismatch`.

**Checkpoint**: User Story 5 fully validated. Branding renders correctly per tenant; cookie-scoping prevents cross-tenant session reuse; JWT carries tenant context.

---

## Phase 8: User Story 6 — Unknown subdomain returns opaque 404 (Priority: P2)

**Goal**: Any unresolved hostname returns HTTP 404 with a body byte-identical to every other unresolved-hostname response; timing variance below the enumeration-protection threshold.

**Independent Test**: Per spec User Story 6 — issue requests against 100 random unresolved hosts; SHA-256 of bodies and headers all match.

### Tests for User Story 6

- [ ] T096 [P] [US6] Test `apps/control-plane/tests/integration/tenants/test_unknown_subdomain_byte_identity.py` — issue 100 randomly-generated unresolved hostnames; assert SHA-256 of body and headers are constant across all.
- [ ] T097 [P] [US6] Test `apps/control-plane/tests/integration/tenants/test_unknown_subdomain_timing.py` — measure latency variance across cache-hit, cache-miss-known, unknown-host code paths; assert variance below the documented enumeration-protection threshold (e.g., 95th-percentile spread < 2 ms).
- [ ] T098 [US6] E2E test `apps/control-plane/tests/e2e/suites/tenant_architecture/test_unknown_subdomain_404.py` — full kind-cluster validation with realistic ingress-induced timing.

### Implementation for User Story 6

- [ ] T099 [US6] Refine the `_apply_timing_floor()` helper in the resolver middleware: in lenient mode use `random.uniform(0, 1) ms` jitter to smooth path differences; in strict mode use `await asyncio.sleep(0)` only (zero added latency unless benchmarks show enumeration vector). Default switching gated by `PLATFORM_TENANT_ENFORCEMENT_LEVEL`.

**Checkpoint**: User Story 6 fully validated. Unknown subdomains opaque; enumeration vector closed.

---

## Phase 9: User Story 7 — Tenant suspension and deletion (Priority: P2)

**Goal**: Super admin can suspend a tenant (data preserved, access blocked), reactivate it, schedule deletion (with grace period and 2PA), cancel scheduled deletion, and complete cascading deletion with tombstone after grace.

**Independent Test**: Per spec User Story 7 — suspend Acme; access blocked; reactivate; schedule deletion; cancel; re-schedule; let grace expire; cascade runs; tombstone exists.

### Tests for User Story 7

- [ ] T100 [P] [US7] Integration test `apps/control-plane/tests/integration/tenants/test_suspension_reactivation.py` — full suspend / reactivate cycle; cookie-bearing requests blocked; non-data API endpoints (e.g., `/api/v1/me/tenant`) return suspension banner; data preserved across the cycle.
- [ ] T101 [P] [US7] Integration test `apps/control-plane/tests/integration/tenants/test_deletion_two_phase.py` — schedule deletion (with 2PA); during grace period access blocked but data preserved; cancel deletion → tenant reactivates; re-schedule and let grace elapse → cascade runs → tombstone audit-chain entry exists with `cascade_complete: true` and per-BC row count digest.
- [ ] T102 [US7] E2E test `apps/control-plane/tests/e2e/suites/tenant_architecture/test_tenant_suspension.py`.
- [ ] T103 [US7] E2E test `apps/control-plane/tests/e2e/suites/tenant_architecture/test_tenant_deletion_two_phase.py`.

### Implementation for User Story 7

- [ ] T104 [US7] Extend `apps/control-plane/src/platform/tenants/service.py` with: `suspend_tenant(actor, id, reason)`, `reactivate_tenant(actor, id)`, `schedule_deletion(actor, id, reason, two_pa_token)`, `cancel_deletion(actor, id)`, `complete_deletion(tenant_id)` (called by scheduler). Each emits the corresponding Kafka event and audit-chain entry.
- [ ] T105 [US7] Wire 2PA validation into `schedule_deletion`: integrate with `apps/control-plane/src/platform/two_person_approval/service.py` (UPD-036). Server-side validate the token freshly per audit-pass rule 33.
- [ ] T106 [US7] Add the deletion-grace scheduler: APScheduler job in the `scheduler` runtime profile that selects `tenants WHERE status='pending_deletion' AND scheduled_deletion_at <= now()` and invokes `complete_deletion` for each. Exactly-once semantics via `FOR UPDATE SKIP LOCKED`.
- [ ] T107 [US7] Implement cascading deletion: per-BC delete handlers registered in a `tenant_cascade_registry` (each BC owner registers its handler in its `__init__.py` startup hook). The cascade engine in `tenants/service.py:complete_deletion` iterates the registry in dependency order, deleting tenant-scoped rows; each handler returns its row count for the tombstone digest.
- [ ] T108 [US7] Add the suspension/deletion endpoints to `apps/control-plane/src/platform/tenants/admin_router.py`: `POST /suspend`, `POST /reactivate`, `POST /schedule-deletion`, `POST /cancel-deletion` per `contracts/admin-tenants-rest.md`. Refuse default tenant (FR-002). Audit-chain + Kafka emitted.
- [ ] T109 [US7] [P] Frontend component: `apps/web/components/features/shell/SuspensionBanner.tsx` — top-of-page banner rendered on `(main)/layout.tsx` whenever `useTenantContext().status === 'suspended'`. Includes localized "Contact support" CTA.
- [ ] T110 [US7] [P] Frontend component: `apps/web/components/features/admin/DeletionGracePeriodCountdown.tsx` — countdown timer rendered on the tenant detail page when `status === 'pending_deletion'`; counts down to `scheduled_deletion_at`; renders "Cancel deletion" button.
- [ ] T111 [US7] Add `apps/control-plane/src/platform/tenants/platform_router.py` with `POST /api/v1/platform/tenants/{id}/force-cascade-deletion` per `contracts/platform-tenants-rest.md`. Requires platform-staff role + 2PA + incident-mode flag.

**Checkpoint**: User Story 7 fully validated. Lifecycle transitions auditable; 2PA enforced for deletion; cascade is exactly-once with tombstone proof.

---

## Phase 10: User Story 8 — Default tenant immutable (Priority: P2)

**Goal**: Operators cannot delete, rename, or disable the default tenant via any code path. Database, application, and UI all refuse.

**Independent Test**: Per spec User Story 8 — attempt delete/rename/disable via UI, admin API, platform API, and direct DB; every attempt refused with no state change.

### Tests for User Story 8

- [ ] T112 [P] [US8] Integration test `apps/control-plane/tests/integration/tenants/test_default_tenant_immutable.py` — attempt every mutation (PATCH, suspend, schedule-deletion, force-cascade-deletion) on the default tenant via every endpoint; each returns 409 with `code=default_tenant_immutable`; database state unchanged.
- [ ] T113 [P] [US8] DB-level test `apps/control-plane/tests/integration/migrations/test_default_tenant_trigger.py` — attempt direct DELETE / UPDATE on the default tenant row using the platform-staff role; trigger refuses with the documented exception message.
- [ ] T114 [US8] E2E test `apps/control-plane/tests/e2e/suites/tenant_architecture/test_default_tenant_constraints.py` — Journey J36: full UI + API attempt matrix; UI buttons disabled with explanatory tooltip; API returns 409.

### Implementation for User Story 8

- [ ] T115 [US8] Add application-layer guard in `tenants/service.py` for every mutation method: short-circuit with `DefaultTenantImmutableError` when the target tenant has `kind='default'`. Required even though the DB trigger catches it; this gives the UI a clean error path.
- [ ] T116 [US8] Frontend: in `apps/web/app/(admin)/admin/tenants/[id]/page.tsx`, when the rendered tenant has `kind === 'default'`, disable the Suspend / Schedule Deletion buttons and render a tooltip explaining the constitutional constraint (SaaS-9).

**Checkpoint**: User Story 8 fully validated. Default tenant is immutable at every layer.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Track D (Vault path scoping), Track E (OAuth per-tenant), Track G (observability + journey rollout), runbook, lenient→strict promotion, deletion of superseded code.

### Track D — Vault path scoping

- [ ] T117 [P] Update `apps/control-plane/src/platform/common/secret_provider.py:CANONICAL_SECRET_PATH_RE` to accept BOTH the legacy regex (existing pattern) AND the new tenant-scoped pattern `^secret/data/musematic/(production|staging|dev|test|ci)/tenants/(default|[a-z][a-z0-9-]{0,30}[a-z0-9])/(oauth|model-providers|notifications|ibor|audit-chain|connectors|accounts|_internal)/[a-zA-Z0-9_/-]+$` AND the platform-scoped pattern `^secret/data/musematic/(production|...)/_platform/...`. Add `validate_secret_path` test cases.
- [ ] T118 [P] Update every caller of `secret_provider.get/put` across the codebase to construct paths via `tenant_vault_path(env, tenant_slug, domain, resource)` from `tenants/vault_paths.py`. Add `tenant_slug` resolution from `current_tenant.get()`.
- [ ] T119 Author secrets-migration utility `apps/ops-cli/secrets-migrate.py`: walks every legacy path under `secret/data/musematic/{env}/{domain}/...`, copies its current version to `secret/data/musematic/{env}/tenants/default/{domain}/...`, verifies the read at the new path, then logs (does NOT delete legacy until follow-up patch removes the dual-read window).
- [ ] T120 [P] Update Vault policy templates `deploy/vault/policies/tenant-scoped.hcl.tpl` to grant tenant-scoped read on `secret/data/musematic/{env}/tenants/{slug}/...` and platform-scoped read on `secret/data/musematic/{env}/_platform/...`.

### Track E — OAuth per-tenant

- [ ] T121 Author Alembic migration `apps/control-plane/migrations/versions/102_oauth_provider_tenant_scope.py`: drop existing UNIQUE on `oauth_providers.provider_type`; add UNIQUE on `(tenant_id, provider_type)`; backfill `tenant_id = default UUID` for existing rows.
- [ ] T122 Update `apps/control-plane/src/platform/auth/models.py:OAuthProvider` model — `tenant_id` column, composite uniqueness; update `apps/control-plane/src/platform/auth/service.py` OAuth resolution to query by `(current_tenant.id, provider_type)`.
- [ ] T123 Update `apps/control-plane/src/platform/auth/router.py` OAuth callback endpoint to construct the callback URL `https://{tenant.subdomain}.{platform_domain}/auth/oauth/{provider}/callback` from the resolved tenant; backward-compat redirect from the legacy global callback to the default-tenant scope for one release.
- [ ] T124 [P] Frontend: extend `apps/web/app/(admin)/admin/oauth/page.tsx` (UPD-041) to expose per-tenant OAuth configuration under a tenant selector; super admin sees all tenants; tenant admins see only their own tenant's OAuth.
- [ ] T125 Integration test `apps/control-plane/tests/integration/tenants/test_oauth_per_tenant.py` — Acme has its own OAuth client ID; Acme's `/auth/oauth/google/callback` uses Acme's config; default tenant's callback uses default's config.

### Track G — Observability and dashboard

- [ ] T126 [P] Author Grafana dashboard ConfigMap `deploy/helm/observability/templates/dashboards/tenants.yaml` (audit-pass rule 24 — every new BC gets a dashboard). Panels: tenant provisioning rate, suspension rate, deletion-cascade rate, hostname-resolver latency p50/p95/p99, cache hit ratio per tier, RLS-enforcement violation rate from `tenant_enforcement_violations`, unknown-host probe rate.
- [ ] T127 [P] Add structured-log fields to all tenants-BC log lines: `tenant_id`, `tenant_slug`, `tenant_kind` (audit-pass rule 21 correlation IDs).

### Track G — E2E journey suite

- [ ] T128 [P] Author E2E test `apps/control-plane/tests/e2e/suites/tenant_architecture/test_default_tenant_exists.py`: assert that on a freshly-installed kind cluster the default tenant exists with the well-known UUID, slug `default`, subdomain `app`, and the seeder is idempotent.
- [ ] T129 [P] Add the `tenant_architecture` suite to the E2E runner registry at `tests/e2e/conftest.py`.
- [ ] T130 Wire the J22 Tenant Provisioning journey into the journey registry (`tests/e2e/journeys/__init__.py` or equivalent); covers super admin login, provisioning Acme, DNS reachability assertion, first-admin invitation, first sign-in.
- [ ] T131 Wire the J31 Cross-Tenant Isolation journey into the journey registry; covers two-tenant setup, cross-tenant probe matrix.
- [ ] T132 Wire the J36 Default Tenant Constraints journey into the journey registry.
- [ ] T133 Run the existing journeys J01–J21 against the post-migration database; capture the regression report. Fix any failures introduced by the BC refactor in Phase 5.

### Lenient → strict promotion + cleanup

- [ ] T134 Author the lenient→strict promotion runbook section in `deploy/runbooks/tenant-provisioning.md`: "After seven consecutive days with zero rows in `tenant_enforcement_violations` under production traffic, set `PLATFORM_TENANT_ENFORCEMENT_LEVEL=strict` via `kubectl set env deployment/control-plane`, roll the deployment, and verify metrics."
- [ ] T135 Delete the obsolete `apps/control-plane/src/platform/admin/tenant_mode_router.py` and its router registration (`PLATFORM_TENANT_MODE` is removed by constitution v2.0.0). Update any references in tests / OpenAPI snapshots.
- [ ] T136 [P] Update `apps/control-plane/src/platform/admin/responses.py:tenant_id_from_user()` — read from `request.state.tenant.id` first, fall back to JWT claim only for compatibility with pre-migration tokens during the lenient window.
- [ ] T137 [P] Update `apps/control-plane/src/platform/admin/activity_feed.py` and `config_export_service.py` to filter by `request.state.tenant` consistently.

### Documentation

- [ ] T138 [P] Update root `README.md` to mention multi-tenant SaaS architecture; reference the tenant-provisioning runbook.
- [ ] T139 [P] Update `docs/system-architecture.md` and `docs/software-architecture.md` to describe the tenant primitive, hostname resolver, RLS posture, and platform-staff role segregation.
- [ ] T140 [P] Add `docs/saas/tenant-architecture.md` documentation page (UPD-089 docs site) describing the architecture for operators and developers.

### Constitutional checks

- [ ] T141 Run `apps/control-plane/scripts/lint/check_rls_coverage.py`, `check_tenant_filter_coverage.py`, `check_platform_staff_role_scope.py`, `check_reserved_slug_parity.sh` locally; resolve any flagged violations before opening the PR.
- [ ] T142 Validate quickstart.md walkthrough end-to-end on a fresh kind cluster; capture any drift and update the doc.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — can start immediately.
- **Phase 2 (Foundational)**: Depends on Setup completion — **BLOCKS all user stories**. Track A migrations 096→101 must complete in order (097 depends on 096; 098 depends on 097; etc.). Track B middleware depends on T013 (Tenant model), T021 (resolver), T025 (segregated engines).
- **Phase 3 (US1)**: Depends on Phase 2 (the tenants table, the resolver, the audit-chain integration must exist).
- **Phase 4 (US2)**: Depends on Phase 2 (the migration suite must exist to be tested).
- **Phase 5 (US3)**: Depends on Phase 2 (RLS policies must exist; segregated engines must be wired). The 15 BC-refactor tasks T062–T076 are mutually parallel.
- **Phase 6 (US4)**: Depends on Phase 2 (resolver must exist) and benefits from Phase 5 (BC refactor improves cross-tenant probe behavior). Can begin alongside Phase 5 once the resolver is wired.
- **Phase 7 (US5)**: Depends on Phase 2 + Phase 5's BC refactor of `auth/` (T064) for cookie-domain scoping.
- **Phase 8 (US6)**: Depends on Phase 2.
- **Phase 9 (US7)**: Depends on Phase 2 + Phase 3 (provisioning must work before deletion is meaningful).
- **Phase 10 (US8)**: Depends on Phase 2 (migration 096 already creates the immutability trigger) and Phase 9 (suspension/deletion endpoints must exist to test their refusal for the default tenant).
- **Phase 11 (Polish)**: Depends on all user-story phases. Track D Vault refactor and Track E OAuth refactor can ship as a follow-up release if user-story phases are time-boxed; the lenient→strict promotion is a separate operator action.

### User Story Dependencies

- **US1 (Provisioning)**: Independent once Phase 2 lands — first user story to demonstrate value (the MVP).
- **US2 (Migration)**: Independent once Phase 2 lands.
- **US3 (Cross-tenant isolation)**: Independent once Phase 2 lands; Phase 5's BC refactor is the longest single track.
- **US4 (Hostname routing)**: Independent once Phase 2 lands.
- **US5 (Branding)**: Mostly independent; Phase 5's BC refactor of `auth/` (T064) is a soft dependency for cookie scoping.
- **US6 (Opaque 404)**: Independent.
- **US7 (Suspension/deletion)**: Soft dependency on US1 (provisioning) so there are tenants to suspend/delete.
- **US8 (Default-tenant immutable)**: Soft dependency on US7 (the deletion endpoint must exist to validate its refusal for the default tenant).

### Within Each User Story

- Tests written alongside or before implementation (constitutional rule for this feature given the security stakes).
- Models before services; services before routers.
- BC refactor tasks (T062–T076) are mutually independent and parallel-friendly.
- Frontend tasks for a story can begin once the corresponding backend endpoint contract is fixed.

---

## Parallel Execution Opportunities

- **Phase 1**: T002, T003, T004, T005 are all parallel (different files).
- **Phase 2**: Track A's models/schemas/exceptions/events/vault-paths (T013–T017) are parallel with each other. Foundational tests T028–T033 are parallel with each other. Track A migrations 096→101 are sequential.
- **Phase 3 (US1)**: T034, T035 (tests), T037, T042, T044, T045, T048, T049 are mutually parallel after the service skeleton lands.
- **Phase 5 (US3)**: T062–T076 are 15 mutually parallel BC-refactor tasks — the bulk of the wall-clock work. Allocate them across 2–3 engineers. CI lint rule tasks T077–T079 are parallel with each other.
- **Phase 7 (US5)**: T086 (Vitest), T087 (Playwright), T092, T093 are parallel.
- **Phase 11 (Polish)**: T117, T118, T120 (Track D), T124 (Track E UI), T126, T127 (Track G), T128, T129 (E2E suite), T136, T137, T138, T139, T140 are largely parallel with each other.

### Parallel Example — Phase 5 BC Refactor

```bash
# Three engineers each pick a band of tasks. With pytest-xdist on the test suite, the entire phase
# completes in ~2 days rather than 5 if serialized.
Engineer A: T062 (workspaces) → T065 (audit) → T068 (cost_governance) → T071 → T074
Engineer B: T063 (accounts) → T064 (auth) → T067 (execution) → T072 → T075
Engineer C: T066 (registry) → T069 (interactions) → T070 (governance) → T073 → T076
# Engineer A also pairs on T077 (CI: rls coverage)
# Engineer B also pairs on T078 (CI: tenant filter)
# Engineer C also pairs on T079 (CI: platform-staff scope)
```

---

## Implementation Strategy

### MVP First — User Story 1 only

1. Complete Phase 1 (Setup) — ~half a day.
2. Complete Phase 2 (Foundational) — ~3 days. **CRITICAL** — blocks every user story.
3. Complete Phase 3 (User Story 1 — Provisioning) — ~1.5 days.
4. **STOP and VALIDATE**: Provision a tenant on a kind cluster. Confirm DNS, TLS, branding, and first-admin invite all work end-to-end (the J22 journey).
5. Demo to stakeholders if ready.

### Incremental Delivery

1. Foundation ready (Phase 1 + Phase 2).
2. Add User Story 1 (provisioning) → demo MVP.
3. Add User Story 2 (migration) → enables operator upgrades.
4. Add User Story 3 (isolation) → enables Enterprise customer onboarding without security risk.
5. Add User Story 4 (routing) → confirms latency SLA.
6. Add User Story 5 (branding) → polishes Enterprise UX.
7. Add User Story 6 (opaque 404) → closes enumeration vector.
8. Add User Story 7 (suspension/deletion) → enables full lifecycle.
9. Add User Story 8 (immutability) → constitutional guarantee.
10. Polish (Phase 11) → Vault, OAuth, observability, cleanup, docs.

### Parallel Team Strategy (3 engineers)

- **Day 0**: All three on Phase 1 + Phase 2 Track A migrations (sequential coordination).
- **Days 1–3**: Engineer A finishes migrations and Track B middleware; Engineers B + C start the BC refactor batches in Phase 5.
- **Days 3–5**: Engineer A on US1 (provisioning) + frontend; Engineers B + C continue Phase 5 BC refactor; pair on the three CI rules.
- **Days 5–6**: All three converge on US2 (migration tests), US4 (resolver perf), US5 (branding), US6 (opaque 404).
- **Days 6–7**: US7 (suspension/deletion) and US8 (immutability).
- **Days 7–8**: Polish phase, Track D (Vault), Track E (OAuth), Track G (E2E + dashboards).

---

## Notes

- [P] tasks = different files, no dependencies on incomplete prior tasks.
- [Story] label maps task to its user story for traceability and for rolling back a story-specific increment cleanly.
- Each user story is independently testable — the journey suite (J22, J31, J36) plus the per-story integration tests cover this.
- Verify tests fail before implementing the production code path.
- Commit after each task or logical group (the git pre-task auto-commit hook is configured).
- Stop at any user-story checkpoint to validate independently.
- The 15-task Phase 5 BC refactor is the largest single block; parallelize aggressively.
- The lenient→strict promotion is a separate operator decision after the feature lands; do not gate the merge on it.
