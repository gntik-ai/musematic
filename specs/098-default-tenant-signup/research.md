# Phase 0 — Research and Design Decisions

**Feature**: UPD-048 — Public Signup at Default Tenant Only
**Date**: 2026-05-02

This document resolves the open technical questions identified during planning. Each entry follows the format: **Decision** / **Rationale** / **Alternatives considered**.

## R1 — Free-workspace auto-creation strategy

**Decision**: Synchronous in the `verify_email` transaction with a deferred-retry safety net. Specifically: `AccountsService.verify_email()` calls `WorkspacesService.create_default_workspace(user_id)` (the method already exists at `apps/control-plane/src/platform/workspaces/service.py:153–185`) and then `SubscriptionService.provision_for_default_workspace(workspace_id)` (UPD-047) before returning the verification success. If either call fails, the verification still rolls forward (the user is verified) and a deferred-retry APScheduler job picks up "verified users without a default workspace" within the tolerance window (default 30 seconds, configurable via `signup.autoCreateRetrySeconds`).

**Rationale**: Synchronous-first means 99%+ of users land directly on a working workspace, hitting the SC-001 budget in a single round-trip. The deferred-retry job is the fallback for transient DB / Redis failures — it ensures eventual consistency without blocking verification on a downstream service that the user doesn't even know about. The "Setting up your workspace" UI splash covers the gap for the 1% that hit the deferred path.

**Alternatives considered**: (a) **Pure deferred** — adds latency on every signup; the user sees the splash even on the happy path. (b) **Pure synchronous, fail signup if workspace fails** — couples the user-facing signup flow to a downstream service that is not actually critical for verification; a transient SubscriptionService outage would block all signups. (c) **Kafka-driven outbox after verification** — increases latency and adds complexity for no benefit; the synchronous-with-fallback shape is simpler and has the same eventual-consistency guarantee.

## R2 — Cross-tenant memberships lookup mechanism

**Decision**: Email-as-correlator query against the platform-staff session (`BYPASSRLS` per UPD-046). The `MembershipsService.list_for_user(user)` method runs `SELECT users.tenant_id, tenants.slug, tenants.display_name, tenants.kind, … FROM users JOIN tenants ON users.tenant_id = tenants.id WHERE users.email = :email AND users.status = 'active'` against the platform-staff engine. The endpoint then filters server-side: if the authenticated user's tenant is one of the returned rows (always true for a signed-in user), every other returned row is also exposed (because by definition the authenticated user holds those memberships); rows where the user holds no membership are not returned by the JOIN.

**Rationale**: Users are tenant-scoped by UPD-046's RLS posture — the only way to query across tenants is the platform-staff session. Email-as-correlator is the canonical join key per spec FR-022. Constraining the query at the SQL level (`WHERE users.email = :authenticated_user_email`) keeps the result set pre-filtered: the endpoint never sees a tenant the user does not belong to, eliminating the leak risk by construction. No new shared-identity table is needed.

**Alternatives considered**: (a) **New global `user_identity` table** — adds a denormalisation that needs to be kept in sync with the per-tenant user records; introduces failure modes that don't exist in the join-based approach. (b) **Tenant-scan via Redis index** — viable but less correct under tenant-creation race conditions; the JOIN reads the source of truth. (c) **Expose `MembershipsService` only to authenticated users** (which we still do at the router layer) — already in place; this entry concerns the lookup mechanism, not the authorization gate.

## R3 — First-admin invitation token model

**Decision**: A separate `tenant_first_admin_invitations` table rather than reusing the existing `Invitation` model with a `kind` discriminator. The new table carries fields that don't apply to workspace invitations (`tenant_id`, `setup_step_state`, `mfa_required`, `prior_token_invalidated_at` for resend tracking) and avoids polluting the workspace-invitation table with optional fields that are only meaningful for first-admin invites.

**Rationale**: First-admin invitations have a different lifecycle from workspace invitations (single-use, longer TTL, drives a multi-step `/setup` flow rather than a direct accept-and-go acceptance). Separating the table keeps the `Invitation` model focused on its current shape and keeps the new state cleanly isolated. Both tables share the same `token_hash`-based lookup pattern so the validation logic stays consistent.

**Alternatives considered**: (a) **Reuse `Invitation` with `kind='tenant_first_admin'`** — saves one table but couples two distinct lifecycles; resend semantics, audit-chain shape, and the setup-step state JSON would all need to be conditional on `kind`. (b) **Polymorphic table with discriminator** — same complexity as (a) without the simplicity benefit. The clean separation is worth one extra migration.

## R4 — MFA-mandatory-for-tenant-admin enforcement

**Decision**: A server-side guard `auth_service.assert_role_mfa_requirement(role, user)` is invoked at every `/api/v1/setup/step/*` endpoint that follows the MFA step. The guard raises `MfaEnrollmentRequiredError` (mapped to HTTP 403) if the user does not hold a verified `MfaEnrollment` row. The frontend's `MandatoryMfaStep` component refuses to advance to the next step's API call without local verification of the TOTP code, but the server-side guard is the source of truth — a malicious client cannot skip the step by calling later endpoints directly.

**Rationale**: Constitutional requirement. The wizard step is UX; the server-side guard is enforcement. Tested per SC-004 by an automated probe that attempts every "skip" / "next" endpoint from the MFA step.

**Alternatives considered**: (a) **Role-based middleware** — too coarse: would need to know which paths are MFA-required; the per-endpoint guard is more localized and explicit. (b) **Frontend-only refusal** — fails security review; client-side gates are not enforcement.

## R5 — Onboarding wizard state model

**Decision**: One `user_onboarding_states` row per user, carrying explicit step-completion booleans (`step_workspace_named`, `step_invitations_sent_or_skipped`, `step_first_agent_created_or_skipped`, `step_tour_started_or_skipped`) plus a `dismissed_at` timestamp and a `last_step_attempted` enum for resume position. State persisted in PostgreSQL.

**Rationale**: Explicit columns are easier to query for analytics ("how many users skipped step 3?") and don't drift across schema versions like a JSON blob would. The row is small (one per user) and read-mostly. PostgreSQL gives us the standard CRUD path without introducing a Redis-state-loss failure mode.

**Alternatives considered**: (a) **Single JSON column for step state** — flexible but harder to query; analytics would need JSON path expressions. (b) **Redis-backed** — fails the FR-031 requirement (state persists across reloads) under Redis eviction; PostgreSQL is durable. (c) **Implicit state derived from other tables** ("did the user create a workspace?") — fails for steps that may be skipped vs not-yet-attempted (e.g., "invitations skipped" vs "invitations not yet seen").

## R6 — Default workspace name template

**Decision**: The default workspace name follows the template `"{display_name}'s workspace"` where `display_name` comes from the user's profile (or the email local-part if no display name is set). The user may rename the workspace at the wizard's first step. The template lives in the platform settings as `signup.defaultWorkspaceNameTemplate` so operators can adapt the wording without a code change.

**Rationale**: A per-user template gives a friendly default that almost always doesn't need editing. Making it configurable lets operators localise or brand the wording without code changes.

**Alternatives considered**: (a) **Literal "My Workspace"** — bland and confusing for users with multiple workspaces over time. (b) **Force user to choose during the wizard with no default** — adds friction for users who just want to start.

## R7 — Tenant switcher placement

**Decision**: The tenant switcher renders in the main shell's header, immediately to the right of the platform logo. It is hidden entirely when the authenticated user has fewer than 2 memberships (FR-023). The component uses a shadcn/ui `DropdownMenu` listing each tenant's display name and the user's role within that tenant, marking the current tenant with a visible indicator.

**Rationale**: Header placement is discoverable for users who have multiple memberships and invisible for users who don't. Reusing shadcn/ui keeps the visual language consistent with the rest of the platform per CLAUDE.md.

**Alternatives considered**: (a) **Sidebar bottom** — buried; users wouldn't find it without prompting. (b) **Profile menu** — discoverable but conflates "who am I?" with "where am I?" — the tenant context is more relevant to the latter. (c) **Always-visible regardless of membership count** — adds clutter for the 99% of users with one tenant.

## R8 — Resend-invitation behaviour

**Decision**: Resend invalidates the prior token immediately. Specifically: when super admin clicks "Resend invitation" on `/admin/tenants/{id}`, the platform sets `tenant_first_admin_invitations.prior_token_invalidated_at = now()` on the existing row, then creates a new row with a fresh token. Any attempt to use the prior token after resend produces the standard "expired" surface (FR-016, SC-009).

**Rationale**: Single-token-at-a-time is the safest model for a single-use, role-elevation invitation. A grace-period overlap would let two parallel tokens coexist; in practice the only time both could be used is if the original recipient discovered the link and acted on it after the resend, which is exactly the scenario the resend is meant to render irrelevant. Immediate invalidation is the cleanest semantics.

**Alternatives considered**: (a) **Grace-period overlap (e.g., 1 hour)** — usability win for the rare case the original was about to be clicked; security loss for the unusual case the original was leaked. The security trade-off favours immediate invalidation. (b) **Both tokens valid until the first one is consumed** — loses the audit-trail clarity the spec demands; the resend would not produce a clear inflection point.

## R9 — Subdomain matching for the signup gate

**Decision**: The signup gate at `/api/v1/accounts/register` (and `/verify-email`, `/resend-verification`) reads `request.state.tenant.kind` (set by UPD-046's hostname middleware). If `kind != 'default'`, the endpoint returns the canonical opaque 404 by calling UPD-046's `_build_opaque_404_response()` helper. The frontend page mirrors this: `(auth)/signup/page.tsx` uses `useTenantContext().kind` to decide whether to render the form or trigger Next.js `notFound()`.

**Rationale**: Reusing UPD-046's helper produces byte-identical 404 responses (per spec FR-008 and constitutional rule SaaS-19). The frontend Next.js `notFound()` matches the backend's response shape so the user experience is consistent regardless of whether they hit the page or the API directly.

**Alternatives considered**: (a) **Custom 404 page for "signup disabled"** — leaks the policy and the tenant's existence; rejected by FR-008. (b) **Server-side redirect to a public marketing page** — also leaks; same rejection. (c) **Reuse UPD-046 helper, no special handling** — chosen.

## R10 — Cross-tenant invitation acceptance authentication

**Decision**: When Juan accepts an invitation to Acme via `acme.musematic.ai/accept-invite?token=…`, the acceptance flow first checks whether Juan already has a user record in the Acme tenant. If yes (re-invite or already-accepted), the flow signs Juan into Acme using Acme's identity provider (refusing to let an active default-tenant cookie cross subdomains per FR-019). If no (fresh acceptance), the flow creates a new Acme-scoped user record with its own credentials, MFA state, and roles, then prompts Juan to authenticate against Acme's identity provider before completing acceptance.

**Rationale**: Per spec User Story 4 — "Cross-tenant invite creates a NEW `user_memberships` row in Acme for Juan" — and constitutional rule SaaS-37 (cookies subdomain-scoped). Acme's identity provider may differ from default's per SaaS-36; the acceptance flow respects the tenant's configured provider. The independent credential row is the constitutional model.

**Alternatives considered**: (a) **Single shared identity record across tenants with per-tenant role assignments** — fundamentally incompatible with UPD-046's RLS posture; rejected. (b) **Auto-link Juan's default-tenant credentials into Acme** — violates constitutional independence of per-tenant identity stores; introduces a session-crossing risk.

## R11 — Onboarding wizard step deletion when underlying feature is missing

**Decision**: The wizard's step 3 (first agent creation) is hidden cleanly when UPD-022 (the agent-creation wizard) is not deployed. Detection happens client-side via a feature-flag check exposed by `/api/v1/me/feature-flags` (existing UPD-014 endpoint); when the flag is absent or false, the step is removed from the wizard's step array before rendering.

**Rationale**: Per spec edge case "Wizard step depending on UPD-022 (agent creation) is unavailable in a deployment that has not landed UPD-022 — the wizard's step 3 hides cleanly without breaking the rest of the flow". The feature-flag-based detection is the simplest non-coupling between UPD-048 and UPD-022.

**Alternatives considered**: (a) **Hard-code the dependency, fail if UPD-022 missing** — fragile; rejected. (b) **Render step 3 with a "feature unavailable" message** — adds noise; the hide-cleanly approach is cleaner.

## Summary of decisions

All resolved. Zero `NEEDS CLARIFICATION` markers remain. The plan can proceed to Phase 1 (data model, contracts, quickstart).
