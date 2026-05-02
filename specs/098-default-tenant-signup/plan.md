# Implementation Plan: UPD-048 — Public Signup at Default Tenant Only

**Branch**: `098-default-tenant-signup` | **Date**: 2026-05-02 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/098-default-tenant-signup/spec.md`

## Summary

UPD-048 makes the audit-pass signup surface tenant-aware. Most of UPD-037's plumbing (verification, anti-enumeration, OAuth, password rules) is preserved unchanged; the work adds (a) a hostname-kind gate on `/api/v1/accounts/register` so non-default tenants get the canonical opaque 404, (b) post-verification auto-creation of a Free workspace and Free subscription, (c) an Enterprise tenant first-admin `/setup` flow with mandatory MFA, (d) a cross-tenant `/me/memberships` introspection endpoint, (e) an onboarding wizard with persisted state, and (f) a tenant switcher in the main shell when the user holds 2+ memberships. Wave 23, after UPD-046 (tenants + RLS) and UPD-047 (subscriptions). Estimated 4 engineering days; ~2–3 wall-clock days with two engineers.

The work is mostly UI on top of proven backend. The two greenfield primitives are (1) the `OnboardingWizardState` table and service, (2) the cross-tenant memberships introspection (which needs the platform-staff DB session because users are tenant-scoped per UPD-046's RLS posture).

## Technical Context

**Language/Version**: Python 3.12+ (control plane), TypeScript 5.x strict (Next.js admin + workspace UIs).
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, asyncpg, redis-py 5.x async, aiokafka 0.11+, TanStack Query v5 + React Hook Form + Zod, qrcode.react (already in repo for MFA enrolment), Playwright. **No new packages**.
**Storage**: PostgreSQL 16 — one new table (`user_onboarding_states`) and one new table (`tenant_first_admin_invitations`) for the Enterprise `/setup` token. Both tenant-scoped per UPD-046 conventions (`tenant_id NOT NULL`, RLS policy, `tenant_id` index). Redis — one new key family `tenant_first_admin_invite:{token_hash}` for fast token lookup with TTL matching the invitation lifetime. No new buckets, no new Vault paths.
**Testing**: pytest + pytest-asyncio 8.x, Playwright (signup + setup + wizard E2E), the existing `tests/e2e/` harness for the `signup_default_only` suite.
**Target Platform**: Linux containers on Kubernetes (the same Hetzner Cloud cluster topology established by UPD-046 / UPD-053).
**Project Type**: Web application — Python control plane (`apps/control-plane/`) + Next.js frontend (`apps/web/`).
**Performance Goals**: Signup-to-working-workspace latency < 2 minutes p95 (SC-001), first-admin invitation delivery < 5 minutes p95 (SC-003), tenant switcher click latency < 3 seconds (SC-005). Auto-creation Free workspace deferred-retry budget under 30 seconds p95.
**Constraints**: Constitutional rule SaaS-3 (tenants are not self-serve), SaaS-19 (opaque 404 on unknown / non-eligible tenant kinds — preserves UPD-046 SC-009), SaaS-37 (cookies subdomain-scoped — sessions never cross tenants), MFA mandatory on the tenant-admin role within `/setup`. The cross-tenant `/me/memberships` endpoint MUST use `BYPASSRLS` (platform-staff session) because users are tenant-scoped per UPD-046; the endpoint MUST hide tenants the user does not belong to (no tenant-existence leak).
**Scale/Scope**: 6 user stories (4 P1 + 1 P2 + 1 P3), 33 functional requirements, 10 success criteria. Two greenfield tables, three new endpoints, six new frontend pages, one new shell component (tenant switcher).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The constitution at v2.0.0 governs this work. This plan complies with each applicable rule:

| Rule | Application in this plan |
|---|---|
| Brownfield-1 (never rewrite) | All work extends existing files (`accounts/router.py`, `accounts/service.py`, `workspaces/service.py`, `auth/mfa.py`, `me/router.py`, `(auth)/signup/page.tsx`, `(main)/layout.tsx`). Two greenfield modules (`accounts/onboarding.py`, `accounts/first_admin_invite.py`). |
| Brownfield-2 (every change is an Alembic migration) | Two additive migrations (106 for `user_onboarding_states`, 107 for `tenant_first_admin_invitations`). |
| Brownfield-3 (preserve existing tests) | Existing pytest + E2E suites continue to pass; UPD-037 J19 New User Signup journey is extended with a default-tenant assertion, not rewritten. |
| Brownfield-7 (backward-compatible APIs) | All new endpoints, columns, and event types are additive. The signup endpoint's tenant-kind gate is a new check; the existing 202 anti-enumeration response is preserved unchanged when the gate passes. |
| SaaS-3 (tenants are not self-serve) | Default-tenant signup creates a *user within the default tenant*, NOT a new tenant. Enterprise tenants are provisioned by super admin (UPD-046); first admins are invited (this feature). |
| SaaS-19 / UPD-046 SC-009 (opaque 404) | The signup-gate refusal at non-default tenants reuses UPD-046's `_build_opaque_404_response()` helper; the response is byte-identical to the unknown-host 404. |
| SaaS-36 (per-tenant SSO) | OAuth signup uses the existing `OAuthProvider.tenant_id` scoping (UPD-046 migration 102); the signup page surfaces only providers configured for the resolved tenant. |
| SaaS-37 (cookies subdomain-scoped) | Already enforced by UPD-046 cookie-domain configuration; this feature adds no cross-subdomain cookie. The tenant switcher is a redirect, not a session swap. |
| Constitutional Critical Reminder (audit chain entries include `tenant_id`) | Every new lifecycle event (`accounts.signup.completed`, `accounts.first_admin_invitation.issued`, `accounts.setup.step_completed`, `accounts.cross_tenant_invitation.accepted`, `accounts.onboarding.dismissed`) emits an audit-chain entry tagged with the relevant tenant identifier. |
| Audit-pass rule 9 (every PII operation → audit chain) | Signup completion, MFA enrolment in `/setup`, cross-tenant invitation acceptance, and membership-introspection accesses are all auditable. |
| Audit-pass rule 25 (every new BC gets E2E + journey) | This feature does NOT add a new bounded context — it extends `accounts/`. The E2E suite `signup_default_only/` extends J19 (UPD-037) and adds fresh suites for the Enterprise `/setup` and cross-tenant invitation paths. J24 Enterprise Tenant Provisioning lands in UPD-054. |

**Result**: PASS. No violations. The Complexity Tracking section is intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/098-default-tenant-signup/
├── plan.md              # This file
├── spec.md              # Feature spec
├── research.md          # Phase 0 — resolved decisions
├── data-model.md        # Phase 1 — new tables, schema changes
├── quickstart.md        # Phase 1 — local-dev validation walkthrough
├── contracts/           # Phase 1 — REST + Kafka contract specs
│   ├── signup-gate.md
│   ├── enterprise-setup-rest.md
│   ├── memberships-rest.md
│   ├── onboarding-wizard-rest.md
│   └── signup-events-kafka.md
├── checklists/
│   └── requirements.md  # Spec quality checklist (already present)
└── tasks.md             # Phase 2 — generated by /speckit-tasks (NOT created by this command)
```

### Source Code (repository root)

```text
apps/control-plane/
├── src/platform/
│   ├── accounts/
│   │   ├── router.py                            # MODIFY: add tenant-kind gate at register/verify-email/resend handlers
│   │   ├── service.py                           # MODIFY: AccountsService.register() rejects non-default; verify_email() calls workspace auto-create + Free subscription provisioning
│   │   ├── models.py                            # MODIFY: add `TenantFirstAdminInvitation` model (separate table for the /setup token + setup-step state)
│   │   ├── first_admin_invite.py                # NEW: TenantFirstAdminInviteService (issue, resend, validate, consume)
│   │   ├── onboarding.py                        # NEW: OnboardingWizardService (state persistence, step transitions)
│   │   ├── memberships.py                       # NEW: MembershipsService (cross-tenant lookup using platform-staff session)
│   │   ├── setup_router.py                      # NEW: /api/v1/setup/* (token-gated tenant-admin onboarding)
│   │   ├── onboarding_router.py                 # NEW: /api/v1/onboarding/* (wizard state)
│   │   └── memberships_router.py                # NEW: /api/v1/me/memberships (mounts under existing /me prefix)
│   ├── workspaces/
│   │   └── service.py                           # MODIFY: WorkspacesService.create_default_workspace() (already exists at line 153–185) is invoked from the verify-email completion path; emit a `billing.subscription.created` outbox event so UPD-047's SubscriptionService.provision_for_default_workspace runs
│   ├── auth/
│   │   ├── mfa.py                               # NO CHANGE — existing TOTP + recovery code flow is reused
│   │   └── service.py                           # MODIFY: add `assert_role_mfa_requirement(role, user)` helper used by /setup to refuse skip
│   ├── billing/
│   │   └── subscriptions/service.py             # NO CHANGE — UPD-047 owns SubscriptionService.provision_for_default_workspace; this feature calls into it
│   ├── tenants/
│   │   └── service.py                           # MODIFY: TenantsService.provision_enterprise_tenant() now also calls TenantFirstAdminInviteService.issue() to create the /setup token + send the invitation
│   └── me/
│       └── router.py                            # MODIFY: register memberships_router under /api/v1/me prefix
└── migrations/versions/
    ├── 106_user_onboarding_states.py            # NEW: user_onboarding_states table (tenant-scoped, RLS)
    └── 107_tenant_first_admin_invitations.py    # NEW: tenant_first_admin_invitations table (tenant-scoped, RLS) + audit chain entry types
└── tests/
    ├── unit/accounts/
    │   ├── test_signup_tenant_gate.py
    │   ├── test_first_admin_invite.py
    │   ├── test_onboarding_state.py
    │   └── test_memberships_resolver.py
    ├── integration/accounts/
    │   ├── test_signup_at_default_succeeds.py
    │   ├── test_signup_at_enterprise_subdomain_404.py
    │   ├── test_free_workspace_auto_created.py
    │   ├── test_free_workspace_deferred_retry.py
    │   ├── test_setup_flow_mandatory_mfa.py
    │   ├── test_setup_token_lifecycle.py
    │   ├── test_cross_tenant_invitation.py
    │   └── test_me_memberships_endpoint.py
    └── e2e/suites/signup_default_only/
        ├── test_signup_at_default.py            # extends J19
        ├── test_signup_at_enterprise_404.py
        ├── test_onboarding_wizard.py
        ├── test_tenant_admin_setup.py
        ├── test_cross_tenant_invitation.py
        ├── test_me_memberships.py
        └── test_tenant_switcher.py

apps/web/
├── app/
│   ├── (auth)/
│   │   ├── signup/
│   │   │   └── page.tsx                          # MODIFY: tenant-kind gate via useTenantContext (404 page if not default)
│   │   ├── setup/
│   │   │   └── page.tsx                          # NEW: Enterprise tenant first-admin wizard
│   │   ├── verify-email/                         # MODIFY: post-verification redirect to /onboarding instead of /dashboard
│   │   └── accept-invite/
│   │       └── page.tsx                          # MODIFY: handle cross-tenant invite case (FR-018, FR-019)
│   ├── (main)/
│   │   ├── layout.tsx                            # MODIFY: render TenantSwitcher when memberships count >= 2
│   │   ├── onboarding/
│   │   │   └── page.tsx                          # NEW: post-signup wizard
│   │   └── settings/
│   │       └── onboarding/page.tsx               # NEW: re-launch wizard from settings (per FR-030)
│   └── (main)/me/
│       └── memberships/
│           └── page.tsx                          # NEW: list of tenants the user belongs to
├── components/features/auth/
│   ├── SignupForm.tsx                            # NO CHANGE — preserved from UPD-037
│   ├── TenantSetupWizard.tsx                     # NEW: 6-step Enterprise admin wizard (TOS, password/OAuth, MFA, workspace, invitations, done)
│   ├── MandatoryMfaStep.tsx                      # NEW: refuses to advance without verified TOTP
│   └── CrossTenantInvitationAccept.tsx           # NEW: handles invite acceptance for already-existing-in-default-tenant users
├── components/features/onboarding/
│   ├── OnboardingWizard.tsx                      # NEW: 4-step wizard (workspace name, invitations, first agent, tour)
│   ├── OnboardingStepWorkspaceName.tsx           # NEW
│   ├── OnboardingStepInvitations.tsx             # NEW (uses existing UPD-042 invitation form)
│   ├── OnboardingStepFirstAgent.tsx              # NEW (delegates to UPD-022 agent-create wizard)
│   └── OnboardingStepTour.tsx                    # NEW (interactive product tour)
├── components/features/shell/
│   ├── TenantBrandingProvider.tsx                # NO CHANGE — already in place from UPD-046
│   └── TenantSwitcher.tsx                        # NEW: renders only when memberships.length >= 2
└── lib/hooks/
    ├── use-onboarding.ts                         # NEW: TanStack Query for /api/v1/onboarding/state, mutations for advance / dismiss / restart
    ├── use-tenant-setup.ts                       # NEW: TanStack Query for /api/v1/setup/* (token-gated)
    └── use-memberships.ts                        # NEW: TanStack Query for /api/v1/me/memberships

deploy/helm/
└── platform/values.yaml                          # MODIFY: add `signup.*` block (autoCreateRetrySeconds, firstAdminInviteTtlDays, onboardingWizardEnabled)

deploy/runbooks/
└── tenant-first-admin-onboarding.md              # NEW: operator runbook (resending invitations, troubleshooting MFA enrolment, cross-tenant invitation acceptance, deferred-retry diagnostics)

.github/workflows/
└── ci.yml                                        # MODIFY: add `lint:signup-tenant-gate` (verifies the gate is invoked at every signup-adjacent endpoint) job
```

**Structure Decision**: Web-application layout. The `accounts/` bounded context is extended (no new BC introduced — this feature ships under the existing accounts BC because it modifies signup, invitation, and onboarding flows that already live there). Two new tables (`user_onboarding_states`, `tenant_first_admin_invitations`) are tenant-scoped under UPD-046 conventions; both get RLS policies via Alembic migrations 106 and 107. The cross-tenant `/me/memberships` endpoint is the only path that bypasses tenant RLS — it uses the platform-staff session per UPD-046 conventions and surfaces only the authenticated user's own memberships (no tenant-existence leak per FR-022).

## Phased Execution Plan

The user's three-phase build plan (backend additions, frontend pages, E2E) is preserved. Phases 0 and 1 produce the artifacts under `specs/098-default-tenant-signup/`; the build phases run after `/speckit-tasks`.

### Phase 0 — Outline & Research

Output: `research.md` resolves outstanding decisions:

- Free-workspace auto-creation strategy (synchronous in verify-email transaction vs deferred-retry vs Kafka-driven outbox).
- Cross-tenant memberships lookup mechanism (email-as-correlator with platform-staff query vs new shared-identity table).
- First-admin invitation token model (reuse `Invitation` model with `kind` discriminator vs separate `tenant_first_admin_invitations` table).
- MFA-mandatory-for-tenant-admin enforcement strategy (server-side guard vs role-based middleware vs setup-wizard-step refusal).
- Onboarding wizard state model (per-user record with step-by-step JSON vs explicit step columns vs Redis-backed).
- Default workspace name template (per-user display name vs configurable template vs literal).
- Tenant switcher placement (sidebar vs header vs profile-menu).
- Resend-invitation behaviour: invalidate prior token immediately vs grace-period overlap.

### Phase 1 — Design & Contracts

Outputs:

- `data-model.md` — `UserOnboardingState`, `TenantFirstAdminInvitation`, the `MembershipListing` projection (read-only), state machines for the onboarding wizard and the first-admin invitation lifecycle.
- `contracts/` — REST contracts for the signup-gate behaviour, the Enterprise `/setup` token-gated endpoints, `/api/v1/me/memberships`, the onboarding wizard state endpoints. Kafka envelopes for the new event types on `accounts.events` (additive; the topic already exists).
- `quickstart.md` — local-dev walkthrough (kind cluster) for: default-tenant signup → verification → workspace auto-create → wizard; Enterprise subdomain signup attempt → 404; first-admin invitation flow at `/setup`; cross-tenant invitation acceptance; multi-tenant switcher.
- Update agent context file (`CLAUDE.md`) with a pointer to this plan.

### Phase 2 — Tasks

`/speckit-tasks` reads this plan and the artifacts and produces `tasks.md` ordered by the three build phases below.

### Build Phases (executed after `/speckit-tasks`)

- **Phase A — Backend additions** (1.5 days, 1 engineer). Migrations 106 + 107. Tenant-kind gate on `accounts/router.py`. `AccountsService.verify_email()` post-verification hook calling `WorkspacesService.create_default_workspace()` (already exists) + `SubscriptionService.provision_for_default_workspace()`. `OnboardingWizardService` + `MembershipsService` + `TenantFirstAdminInviteService` + `/api/v1/setup` endpoints + `/api/v1/me/memberships` + `/api/v1/onboarding/state`. MFA-mandatory guard for the tenant-admin role within `/setup`. Audit-chain entries on every new lifecycle event.
- **Phase B — Frontend pages** (1.5 days, 1 engineer). `(auth)/signup/page.tsx` tenant-kind gate. `(auth)/setup/page.tsx` for Enterprise wizard. `(main)/onboarding/page.tsx` for default-tenant wizard. `(main)/me/memberships/page.tsx`. `TenantSwitcher` component in `(main)/layout.tsx`. `(main)/settings/onboarding/page.tsx` for wizard re-launch. Localization (per audit-pass rule 38 — UPD-083 locale parity).
- **Phase C — E2E + observability** (1 day, 1 engineer). E2E suite under `tests/e2e/suites/signup_default_only/`. Extend J19. New journey suites for cross-tenant invitation, tenant-admin setup, multi-tenant switcher. Operator runbook. Optional: small Grafana panel addition to the existing accounts dashboard (not a new dashboard since this isn't a new BC).

## Risk Posture

Risks tracked in `spec.md` and `research.md`. Mitigations:

| Risk | Mitigation |
|---|---|
| Free-workspace auto-creation race | Idempotent on `(user_id, is_default=true)` via partial unique index; second concurrent call returns the existing workspace. |
| Auto-creation transient failure | Deferred-retry job (APScheduler) checks for verified users without a default workspace and creates one within the documented latency budget; a "Setting up your workspace" UI splash covers the gap. |
| Onboarding state lost on session expiry | State persisted in PostgreSQL `user_onboarding_states`, not session memory; survives logout / login. |
| First-admin invitation leaked | Single-use, time-bounded, hashed-only-stored. Resend invalidates the prior token. |
| MFA enrolment skipped via API rather than UI | Server-side guard `assert_role_mfa_requirement('tenant_admin', user)` invoked on every `/setup` step beyond the MFA step; refuses to advance without verified TOTP. |
| Cross-tenant memberships endpoint leaks tenant existence | The endpoint returns ONLY tenants the authenticated user belongs to; never an "exists but you don't have access" disclosure. Implemented via email-correlator query that filters before returning. |
| Tenant switcher usability when user has 1 membership | Switcher hidden when count < 2 (FR-023). |
| Default tenant happens to be unreachable | Spec edge case (`Default tenant disabled (impossible per FR-705)`). The signup page surfaces an explanatory error, not the opaque 404. |

## Complexity Tracking

> No constitutional violations. The Complexity Tracking table is intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | — | — |
