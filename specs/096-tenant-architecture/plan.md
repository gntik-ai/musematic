# Implementation Plan: UPD-046 — Tenant Architecture (Subdomain + RLS + Default-Plus-Enterprise)

**Branch**: `096-tenant-architecture` | **Date**: 2026-05-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/096-tenant-architecture/spec.md`

## Summary

UPD-046 introduces the `Tenant` entity as a first-class isolation primitive in the modular monolith. Strategy is **migration-first**: schema, hostname middleware, and the `tenants/` bounded context land before bounded-context query refactors. A staged-rollout feature flag `PLATFORM_TENANT_ENFORCEMENT_LEVEL=lenient|strict` lets operators run the new schema with verbose RLS-violation logging before flipping to hard enforcement. The default tenant has a stable, hardcoded UUID and is provisioned by an idempotent seeder; Enterprise tenants are provisioned manually by super admin via `/admin/tenants/new` and reach a working subdomain within five minutes.

The work is the largest single feature in the SaaS pass and touches every existing bounded context. Wave 21 (first SaaS feature). Estimated 14 engineering days; ~7–8 wall-clock days with three engineers in parallel.

## Technical Context

**Language/Version**: Python 3.12+ (control plane), TypeScript 5.x strict (Next.js admin workbench), SQL/PL/pgSQL (PostgreSQL 16).
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, asyncpg, redis-py 5.x async (resolver cache), aiokafka 0.11+ (lifecycle events), aioboto3 (DPA artifact storage), httpx (Hetzner DNS API), TanStack Query v5 + React Hook Form + Zod (admin UI). All in existing `requirements.txt` / `apps/web/package.json` — **no new packages**.
**Storage**: PostgreSQL 16 — 1 new table (`tenants`), additive `tenant_id UUID NOT NULL` column on ~40 existing tables (catalogue in `data-model.md`), RLS policies on every tenant-scoped table, new `musematic_platform_staff` PG role with `BYPASSRLS`. Redis — new key family `tenants:resolve:{host}` (resolver cache, TTL configurable, default 60s). MinIO/S3 — new bucket `tenant-dpas` for DPA PDF blobs. Vault — path family refactored from `secret/data/musematic/{env}/{domain}/...` → `secret/data/musematic/{env}/tenants/{slug}/{domain}/...` (tenant-scoped) + `secret/data/musematic/{env}/_platform/{domain}/...` (platform-scoped, e.g., cert-manager). Vault KV-v2 versioning preserves prior secrets through dual-read window.
**Testing**: pytest + pytest-asyncio 8.x (control plane unit + integration), pytest fixtures with realistic audit-pass data for migration tests, Playwright (admin UI E2E), the existing `tests/e2e/` harness for cross-tenant isolation suite.
**Target Platform**: Linux containers on Kubernetes (Hetzner Cloud production cluster + dev cluster per constitutional rule SaaS-45).
**Project Type**: Web application — Python control plane (`apps/control-plane/`) + Next.js admin/user frontend (`apps/web/`).
**Performance Goals**: Hostname middleware p95 < 5 ms cache-resident, < 50 ms cache miss (SC-005). RLS query overhead < 10% on the existing benchmark suite.
**Constraints**: Defense-in-depth — RLS is the safety net, application code MUST still filter by `tenant_id` (SaaS-11). Cross-tenant 404 must be byte-identical (SC-009). Migration must be idempotent, checkpointed, reversible within rollback window (FR-028, FR-030). Default tenant UUID is hardcoded and immutable (SaaS-9, FR-002). gRPC contracts maintain backward compatibility for one minor version (constitutional input constraint #2).
**Scale/Scope**: Tenants per deployment in the dozens to low hundreds (Enterprise customer count); ~40 tenant-scoped tables × backfill of full audit-pass data; 8 P1+P2 user stories; 44 functional requirements; 10 success criteria.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The constitution at v2.0.0 introduces SaaS-1 through SaaS-50 alongside Core Principles I–XVI and brownfield rules 1–50. This plan complies with each applicable rule:

| Rule | Application in this plan |
|---|---|
| Brownfield-1 (never rewrite) | All work extends existing files (`main.py`, `auth/models.py`, `secret_provider.py`, `audit/models.py`, etc.). New `tenants/` BC follows the standard layout. |
| Brownfield-2 (every change is an Alembic migration) | Six new Alembic migrations 096→101 (split for readability and checkpoint safety). No raw DDL. |
| Brownfield-3 (preserve existing tests) | Existing pytest + E2E suites continue to pass. New tests added under `tests/unit/tenants/`, `tests/integration/tenants/`, `tests/e2e/suites/tenant_architecture/`. |
| Brownfield-7 (backward-compatible APIs) | All existing REST endpoints continue to function. New `tenant_id` field on response schemas is additive. JWT gains an additive `tenant_id` claim. |
| Brownfield-8 (feature flags) | Rollout flag `PLATFORM_TENANT_ENFORCEMENT_LEVEL=lenient|strict` (lenient default during rollout, strict in production). |
| SaaS-2 (two tenant kinds only) | DB CHECK constraint + service validation: `kind IN ('default', 'enterprise')`. |
| SaaS-3 (tenants are not self-serve) | No public-facing creation route; only `/api/v1/admin/tenants/*` (super-admin) and `/api/v1/platform/tenants/*` (platform-staff). |
| SaaS-9 (default tenant is a constant) | `CREATE UNIQUE INDEX tenants_one_default ON tenants (kind) WHERE kind = 'default'` plus deletion/rename refused at DB trigger and application service. Hardcoded default UUID `00000000-0000-0000-0000-000000000001`. |
| SaaS-10 (subdomain routing primary) | `TenantResolverMiddleware` registered LAST (Starlette processes registered middleware in reverse, so last-added runs first) in `apps/control-plane/src/platform/main.py:create_app()`, before any other middleware. |
| SaaS-11 (RLS first, app code second) | RLS policy on every tenant-scoped table; service layer also adds explicit `WHERE tenant_id = :ctx_tenant_id`. CI static analysis enforces both. |
| SaaS-12 (cross-tenant queries rejected) | Privileged DB role `musematic_platform_staff` is the only `BYPASSRLS` role; routes only used under `/api/v1/platform/*`. CI rule blocks any other reference. |
| SaaS-19 (hostname-to-tenant before anything else) | Confirmed registration order; resolver runs before `AuthMiddleware` and before `MaintenanceGateMiddleware`. |
| SaaS-20 (default slug `default`) | Seeder hardcodes slug `default`, subdomain `app`, and the canonical UUID. |
| SaaS-33 (PostgreSQL RLS mandatory) | Migration 100 enables RLS and creates `tenant_isolation` policy on every tenant-scoped table. |
| SaaS-34 (`SET LOCAL app.tenant_id` per request) | SQLAlchemy event listener `before_cursor_execute` sets the GUC at session-start time inside the request transaction. |
| SaaS-35 (Vault paths tenant-scoped) | `secret_provider.py` regex updated; new `tenant_vault_path()` helper; migration utility moves existing secrets. |
| SaaS-36 (per-tenant SSO) | `oauth_providers.tenant_id` added; uniqueness changes from `(provider_type)` to `(tenant_id, provider_type)`. |
| SaaS-37 (cookie scoping) | Session cookie `Domain` attribute computed from resolved tenant subdomain rather than from a global `COOKIE_DOMAIN` setting. |
| SaaS-38 (per-tenant OAuth callbacks) | Callback URL template `https://{tenant_subdomain}.{platform_domain}/auth/oauth/{provider}/callback` constructed at config time. |
| Audit Chain (rule 9) hash inclusion of `tenant_id` | `audit/models.py` AuditChainEntry gains `tenant_id` column; canonical-payload hashing function updated to include `tenant_id`; verification tooling for v1.x chains is unaffected for entries written under v1.x (chain remains valid up to the migration boundary; new entries form a new sub-chain whose first entry's `previous_hash` is the last v1 entry's hash). |
| Audit-pass rule 24 (every new BC gets a dashboard) | Track G adds `deploy/helm/observability/templates/dashboards/tenants.yaml` with provisioning, suspension, deletion, and unknown-host metrics. |
| Audit-pass rule 25 (every new BC gets E2E + journey) | Phase 7 authors `tests/e2e/suites/tenant_architecture/` and the J22 Tenant Provisioning journey. |

**Result**: PASS. No violations. The Complexity Tracking section is intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/096-tenant-architecture/
├── plan.md              # This file (/speckit-plan output)
├── spec.md              # Feature spec
├── research.md          # Phase 0 — resolved unknowns + technical decisions
├── data-model.md        # Phase 1 — Tenant entity, ~40 tenant-scoped table catalogue, RLS schema
├── quickstart.md        # Phase 1 — local-dev validation walkthrough
├── contracts/           # Phase 1 — REST + Kafka + JWT contract specs
│   ├── admin-tenants-rest.md
│   ├── platform-tenants-rest.md
│   ├── tenant-events-kafka.md
│   ├── tenant-resolution-context.md
│   └── jwt-claim-additions.md
├── checklists/
│   └── requirements.md  # Spec quality checklist (already present)
└── tasks.md             # Phase 2 — generated by /speckit-tasks (NOT created by this command)
```

### Source Code (repository root)

```text
apps/control-plane/
├── src/platform/
│   ├── main.py                                  # MODIFY: register TenantResolverMiddleware last in create_app()
│   ├── tenants/                                 # NEW bounded context (standard layout per Brownfield rule 4)
│   │   ├── __init__.py
│   │   ├── models.py                            # SQLAlchemy Tenant model
│   │   ├── schemas.py                           # Pydantic request/response schemas
│   │   ├── service.py                           # TenantsService — provisioning, suspension, deletion lifecycle
│   │   ├── repository.py                        # Repository (uses platform-staff role for cross-tenant queries)
│   │   ├── router.py                            # /api/v1/me/tenant (read-only introspection for current request)
│   │   ├── admin_router.py                      # /api/v1/admin/tenants/* (super admin)
│   │   ├── platform_router.py                   # /api/v1/platform/tenants/* (platform staff, BYPASSRLS pool)
│   │   ├── seeder.py                            # Default-tenant idempotent provisioner (called at install + main startup)
│   │   ├── resolver.py                          # Hostname → Tenant lookup with Redis-backed cache
│   │   ├── dns_automation.py                    # Hetzner DNS API client (stub returning success in dev; full impl in UPD-053)
│   │   ├── vault_paths.py                       # Tenant-aware Vault path helpers (used across BCs)
│   │   ├── events.py                            # Kafka event envelopes for tenants.lifecycle.*
│   │   └── exceptions.py                        # ReservedSlugError, DefaultTenantImmutableError, TenantNotFoundError, …
│   ├── common/
│   │   ├── middleware/
│   │   │   └── tenant_resolver.py               # NEW: TenantResolverMiddleware
│   │   ├── tenant_context.py                    # NEW: ContextVar[TenantContext] + helpers
│   │   ├── secret_provider.py                   # MODIFY: regex update, tenant_vault_path() helper
│   │   ├── database.py                          # MODIFY: SET LOCAL app.tenant_id event listener; segregated platform-staff engine
│   │   └── config.py                            # MODIFY: PLATFORM_DOMAIN, PLATFORM_TENANT_ENFORCEMENT_LEVEL, TENANT_RESOLVER_CACHE_TTL_SECONDS
│   ├── auth/
│   │   ├── models.py                            # MODIFY: OAuthProvider gains tenant_id; uniqueness migrates to (tenant_id, provider_type)
│   │   ├── service.py                           # MODIFY: per-tenant OAuth resolution via request context
│   │   └── jwt_service.py                       # MODIFY: include tenant_id claim
│   ├── audit/
│   │   ├── models.py                            # MODIFY: AuditChainEntry.tenant_id added
│   │   └── service.py                           # MODIFY: include tenant_id in canonical_payload hashing
│   ├── admin/
│   │   ├── tenant_mode_router.py                # DELETE: PLATFORM_TENANT_MODE flag is removed (constitution v2.0.0)
│   │   ├── responses.py                         # MODIFY: tenant_id_from_user reads from request.state.tenant when present
│   │   └── activity_feed.py                     # MODIFY: filter activity by request.state.tenant
│   └── workspaces/
│       └── admin_router.py                      # MODIFY: replace stub /tenants/* handlers with delegation to tenants service
└── migrations/versions/
    ├── 096_tenant_table_and_seed.py             # NEW: tenants table, default-tenant seed, reserved-slug trigger, dpa metadata
    ├── 097_tenant_id_columns_nullable.py        # NEW: add tenant_id UUID NULL to all tenant-scoped tables
    ├── 098_tenant_id_backfill_default.py        # NEW: backfill tenant_id = default UUID with checkpoint table
    ├── 099_tenant_id_not_null_and_indexes.py    # NEW: ALTER NOT NULL + create per-table tenant_id indexes
    ├── 100_tenant_rls_policies.py               # NEW: ENABLE RLS + CREATE POLICY tenant_isolation on every tenant-scoped table
    ├── 101_platform_staff_role.py               # NEW: CREATE ROLE musematic_platform_staff WITH BYPASSRLS
    └── 102_oauth_provider_tenant_scope.py       # NEW: oauth_providers.tenant_id + composite uniqueness; default-tenant backfill
└── tests/
    ├── unit/tenants/
    │   ├── test_resolver.py
    │   ├── test_service.py
    │   ├── test_seeder.py
    │   ├── test_vault_paths.py
    │   └── test_default_tenant_immutable.py
    ├── integration/tenants/
    │   ├── test_hostname_middleware.py
    │   ├── test_rls_isolation.py
    │   ├── test_platform_staff_bypass.py
    │   ├── test_provision_enterprise.py
    │   ├── test_suspension_reactivation.py
    │   ├── test_deletion_two_phase.py
    │   ├── test_oauth_per_tenant.py
    │   └── test_audit_chain_tenant_id.py
    └── e2e/suites/tenant_architecture/
        ├── test_default_tenant_exists.py
        ├── test_enterprise_tenant_provisioning.py     # journey J22
        ├── test_cross_tenant_isolation.py             # journey J31
        ├── test_default_tenant_constraints.py         # journey J36
        ├── test_tenant_suspension.py
        ├── test_tenant_deletion_two_phase.py
        ├── test_hostname_routing.py
        └── test_unknown_subdomain_404.py

apps/web/
├── app/
│   ├── (admin)/
│   │   ├── admin/
│   │   │   └── tenants/
│   │   │       ├── page.tsx                     # MODIFY: replace stub with real list (TanStack Query → /api/v1/admin/tenants)
│   │   │       ├── new/
│   │   │       │   └── page.tsx                 # NEW: provisioning form (RHF + Zod)
│   │   │       ├── [id]/
│   │   │       │   ├── page.tsx                 # MODIFY: real detail with edit/suspend/delete actions
│   │   │       │   └── help.tsx
│   │   │       └── help.tsx
│   ├── (main)/
│   │   └── layout.tsx                           # MODIFY: read tenant context, apply branding (logo, accent), render suspension banner
│   └── (auth)/
│       ├── login/page.tsx                       # MODIFY: tenant-aware branding
│       └── setup/page.tsx                       # NEW: first-admin onboarding landing page
├── components/features/admin/
│   ├── TenantList.tsx                           # NEW
│   ├── TenantDetailPanel.tsx                    # NEW
│   ├── TenantProvisionForm.tsx                  # NEW
│   ├── TenantStatusBadge.tsx                    # NEW
│   ├── TenantBrandingPreview.tsx                # NEW
│   └── DeletionGracePeriodCountdown.tsx         # NEW
├── components/features/shell/
│   ├── TenantBrandingProvider.tsx               # NEW: reads tenant from server-injected context
│   └── SuspensionBanner.tsx                     # NEW
└── lib/hooks/
    ├── use-admin-tenants.ts                     # NEW: TanStack Query hooks for /api/v1/admin/tenants/*
    ├── use-tenant-context.ts                    # NEW: hook reading tenant context injected by SSR
    └── use-tenant-mutations.ts                  # NEW: provision / suspend / reactivate / schedule-delete / cancel-delete

deploy/helm/
├── platform/values.yaml                         # MODIFY: add `tenancy.*` block; remove `platformTenantMode` if present
└── observability/templates/dashboards/
    └── tenants.yaml                             # NEW: Grafana dashboard ConfigMap (audit-pass rule 24)

deploy/runbooks/
└── tenant-provisioning.md                       # NEW: operator runbook for provisioning, suspension, deletion, rollback

.github/workflows/
└── ci.yml                                       # MODIFY: add `lint:rls-coverage`, `lint:tenant-filter-static-analysis`, `lint:platform-staff-role-scope` jobs
```

**Structure Decision**: Web-application layout per the existing repository — `apps/control-plane/` (Python modular monolith) plus `apps/web/` (Next.js). New `tenants/` bounded context follows the standard BC layout established in CLAUDE.md (`models.py`, `service.py`, `repository.py`, `router.py`, `admin_router.py`, etc.). Migrations are sequential Alembic Python files (096→102). RLS is the defense-in-depth substrate; explicit application-level filtering is the primary mechanism. Hostname resolver is registered LAST in `create_app()` because Starlette executes registered middleware in reverse-registration order (last-added runs first); the existing eight middleware get pushed back, with the resolver becoming the outermost layer.

## Phased Execution Plan

This feature is large enough that the speckit two-phase model (Phase 0 research, Phase 1 design) is supplemented with the user-provided seven-track build plan. Phases 0 and 1 produce the artifacts under `specs/096-tenant-architecture/`; the build phases (Track A through Track G) are scheduled in `tasks.md` by `/speckit-tasks`.

### Phase 0 — Outline & Research

Output: `research.md` resolves outstanding decisions:

- RLS performance at scale (best practices for index design, `current_setting`-based policies, query plan stability).
- Stripe-style staged-rollout pattern for `PLATFORM_TENANT_ENFORCEMENT_LEVEL` (lenient violations log to a side table; promotion criterion is "zero violations for 7 days").
- Default-tenant UUID immutability strategy (DB-level + application-level guards; constitutional rule SaaS-9).
- Hostname resolver cache invalidation (write-through on tenant attribute changes; opportunistic re-fetch on suspended/active flip).
- Hetzner DNS API contract (record types A + AAAA + cert-manager DNS-01 challenge support).
- Audit chain hash semantics under additive `tenant_id` column (chain remains valid through migration; verification tooling notes appended to runbook).
- Vault path migration: dual-read window strategy (one week) and the regex update pattern.
- Cross-tenant 404 byte-identity strategy (constant-time response generator; identical headers / body / shape regardless of unresolved hostname).

### Phase 1 — Design & Contracts

Outputs:

- `data-model.md` — `Tenant` entity, `TenantBrandingConfiguration` JSONB shape, audit chain entry shape with `tenant_id`, the canonical catalogue of ~40 tenant-scoped tables across the 35 BCs identified (workspaces, users in `accounts`, agents/agent_revisions/capabilities in `registry`, executions in `execution`, audit chain in `audit`, costs in `cost_governance`, conversations in `interactions`, goals in `workspaces`, fleets, governance, secrets refs in `auth`, policies, contracts in `policies`, etc.).
- `contracts/` — REST contracts for `/api/v1/me/tenant` (introspection), `/api/v1/admin/tenants/*` (super admin), `/api/v1/platform/tenants/*` (platform staff). Kafka event envelope for `tenants.lifecycle.*` topic. JWT additive claim spec (`tenant_id`, `tenant_slug`, `tenant_kind`).
- `quickstart.md` — local-dev walkthrough (kind cluster) for: provisioning a tenant, hitting it on `acme.localtest.me`, validating RLS by attempting cross-tenant access, suspending and reactivating.
- Update agent context file (`CLAUDE.md`) with a pointer to this plan between `<!-- SPECKIT START -->` and `<!-- SPECKIT END -->` markers.

### Phase 2 — Tasks

`/speckit-tasks` reads this plan and the artifacts under `specs/096-tenant-architecture/` and produces `tasks.md` ordered by the seven build tracks below.

### Build Tracks (executed after `/speckit-tasks`)

- **Track A — Schema migration + tenants BC core** (3 days, 1 engineer). Migrations 096→101 with checkpoint table for the backfill. Tenants BC skeleton (`models.py`, `service.py`, `repository.py`, `seeder.py`, `vault_paths.py`, `events.py`, `exceptions.py`).
- **Track B — Hostname middleware + request context propagation** (2 days, 1 engineer). `TenantResolverMiddleware`, `tenant_context.py` ContextVar, SQLAlchemy `before_cursor_execute` listener for `SET LOCAL app.tenant_id`, segregated `musematic_platform_staff` async engine + dedicated session factory. Wire into `main.py`. Unit + integration tests.
- **Track C — Bounded-context refactor** (5 days, 2–3 engineers in parallel by BC). Add explicit `tenant_id` filtering to every existing repository query path. Add `tenant_id` to every Kafka event envelope. Update Pydantic response schemas (admin/platform endpoints expose `tenant_id`; regular endpoints omit it). Canonical catalogue in `data-model.md`. CI static-analysis rules for tenant-filter coverage and RLS-policy presence.
- **Track D — Vault path scoping** (1 day, 1 engineer). Update `CANONICAL_SECRET_PATH_RE` to accept the new tenant-scoped pattern alongside the legacy pattern (dual-read window). Author migration utility under `apps/ops-cli/` to move existing secrets to default-tenant paths. Update Vault policies for tenant-scoped read/write.
- **Track E — OAuth per-tenant** (1.5 days, 1 engineer). Migration 102 adds `oauth_providers.tenant_id` + composite uniqueness `(tenant_id, provider_type)` with default-tenant backfill. Update `auth/service.py` to resolve OAuth config from request tenant. Per-tenant OAuth admin page extension. Backward-compat redirect from old global callback URL to tenant-scoped one.
- **Track F — Admin tenants page activation** (1.5 days, 1 engineer). Replace the stub `apps/web/app/(admin)/admin/tenants/page.tsx` with real list + provisioning form + detail panel + suspension/deletion flows. DPA upload to S3 bucket `tenant-dpas` (Vault-stored encryption key for envelope encryption per principle XVI). Wire to `TenantsService.provision_enterprise_tenant()`.
- **Track G — Observability + E2E rollout** (2 days). Grafana dashboard ConfigMap. E2E suite under `tests/e2e/suites/tenant_architecture/`. Journeys J22 (provisioning), J31 (cross-tenant isolation), J36 (default-tenant constraints). Lenient-mode soak (1 week) with violation telemetry; flip to strict.

## Risk Posture

Risks tracked in `spec.md` Background and `research.md`. Mitigations:

| Risk | Mitigation |
|---|---|
| Migration data loss | Migration tests load realistic audit-pass fixtures; full DB snapshot before upgrade; reversible migrations 098→101 with reverse path tested in CI; checkpoint table makes resume safe. |
| RLS query overhead | Per-table `tenant_id` index (migration 099); query plans reviewed; benchmark suite runs before/after with documented thresholds. |
| Missed `tenant_id` filter | RLS catches; CI static analysis rejects pull requests; integration tests with deliberate cross-tenant probes (User Story 3) verify. |
| OAuth callback URL change | Documentation in `deploy/runbooks/tenant-provisioning.md`; backward-compat redirect from `app.musematic.ai/auth/oauth/{provider}/callback` to default-tenant scope works as before; Enterprise tenants register new apps as part of onboarding (FR-006, FR-007). |
| Vault path migration interrupted | Dual-read pattern (try new path, fall back to legacy) for one week, then remove fallback in a follow-up patch; KV-v2 versioning preserves history. |
| Hostname middleware bug | Extensive unit + integration tests; staged deployment with `PLATFORM_TENANT_ENFORCEMENT_LEVEL=lenient` initially; resolver health metrics on Grafana dashboard. |
| RLS policy gap on a future new table | Audit-pass rule 24 already mandates BC dashboards; new CI rule (FR-040) blocks PRs that introduce a tenant-scoped table without an RLS policy. |
| Default-tenant accidental destruction | DB unique partial index `tenants_one_default ON tenants (kind) WHERE kind='default'`; trigger refuses delete/rename of `kind='default'`; application service rejects; integration test User Story 8 validates. |

## Complexity Tracking

> No constitutional violations. The Complexity Tracking table is intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | — | — |
