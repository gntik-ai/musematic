# Phase 0 — Research and Design Decisions

**Feature**: UPD-046 — Tenant Architecture
**Date**: 2026-05-01

This document resolves the open technical questions identified during planning. Each entry follows the format: **Decision** / **Rationale** / **Alternatives considered**.

## R1 — Default-tenant identity strategy

**Decision**: The default tenant has the hardcoded UUID `00000000-0000-0000-0000-000000000001`, slug `default`, subdomain `app`, and is seeded by Alembic migration 096 (idempotent `INSERT … ON CONFLICT DO NOTHING`). The seeder is also called from `main.py` startup to make local-dev databases self-heal.

**Rationale**: A well-known UUID lets every backfill statement reference the default tenant without a lookup; it also lets tests assert default-tenant membership without first querying the table. Seeding from both Alembic and startup makes upgrades and fresh installs converge to the same state. The hardcoded UUID is constitutional (SaaS-9, SaaS-20).

**Alternatives considered**: (a) generated UUID looked up by slug in a CTE within each backfill statement — slower, more failure modes, not testable without a DB round-trip; (b) seed only at install — fails for ephemeral local-dev databases.

## R2 — Migration shape and ordering

**Decision**: Six migrations 096→101, each focused on a single phase so that if any phase fails the rollback path is short:

- **096** — `tenants` table, default-tenant seed, reserved-slug trigger, DPA-metadata columns.
- **097** — Add `tenant_id UUID NULL` to every tenant-scoped table identified in `data-model.md`. Each table is its own batch in a checkpoint table (`_alembic_tenant_backfill_checkpoint`) so a re-run skips already-completed batches.
- **098** — Backfill `tenant_id = '00000000-0000-0000-0000-000000000001'` per table, using a single `UPDATE` per table within a transaction, marking the checkpoint table after each. Statement-batched for tables with > 1M rows.
- **099** — `ALTER TABLE … ALTER COLUMN tenant_id SET NOT NULL` and create per-table indexes `<table>_tenant_id_idx`.
- **100** — `ENABLE ROW LEVEL SECURITY` and `CREATE POLICY tenant_isolation` on every tenant-scoped table.
- **101** — `CREATE ROLE musematic_platform_staff` with `BYPASSRLS`. Grant on all relevant tables. The application's regular role does NOT have `BYPASSRLS`.
- **102** — Carrier for the OAuth-provider tenant-scoping change (Track E); kept separate so Track A is fully reversible without touching identity tables.

**Rationale**: Splitting reduces blast radius and makes rollback granular. The checkpoint table gives idempotent resume after any interruption per FR-028. Per-table indexing in 099 isolates the index-creation cost from the backfill cost. RLS policies in 100 are the last-required step before the application can run in strict mode.

**Alternatives considered**: (a) one giant migration — fails the constitutional requirement "every change is an Alembic migration" only nominally and is much harder to roll back; (b) per-table migrations — too many files (~40), no savings since RLS policies must wait for `NOT NULL`.

## R3 — RLS policy shape

**Decision**: A single `CREATE POLICY tenant_isolation ON <table> USING (tenant_id = current_setting('app.tenant_id', true)::uuid)` per tenant-scoped table. The `true` second argument to `current_setting` returns NULL if the GUC is unset, and `tenant_id = NULL` evaluates to `unknown` so the policy returns zero rows — exactly the defense-in-depth posture FR-020 requires. The `app.tenant_id` GUC is set per-transaction by the `before_cursor_execute` SQLAlchemy event listener: `SET LOCAL app.tenant_id = '<uuid>'`.

**Rationale**: PostgreSQL `current_setting('name', true)` is the documented missing-OK path; using `SET LOCAL` ties the GUC lifetime to the transaction, which matches the request-transaction lifetime in our async SQLAlchemy session pattern. The `::uuid` cast forces the policy planner to use the per-table `tenant_id` index.

**Alternatives considered**: (a) parameterised policy with `WITH CHECK` for write operations — adds complexity; for now, `USING` covers reads and the application enforces tenant_id on writes as a separate rule (Track C). (b) a single shared policy applied per role — PostgreSQL doesn't allow policy sharing across tables.

## R4 — `BYPASSRLS` role segregation

**Decision**: Two separate async SQLAlchemy engines — `regular_engine` (role `musematic_app`, no `BYPASSRLS`) and `platform_staff_engine` (role `musematic_platform_staff`, `BYPASSRLS`). Two corresponding async session factories. A FastAPI dependency `get_platform_staff_session()` returns sessions from the privileged engine; it is only used in routers under `/api/v1/platform/*`. CI rule blocks any other reference.

**Rationale**: PostgreSQL `BYPASSRLS` is a role attribute, so segregation is at the connection level. Connection-pool segregation prevents an accidental code path from upgrading its privileges by mistake. Using a separate engine + dependency makes the audit-pass rule 30 (admin endpoint role-gate) trivially extensible to platform-staff-role-gate (a new CI rule, FR-042).

**Alternatives considered**: (a) one engine with `SET ROLE` per request — easy to forget; (b) one engine that bypasses RLS via `SET LOCAL ROW_SECURITY = off` — undermines the defense-in-depth principle by relying on application code rather than a role attribute.

## R5 — Hostname resolver caching strategy

**Decision**: A two-tier cache. **Tier 1**: process-local LRU (`functools.lru_cache` with TTL via `cachetools.TTLCache`, max 1024 entries, TTL 60s). **Tier 2**: Redis with key pattern `tenants:resolve:{normalized_host}` and TTL 60s. Both tiers are populated on a successful lookup. On any tenant attribute mutation (suspend, reactivate, schedule-delete, cancel-delete, branding update, delete-complete), the service publishes a Kafka event on `tenants.lifecycle.*` and writes a Redis pub/sub invalidation message; receivers evict the matching Tier 1 entry. The Tier 2 cache invalidation is a `DEL` on the affected key.

**Rationale**: The two-tier shape gives sub-millisecond lookups for the hot path while keeping cross-instance consistency under tenant-attribute changes. The 60s TTL is short enough that even without invalidation a stale entry self-heals in under a minute. Redis pub/sub on top of TTL gives near-instant invalidation when needed.

**Alternatives considered**: (a) Redis-only — adds a network hop on every request; (b) process-local-only — drift between instances; (c) push-based invalidation only — fragile under instance churn.

## R6 — Cross-tenant 404 byte-identity

**Decision**: A constant body builder `tenant_not_found_response()` returns the same bytes regardless of input host. The body is `{"detail": "Not Found"}` (matching FastAPI default), the headers are `Content-Type: application/json`, `Content-Length: <fixed>`, and no `Set-Cookie`. No `X-Request-ID` echo for unresolved hosts. The response is built once at module import and reused. The middleware uses `asyncio.sleep(0)` to add a small jittering latency floor of ~1ms that smooths timing differences between cache-hit, cache-miss, and unknown-host code paths.

**Rationale**: Byte-identity prevents content-based enumeration; latency floor prevents timing-based enumeration. SC-009 requires "byte-identical … timing variance below the documented enumeration-protection threshold". `asyncio.sleep(0)` is intentional minimal jitter; an actual jitter generator (e.g., `random.uniform(0, 1)` ms) is added in lenient mode and removed if benchmarks show no measurable difference.

**Alternatives considered**: (a) include the host in the response body — leaks; (b) different status codes for known-but-suspended vs unknown — leaks; (c) response-cache the negative result — deferred until after lenient soak shows whether unknown-host probing is a real volume problem.

## R7 — Audit chain `tenant_id` semantics

**Decision**: `AuditChainEntry.tenant_id UUID NULL` column added in migration 097 (alongside the other `tenant_id` columns), backfilled to default tenant in migration 098, and made `NOT NULL` in 099. The canonical-payload hashing function in `audit/service.py:_canonical_hash()` is updated to include `tenant_id` in the hashed bytes. Existing entries from before the migration retain their original hash chain; the migration creates a single "schema-version-boundary" entry whose `previous_hash` is the last v1 entry's hash and whose `tenant_id` is the default tenant — this anchors the new sub-chain. Verification tooling for v1 chains continues to work for entries up to the boundary; entries from the boundary forward use the new hashing function.

**Rationale**: The constitutional Sync Impact Report flags this as a backward-incompatible change to chain verification tooling. The schema-version-boundary entry preserves continuity (no gap in the chain) while making the format change explicit and verifiable. Operators upgrading their offline verification tools have a concrete inflection point.

**Alternatives considered**: (a) tenant_id column without changing the hash — breaks the constitutional requirement that audit chain entries include tenant_id in the chain hash (Critical Reminder); (b) re-hash all v1 entries with synthetic default-tenant inclusion — invalidates existing exported attestations.

## R8 — Vault path migration window

**Decision**: A two-week dual-read window. During the window, `secret_provider.py` accepts both the legacy regex `^secret/data/musematic/(production|...)/(oauth|...)/...$` and the new tenant-scoped regex `^secret/data/musematic/(production|...)/tenants/(default|<slug>)/(oauth|...)/...$`. Reads first try the new path; if not found, fall back to the legacy path. Writes go only to the new path. A migration utility (Alembic post-deploy step or CLI command under `apps/ops-cli/secrets-migrate.sh`) walks every legacy key and copies it to its new tenant-scoped path. After two weeks, a follow-up patch removes the legacy regex and fallback.

**Rationale**: Two weeks gives operators time to verify the migration utility ran cleanly and to address any edge-case secrets. The dual-read pattern means a partial run never leaves any code path without secrets — old paths stay readable until removed.

**Alternatives considered**: (a) immediate cutover — too risky; (b) leave legacy paths forever — violates SaaS-35 and creates two parallel naming schemes.

## R9 — OAuth backward compatibility for the default tenant

**Decision**: Migration 102 backfills `oauth_providers.tenant_id = default tenant UUID` for all existing rows and changes the unique constraint from `(provider_type)` to `(tenant_id, provider_type)`. The OAuth callback router resolves the provider from `(request.state.tenant.id, provider_type)`. Existing globally-registered OAuth applications continue to work for the default tenant. Enterprise tenants register their own OAuth applications during onboarding and configure them through the per-tenant OAuth admin page.

**Rationale**: Default-tenant OAuth keeps working without operator intervention. Enterprise OAuth is a deliberate onboarding step (FR-005, FR-007). The composite uniqueness lets multiple tenants use the same provider type with different client IDs.

**Alternatives considered**: (a) keep `provider_type` unique and store tenant scope in a separate join table — adds complexity for no benefit; (b) allow `tenant_id` NULL meaning "all tenants" — violates SaaS-36 (per-tenant SSO).

## R10 — `PLATFORM_TENANT_ENFORCEMENT_LEVEL` rollout flag

**Decision**: A new Pydantic setting `PLATFORM_TENANT_ENFORCEMENT_LEVEL: Literal['lenient', 'strict']` defaulting to `lenient` in non-production profiles and `strict` in production. In lenient mode, the `before_cursor_execute` listener still sets `app.tenant_id` but tags any RLS-violation event (caught via PostgreSQL log capture or by an explicit sentinel query) to a side table `tenant_enforcement_violations` and emits a warning structured log. In strict mode, the side table is not consulted; RLS-induced empty results return 404 to the client unchanged. The promotion criterion documented in `deploy/runbooks/tenant-provisioning.md` is: "zero violations in `tenant_enforcement_violations` for seven consecutive days under production traffic; then change `PLATFORM_TENANT_ENFORCEMENT_LEVEL=strict`".

**Rationale**: Constitutional rule Brownfield-8 requires feature flags for behaviour-changing rollouts. The lenient/strict pair is a standard staged-rollout shape: visible diagnostics first, hard enforcement second. The side table makes "did we miss any unfiltered query path" auditable.

**Alternatives considered**: (a) skip lenient and go directly to strict — too risky given that Track C touches every BC; (b) three levels (off / lenient / strict) — "off" would let RLS be disabled, which is a constitutional violation.

## R11 — Hetzner DNS API contract

**Decision**: A thin client `tenants/dns_automation.py` calling the Hetzner DNS API endpoints `POST /api/v1/records` for A and AAAA records. The client is interface-driven (`DnsAutomationClient` Protocol); the production implementation talks to Hetzner; the dev/test implementation is a mock that returns success and emits a structured log. The client is invoked from `TenantsService.provision_enterprise_tenant()` after the database row is committed and before the first-admin invitation is sent. UPD-053 owns the operational details (cluster annotations, IPv4/IPv6 dual-record creation, retry policy under DNS API rate limits) — for UPD-046, the contract is "given a slug, ensure DNS records exist within five minutes; raise a typed error if not".

**Rationale**: Decoupling lets UPD-046 land before UPD-053 ships its full Hetzner integration. The Protocol-based interface lets every other test path inject a mock without monkey-patching.

**Alternatives considered**: (a) inline the Hetzner client in `service.py` — couples UPD-046 to UPD-053; (b) call DNS automation from a Kafka consumer — adds an unnecessary async hop and complicates the five-minute SLA.

## R12 — Tenant-deletion grace period and rollback window

**Decision**: Both are configurable. The default tenant-deletion grace period is **72 hours** (operator can change via `TENANT_DELETION_GRACE_HOURS`). The default migration rollback window is **24 hours** (operator can change via `TENANT_MIGRATION_ROLLBACK_WINDOW_HOURS`). Both are documented in the upgrade and tenant-lifecycle runbooks. `tenants.scheduled_deletion_at` records the deletion target time; the scheduler invokes the cascade exactly once at or after that time.

**Rationale**: The spec deliberately left these configurable per the assumption section. 72 hours is a reasonable default for "operator review and accidental-action recovery" — long enough that a weekend doesn't expire a Friday-morning deletion, short enough that an aggrieved customer's data is removed promptly. 24 hours for migration rollback aligns with typical staged-deployment validation windows.

**Alternatives considered**: (a) hardcode the values — inflexible; (b) one configurable, the other hardcoded — inconsistent.

## R13 — Frontend tenant-context injection

**Decision**: The Next.js admin/main shell reads the tenant context from a server component that calls `/api/v1/me/tenant` during SSR. The result is passed via `TenantBrandingProvider` (a client-side React context provider) to every descendant. The provider exposes `useTenantContext()` returning `{ id, slug, displayName, kind, branding, status }`. Suspended tenants render `<SuspensionBanner />` at the top of the shell; deleted tenants would have already 404'd in middleware so the frontend never sees them.

**Rationale**: SSR injection avoids a client-side flash-of-default-branding. Read-only `/api/v1/me/tenant` keeps the contract narrow. Reuses the existing TanStack Query + React Hook Form stack — no new packages.

**Alternatives considered**: (a) read tenant from a hidden meta tag injected by the API gateway — couples the gateway to UI internals; (b) client-side fetch then re-render — flash-of-default-branding visible on every page load.

## Summary of decisions

All resolved. Zero `NEEDS CLARIFICATION` markers remain. The plan can proceed to Phase 1 (data model, contracts, quickstart).
