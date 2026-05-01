# Feature Specification: UPD-046 — Tenant Architecture (Subdomain + RLS + Default-Plus-Enterprise)

**Feature Branch**: `096-tenant-architecture`
**Created**: 2026-05-01
**Status**: Draft
**Input**: User description: "UPD-046 — Tenant Architecture (Subdomain + RLS + Default-Plus-Enterprise) — foundational refactor of the SaaS pass; introduces Tenant as a first-class isolation primitive identified by subdomain, default-tenant-plus-enterprise model, defense-in-depth row-level isolation, per-tenant secrets/OAuth/cookies/branding, and migration of all existing data into the default tenant. FR-685 through FR-705."

## Background and Motivation

The platform was built as a self-hosted enterprise platform with workspaces as the unit of isolation and a single-tenant deployment posture. The SaaS transformation (constitution v2.0.0) requires a tenant primitive that separates customers at a higher level than workspaces, identified by subdomain and isolated end-to-end across the data, identity, secrets, branding, and cookie layers. UPD-046 establishes that primitive. Every subsequent SaaS-pass feature (subscriptions, billing, abuse prevention, Hetzner topology, cross-tenant E2E) depends on it.

Two tenant kinds exist by constitutional rule SaaS-2: exactly one **`default`** tenant (the public SaaS surface at `app.musematic.ai` where Free and Pro users live) and zero or more **`enterprise`** tenants (one per contracted customer, manually provisioned by super admin). No tenant kind besides those two exists, no self-serve tenant creation exists, and the default tenant cannot be deleted, renamed, or disabled.

Because the existing platform is single-tenant in practice, this feature MUST migrate every existing row across roughly forty tenant-scoped tables into the default tenant, add a `tenant_id` first-class dimension, and enforce isolation through database-level row-level security so a single missed `tenant_id` filter in application code cannot leak data across tenants.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Super admin provisions a new Enterprise tenant (Priority: P1)

After the commercial team closes a deal with Acme Corp, super admin manually provisions Acme's tenant from the admin workbench. Within five minutes, Acme's subdomain is live with valid TLS, the first tenant admin has received an invitation, and the tenant admin can sign in.

**Why this priority**: Without operational tenant provisioning, the SaaS pass cannot onboard any paying Enterprise customer. This is the gating capability for every subsequent SaaS feature.

**Independent Test**: Authenticated as super admin at `app.musematic.ai/admin/tenants/new`, fill the form (slug `acme`, display name "Acme Corp", region `eu-central`, plan kind `enterprise`, uploaded DPA PDF, first admin email `cto@acme.com`). Submit. Within five minutes, navigate to `acme.musematic.ai`; the page loads with valid TLS and Acme's branding. The mailbox at `cto@acme.com` has received an invitation email. The invite link lands at `acme.musematic.ai/setup` and the tenant admin can complete first sign-in.

**Acceptance Scenarios**:

1. **Given** super admin is authenticated and on `/admin/tenants/new`, **When** the form is submitted with a valid unique slug and a DPA file, **Then** a tenant row is created with status `active`, the DPA file hash and version are recorded, an audit chain entry tags the super admin principal and the new tenant_id, and the tenant appears at the top of `/admin/tenants`.
2. **Given** a newly created tenant with subdomain `acme`, **When** the provisioning workflow runs, **Then** DNS records are created via the Hetzner DNS API, the wildcard TLS certificate covers the subdomain (no per-tenant cert issuance is required), and the subdomain becomes reachable within the SLA.
3. **Given** the new tenant has been provisioned, **When** the system delivers the first-admin invitation through the existing notification channels, **Then** the recipient receives a tenant-specific invite link that — when clicked — lands them at `acme.musematic.ai/setup` and binds the new user record to the Acme tenant.
4. **Given** super admin attempts to provision a tenant with slug `app`, `api`, `grafana`, `status`, `www`, `admin`, `platform`, `webhooks`, `public`, `docs`, or `help`, **When** the form is submitted, **Then** validation rejects with a reserved-slug error and no tenant row is created.

---

### User Story 2 — Existing data migrates to the default tenant on upgrade (Priority: P1)

Operators upgrading from the audit-pass version expect every existing workspace, agent, execution, audit-chain entry, and cost record to remain intact after the upgrade. The upgrade migration creates the default tenant, backfills `tenant_id` into every tenant-scoped row, and enables row-level isolation without data loss.

**Why this priority**: A migration that loses or corrupts existing data blocks the entire upgrade. This is the absolute precondition for any operator running the new platform version.

**Independent Test**: Snapshot a database loaded with realistic audit-pass production data (multiple workspaces, agents, executions, audit-chain entries, cost attributions, OAuth clients, secret refs). Apply the upgrade migration. Verify (a) the default tenant row exists with the well-known UUID, (b) every tenant-scoped table has a `NOT NULL tenant_id` column whose value is the default tenant's UUID for every pre-existing row, (c) every existing query path continues to return the same results for existing users, (d) row-level isolation policies are active on every tenant-scoped table, (e) the migration reverse path returns the database to its pre-upgrade state if invoked within the rollback window.

**Acceptance Scenarios**:

1. **Given** a database with the audit-pass schema and realistic data, **When** the upgrade migration runs to completion, **Then** the `tenants` table exists, the default tenant row has the well-known identifier and is the unique tenant of kind `default`, and every existing row in every tenant-scoped table has been backfilled with the default tenant's identifier.
2. **Given** the migration runs and is interrupted partway through (operator kills the process, the database connection drops, the cluster restarts), **When** the migration is re-invoked, **Then** it resumes from the last completed checkpoint, never double-applies a step, and converges to the same end state as an uninterrupted run.
3. **Given** the migration has completed, **When** a regular application connection executes a query against a tenant-scoped table without setting the per-request tenant identifier, **Then** the row-level isolation policy returns zero rows (defense-in-depth backstop).
4. **Given** the migration has completed within the configured rollback window, **When** an operator invokes the reverse migration, **Then** the database returns to its pre-upgrade state without data loss.

---

### User Story 3 — Cross-tenant access attempts are opaquely refused (Priority: P1)

A user belonging to tenant Acme attempts to fetch a workspace that exists in tenant Globex (whether by guessed identifier, leaked link, or compromised client). The platform refuses with HTTP 404, leaks no information about whether the target exists, and avoids creating audit log spam from probing.

**Why this priority**: Cross-tenant data leakage is the existential security failure for a multi-tenant SaaS. The platform must refuse correctly even if application code has a bug.

**Independent Test**: Provision two tenants (Acme, Globex), each with a workspace. Authenticate as a user in tenant Acme. Issue `GET /api/v1/workspaces/<globex-workspace-id>` against `acme.musematic.ai`. Expect HTTP 404 with a generic body. Verify the database session ran with the per-request tenant identifier bound to Acme, the row-level policy filtered the row out, and no audit chain entry was emitted for the failed probe. Repeat with the same identifier against the platform-staff endpoint `/api/v1/platform/workspaces/<globex-workspace-id>` while authenticated as platform staff: the response succeeds (privileged role bypasses RLS).

**Acceptance Scenarios**:

1. **Given** a user authenticated in tenant A, **When** the user requests a resource identifier belonging to tenant B, **Then** the response is HTTP 404 with a generic message, no row is returned by the row-level policy, and no audit chain entry is created for the probe.
2. **Given** a developer writes new application code that queries a tenant-scoped table without an explicit `tenant_id` filter, **When** the code runs in any environment, **Then** the row-level policy returns only the current tenant's rows; the missing application filter does NOT leak data.
3. **Given** platform-staff personnel need to debug across tenants, **When** they invoke endpoints under `/api/v1/platform/*`, **Then** the privileged database role bypasses row-level isolation and returns rows from any tenant; no other code path may use the privileged role.

---

### User Story 4 — Hostname resolves to the correct tenant before any other middleware (Priority: P1)

Every HTTP request entering the platform is mapped to a tenant by the `Host` header before any database query, before any auth check, before any business logic. The mapping is fast (cache-backed) and complete (no request runs without a resolved tenant).

**Why this priority**: Hostname-to-tenant resolution is a constitutional ordering invariant (SaaS-10). Every other request-time guarantee — RLS binding, branding, cookies, OAuth callbacks — depends on the tenant being known first.

**Independent Test**: Issue requests with `Host: app.musematic.ai`, `Host: acme.musematic.ai`, `Host: acme.api.musematic.ai`, and `Host: acme.grafana.musematic.ai` against a single platform deployment. Each request lands in the correct tenant context as verified by an internal `/api/v1/me/tenant` introspection endpoint. Repeated requests from the same hostname use a cached lookup (verified by cache-hit metrics).

**Acceptance Scenarios**:

1. **Given** the request `Host` header is `app.musematic.ai`, **When** the request enters the pipeline, **Then** the default tenant is resolved, attached to the request context, and bound to the database session; the page renders with default Musematic branding; cookies issued by the response are scoped to `app.musematic.ai`.
2. **Given** the request `Host` header is `acme.musematic.ai`, **When** the request enters the pipeline, **Then** the Acme tenant is resolved, the Acme branding configuration is loaded, the login form accepts only users with membership in tenant Acme, and cookies issued by the response are scoped to `acme.musematic.ai`.
3. **Given** repeated requests from the same hostname within the cache window, **When** they hit the resolution middleware, **Then** the tenant lookup is served from cache (no database query); cache invalidation propagates within the cache TTL after a tenant attribute is changed.
4. **Given** the request `Host` header includes a leading port or upper-case characters, **When** the resolver normalizes it, **Then** the same tenant is resolved as for the canonical lower-case host.

---

### User Story 5 — Per-tenant branding renders on tenant-scoped pages (Priority: P1)

Pages served from `acme.musematic.ai` render with Acme's brand configuration (logo, accent colors, display name). The default tenant retains the default Musematic visual identity. Branding is loaded from the tenant record, never hardcoded per-page.

**Why this priority**: Enterprise tenants require visible distinction so their users do not feel like they are using a generic third-party tool. This is part of the Pro→Enterprise upgrade differentiator (constitutional principle SaaS-14).

**Independent Test**: Provision tenant Acme with a non-default branding payload (custom logo URL, custom primary color). Navigate to `acme.musematic.ai/login` and `acme.musematic.ai/setup`. Verify the rendered logo, accent color, and display name match the tenant configuration. Navigate to `app.musematic.ai/login` and verify the default Musematic branding still renders.

**Acceptance Scenarios**:

1. **Given** an Enterprise tenant has a non-empty branding configuration, **When** any tenant-scoped page is rendered for that tenant, **Then** the configured logo, accent color, and display name are applied; pages without explicit branding overrides fall back to the default Musematic visual identity in a deterministic and documented way.
2. **Given** the default tenant has no custom branding (always), **When** any page on `app.musematic.ai` is rendered, **Then** it shows the default Musematic visual identity.
3. **Given** super admin updates a tenant's branding configuration, **When** the change is saved, **Then** users of that tenant see the new branding within the cache TTL without needing to clear browser state.

---

### User Story 6 — Unknown subdomain returns an opaque 404 (Priority: P2)

A request to a hostname that does not match any provisioned tenant subdomain returns HTTP 404 with a generic body. The response leaks no information about which subdomains exist, which tenants are provisioned, or whether the platform is reachable.

**Why this priority**: Probing for tenant slugs is a reconnaissance vector; an opaque 404 closes it. P2 because it is a hardening property rather than a gating capability.

**Independent Test**: Issue requests with `Host: bogus.musematic.ai`, `Host: xyz123.musematic.ai`, and `Host: tenant-that-was-deleted.musematic.ai`. Each returns HTTP 404 with the same generic body. Compare response bodies and headers — they are byte-identical (no per-host variance that would enable timing or content-based enumeration).

**Acceptance Scenarios**:

1. **Given** a request with a hostname that does not match any tenant, **When** it reaches the resolution middleware, **Then** the response is HTTP 404 with a generic message and no tenant is created on the fly.
2. **Given** a series of requests probing many candidate slugs, **When** they are issued in rapid succession, **Then** each receives an identical 404 response (no leakage via response shape, response time, or response headers about which slugs are valid versus invalid).

---

### User Story 7 — Tenant suspension is reversible; tenant deletion is not (Priority: P2)

Super admin can suspend a tenant (data preserved, access blocked) and can later reactivate it. Super admin can also schedule a tenant for deletion; deletion is two-phase with a grace period during which it can be reversed, after which it cascades and produces a final tombstone.

**Why this priority**: Necessary for handling overdue Enterprise contracts (suspend), legal/compliance withdrawals (suspend then reactivate), and end-of-contract cleanup (delete). P2 because P1 stories cover the provisioning, isolation, and routing core; this is lifecycle.

**Independent Test**: Suspend tenant Acme. Verify users at `acme.musematic.ai` cannot sign in or reach any resource. Reactivate; users can sign in again with no data loss. Schedule tenant Acme for deletion; verify access is blocked and a deletion countdown is visible in `/admin/tenants`. Cancel deletion before the grace period ends; verify the tenant is reactivated. Re-schedule deletion and let the grace period expire; verify the tenant is permanently removed and a tombstone audit chain entry exists.

**Acceptance Scenarios**:

1. **Given** an active tenant, **When** super admin suspends it, **Then** all interactive access (login, API except platform-staff, agent execution) is blocked and a banner explains the suspension to anyone who reaches the subdomain; data is preserved untouched.
2. **Given** a suspended tenant, **When** super admin reactivates it, **Then** access resumes immediately for all users with no data loss and no requirement for users to re-authenticate beyond their normal session lifecycle.
3. **Given** super admin schedules a tenant for deletion, **When** the grace period is still in effect, **Then** access is blocked and super admin can cancel the deletion to reactivate the tenant.
4. **Given** the grace period for a scheduled deletion has expired, **When** the deletion job runs, **Then** all tenant-scoped data is cascaded out across every owning bounded context, the subdomain is released, and a tombstone audit chain entry records the operation with cryptographic proof of completion.

---

### User Story 8 — Default tenant cannot be deleted, renamed, or disabled (Priority: P2)

Database-level and application-level constraints prevent any operator action that would delete, rename, or disable the default tenant.

**Why this priority**: Constitutional rule SaaS-9. The default tenant is the public SaaS surface where Free and Pro users live; losing it would be catastrophic. P2 because the constraint surfaces as a refusal of an unsafe action rather than as a positive capability.

**Independent Test**: As super admin, attempt to delete the default tenant via UI, attempt to rename its slug or subdomain via the admin API, attempt to suspend it, and attempt the same operations directly through the platform-staff API. Each attempt is refused with a constraint-violation error and no state changes.

**Acceptance Scenarios**:

1. **Given** the default tenant exists, **When** any operator attempts to delete it through any code path, **Then** the operation is refused (database trigger and application validation both reject) and no state changes.
2. **Given** the default tenant exists, **When** any operator attempts to change its `slug`, `subdomain`, or `kind`, **Then** the change is refused with a constraint-violation error.
3. **Given** the platform is freshly installed, **When** the seeder runs, **Then** exactly one tenant of kind `default` is created with the well-known identifier and the canonical `default` slug + `app` subdomain; running the seeder again is a no-op.

---

### Edge Cases

- **Reserved subdomain protection**: an attempt to provision a tenant with slug `app`, `api`, `grafana`, `status`, `www`, `admin`, `platform`, `webhooks`, `public`, `docs`, or `help` is rejected at form validation, at the application service layer, and at the database trigger (defense in depth).
- **Migration interruption mid-upgrade**: the upgrade migration is idempotent and checkpointed; partial state is detectable and recoverable on retry.
- **Existing secrets path migration**: secrets stored at non-tenant-scoped paths under the audit-pass version are moved to default-tenant paths during upgrade; the migration writes the new path, verifies, and only then removes the old path.
- **Existing OAuth provider configuration**: OAuth clients configured globally before the upgrade continue to operate against the default tenant's callback URL after the upgrade; Enterprise tenants must register new OAuth applications against their own callback URLs as part of onboarding.
- **Cookie scope on tenant change**: cookies are scoped per subdomain. A user moved between tenants must re-authenticate at the new subdomain; this is intentional to prevent cross-tenant cookie reuse.
- **First-admin email already exists in default tenant**: when a super admin provisions an Enterprise tenant whose first-admin email collides with an account that already exists in the default tenant, the new tenant gets a fresh user record bound only to the new tenant; the default-tenant account is not affected. The two are independent identities.
- **Concurrent tenant slug claim**: two super admins attempting to provision tenants with the same slug at the same time — exactly one succeeds (database unique constraint) and the other receives a clear conflict error.
- **Tenant resolution under platform-domain itself**: a request to the bare apex (`musematic.ai` with no subdomain) resolves to a deterministic landing page (or default tenant marketing surface) rather than to a tenant — explicit policy, not accidental.
- **CI prevention of new tables without RLS**: any pull request that introduces a tenant-scoped table without a corresponding row-level policy fails CI and cannot merge.
- **CI prevention of unfiltered queries**: static analysis flags any production query against a tenant-scoped table that does not include either an explicit `tenant_id` filter or evidence the query runs through the per-request session binding; offending pull requests fail CI.

## Requirements *(mandatory)*

### Functional Requirements

#### Tenant entity and lifecycle

- **FR-001**: The platform MUST persist a `Tenant` entity with attributes: stable identifier, URL-safe slug, display name, subdomain, kind (`default` or `enterprise`), region, data isolation mode (default `pool`, with `silo` reserved for future per-tenant physical isolation), branding configuration, status (`active`, `suspended`, `pending_deletion`), creation timestamp, creating super-admin reference (nullable for the default tenant), DPA signed-at timestamp and version, contract metadata, and feature flags.
- **FR-002**: The platform MUST enforce that exactly one tenant of kind `default` exists at all times. No code path may create a second default tenant; no code path may delete, rename, change the kind of, or disable the default tenant.
- **FR-003**: The platform MUST enforce a reserved-slug list (`api`, `grafana`, `status`, `www`, `admin`, `platform`, `webhooks`, `public`, `docs`, `help`) at three layers — form validation, application service, and database trigger — for any tenant of kind `enterprise`.
- **FR-004**: The platform MUST enforce slug uniqueness, subdomain uniqueness, and a slug regex that disallows leading or trailing hyphens, requires a leading lowercase letter, and limits length to a documented bound.
- **FR-005**: The platform MUST allow super admin to provision an Enterprise tenant with a single super-admin action that captures slug, display name, region, plan kind, DPA file (with hash and version recorded), and first-tenant-admin email.
- **FR-006**: The platform MUST automate DNS configuration for newly provisioned Enterprise tenant subdomains so the subdomain is reachable (with valid TLS) within five minutes of provisioning. Wildcard TLS coverage is in scope for the platform-domain certificate; no per-tenant certificate issuance is required.
- **FR-007**: The platform MUST send the first-tenant-admin invitation through the existing notification channels (email at minimum) and MUST bind a click-through invite URL to the new tenant subdomain.
- **FR-008**: The platform MUST allow super admin to suspend a tenant; suspension blocks all interactive access to the tenant subdomain (login, regular API, agent execution) while preserving all tenant data unchanged.
- **FR-009**: The platform MUST allow super admin to reactivate a suspended tenant; reactivation restores access without data modification.
- **FR-010**: The platform MUST allow super admin to schedule a tenant for deletion; the operation enters a documented grace period during which access is blocked but data is preserved and the deletion can be cancelled.
- **FR-011**: The platform MUST execute scheduled deletion as a cascading data removal across every owning bounded context after the grace period elapses; the operation MUST emit a final tombstone audit chain entry with cryptographic proof of completion.
- **FR-012**: The platform MUST record a hash-linked audit chain entry tagged with the tenant identifier and the acting super-admin principal for every tenant-lifecycle state change (create, suspend, reactivate, schedule-delete, cancel-delete, delete-complete).

#### Hostname resolution

- **FR-013**: The platform MUST resolve every incoming HTTP request to a tenant by inspecting the `Host` header before any other middleware runs, before any database query, and before any authentication check.
- **FR-014**: The hostname resolver MUST support these patterns: bare-tenant subdomain (`<slug>.<platform-domain>`), tenant-scoped API subdomain (`<slug>.api.<platform-domain>`), tenant-scoped Grafana subdomain (`<slug>.grafana.<platform-domain>`), the default tenant's `app.<platform-domain>`, the default tenant's `api.<platform-domain>`, and the default tenant's `grafana.<platform-domain>`.
- **FR-015**: The hostname resolver MUST normalize the incoming `Host` header (strip port, lower-case) before lookup.
- **FR-016**: The hostname resolver MUST cache successful tenant lookups in a fast-cache layer with a documented TTL, and MUST honor invalidation events when tenant attributes change.
- **FR-017**: The hostname resolver MUST return HTTP 404 with a generic body for any hostname it cannot resolve to a provisioned tenant; the response MUST be byte-identical across different unresolved hostnames so the response cannot be used to enumerate provisioned tenant slugs.
- **FR-018**: The hostname resolver MUST attach the resolved tenant to the request context where downstream code reads it; downstream code MUST NOT re-read the `Host` header.

#### Data isolation

- **FR-019**: The platform MUST add a non-nullable `tenant_id` column to every tenant-scoped table (workspaces, users, agents, agent revisions, executions, audit-chain entries, costs, conversations, goals, fleets, governance chains, secrets references, policies, contracts, and the rest of the audit-pass surface) on upgrade.
- **FR-020**: The platform MUST enable database-level row-level security on every tenant-scoped table such that a session lacking a bound tenant identifier returns zero rows from any select.
- **FR-021**: The platform MUST bind the per-request tenant identifier to the database session for the lifetime of the request transaction so RLS filters every query implicitly.
- **FR-022**: The platform MUST require application code to filter by `tenant_id` explicitly in addition to RLS; RLS is the safety net, not the primary mechanism.
- **FR-023**: The platform MUST provide a privileged database role that bypasses RLS, MUST restrict that role to platform-staff endpoints under `/api/v1/platform/*`, and MUST forbid any other code path from using that role. Connection-pool segregation enforces the restriction.
- **FR-024**: The platform MUST surface cross-tenant resource access attempts as HTTP 404 (not 403) with a generic body so the response does not disclose whether the target exists.
- **FR-025**: The platform MUST NOT emit an audit chain entry for an unsuccessful cross-tenant probe (probes are not auditable events; volume would dominate the chain). Successful platform-staff cross-tenant access IS auditable.

#### Migration and existing-data preservation

- **FR-026**: The upgrade migration MUST create the default tenant with a stable, well-known identifier, the canonical `default` slug, and the canonical `app` subdomain.
- **FR-027**: The upgrade migration MUST backfill `tenant_id` to the default tenant's identifier on every existing row in every tenant-scoped table.
- **FR-028**: The upgrade migration MUST be idempotent and resumable from checkpoints; an interrupted run resumes correctly without data corruption or duplicate work.
- **FR-029**: The upgrade migration MUST produce no data loss; row counts in every tenant-scoped table MUST match pre-upgrade counts after backfill.
- **FR-030**: The upgrade migration MUST be reversible to a pre-upgrade snapshot if invoked within the documented rollback window.
- **FR-031**: The upgrade migration MUST move existing secret references stored at platform-global Vault paths to default-tenant Vault paths using a write-verify-then-delete sequence so a partial run leaves a recoverable state.

#### Per-tenant scoping of identity and secrets

- **FR-032**: The platform MUST scope cookies issued from a tenant subdomain to that subdomain only; cookies MUST NOT span tenants.
- **FR-033**: The platform MUST resolve OAuth callback URLs per tenant — each tenant has its own registered OAuth applications and callback URL pattern under its subdomain.
- **FR-034**: The platform MUST support per-tenant Single Sign-On configuration (provider client identifiers, secrets, scopes, callback paths). Different tenants MAY use different identity providers.
- **FR-035**: The platform MUST scope every Vault secret path that holds tenant-owned material so the path includes the tenant slug.
- **FR-036**: The platform MUST scope every cost attribution record, every audit-chain entry, and every analytics event with `tenant_id` so all downstream chargeback, retention, and forensic flows are per-tenant.

#### Branding and presentation

- **FR-037**: The platform MUST load tenant-specific branding (logo, accent color, display name) from the tenant record and apply it to user-facing pages served from that tenant's subdomain. Pages MUST fall back to default Musematic branding for fields not customized.
- **FR-038**: The platform MUST limit branding customization to tenants of kind `enterprise`; the default tenant always renders the default Musematic visual identity.
- **FR-039**: The platform MUST surface a visible suspension banner on every page served from a suspended tenant subdomain so end users understand why interactive features are blocked.

#### Operator and CI guarantees

- **FR-040**: The repository MUST enforce in CI that any new tenant-scoped table introduced in a pull request includes a row-level isolation policy; a missing policy fails the build.
- **FR-041**: The repository MUST enforce in CI through static analysis that production code does not query a tenant-scoped table without either an explicit `tenant_id` filter or evidence the query runs through the per-request session binding.
- **FR-042**: The repository MUST enforce in CI that the privileged database role is only referenced from code paths under `/api/v1/platform/*`.
- **FR-043**: The platform MUST expose `/admin/tenants` as a fully operational page (no longer feature-flagged behind `PLATFORM_TENANT_MODE=multi`); the page lists tenants, supports provisioning, suspension, reactivation, and scheduling deletion, and is gated on the super-admin role.
- **FR-044**: The platform MUST expose `/api/v1/platform/tenants/*` as platform-staff-only endpoints that operate cross-tenant.

### Key Entities

- **Tenant**: A first-class isolation primitive. Attributes: identifier, slug (URL-safe, unique), display name, subdomain (unique), kind (`default` or `enterprise`), region, data isolation mode, branding configuration, status, created_at, creating super admin (nullable for default), DPA signed_at and version, contract metadata, feature flags. Exactly one tenant of kind `default` exists.
- **Tenant Lifecycle Audit Entry**: A hash-linked audit chain entry recording every state transition (create, suspend, reactivate, schedule-delete, cancel-delete, delete-complete). Tagged with the tenant identifier, the acting super-admin principal, and the operation outcome.
- **Tenant Branding Configuration**: Logo URL, accent color, display name override, and reserved fields for future customization. Empty for the default tenant; populated for Enterprise tenants.
- **Tenant Membership**: An association between a user and a tenant. A user belongs to exactly one tenant; cross-tenant identities are independent records (the same email can exist in multiple tenants as separate users).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Super admin can provision a new Enterprise tenant from the admin workbench and the tenant subdomain becomes reachable with valid TLS and the first-admin invitation delivered within **five minutes** of submission, on at least 95% of attempts under normal operating conditions.
- **SC-002**: After applying the upgrade migration to a database with realistic audit-pass data, **100% of pre-existing rows in every tenant-scoped table** carry the default tenant's identifier; row counts match exactly; no existing user-visible behavior regresses.
- **SC-003**: A penetration test that issues cross-tenant requests against every tenant-scoped read endpoint **never returns data belonging to another tenant** and never produces a response (status code, body, headers, or timing) that distinguishes "resource exists in another tenant" from "resource does not exist anywhere".
- **SC-004**: Static analysis verifies that **every tenant-scoped table has a row-level isolation policy** and that **every production query against a tenant-scoped table** is either explicitly tenant-filtered or runs under the per-request session binding; CI rejects pull requests that violate either rule.
- **SC-005**: 95th-percentile hostname-resolution overhead added by the new middleware is **under 5 milliseconds** when the lookup is cache-resident; under 50 milliseconds when the cache misses.
- **SC-006**: Tenant suspension blocks **100% of interactive access paths** (login, regular API, agent execution, web UI) for the suspended tenant within the cache TTL; reactivation restores access within the same TTL; no data is lost across either transition.
- **SC-007**: After tenant deletion completes, **zero rows reference the deleted tenant identifier** in any tenant-scoped table or in any owning bounded context, and a tombstone audit chain entry attests to the cascade with cryptographic proof.
- **SC-008**: An operator who attempts to delete, rename, or disable the default tenant through any UI, API, CLI, or direct platform-staff endpoint is **always refused** with a clear constraint-violation error and no state change occurs.
- **SC-009**: The unknown-subdomain 404 response is **byte-identical** across at least 100 randomly-selected unresolved hostnames; response timing variance across the sample is below the documented enumeration-protection threshold.
- **SC-010**: Tenant branding renders correctly on at least the login page, the setup page, and the main shell layout for an Enterprise tenant; the default tenant continues to render the default Musematic visual identity unchanged.

## Assumptions

- The platform domain is `musematic.ai` in production and `dev.musematic.ai` in the development cluster; wildcard TLS certificates already cover both.
- DNS automation against the Hetzner DNS API is reachable and credentialed in both production and dev clusters; UPD-053 owns the operational details.
- The audit chain service from UPD-024 already supports an additive `tenant_id` column on its entries; this feature requires the audit service to include `tenant_id` in the chain hash (additive change, documented for downstream verification tooling).
- The notification service from UPD-042 supports the first-admin invitation flow and accepts a tenant subdomain in the invite URL.
- The migration rollback window is bounded; the precise window is configurable per operator and documented in the upgrade runbook.
- The tenant-deletion grace period is configurable per operator with a documented default that allows operator review and accidental-action recovery.
- The number of tenants per platform deployment is bounded by operational practice (small Enterprise customer counts measured in the dozens to hundreds, not thousands), so a process-local plus shared-cache resolver handles the load without sharding.
- Cross-tenant identity (the same email used by different humans in different tenants) is intentionally supported as independent user records; cross-tenant single sign-on is out of scope for this feature.
- The first Enterprise tenants live on `*.musematic.ai`. Custom domains (`agents.acme.com`) are deferred per constitutional rule SaaS-15 and out of scope for this feature.
- This feature owns hostname resolution, the tenant entity, RLS policy creation, and migration backfill. It does NOT own subscription scoping, billing, or per-tenant quota enforcement (UPD-047 and onward).
