---
description: "Task list for UPD-048 — Public Signup at Default Tenant Only"
---

# Tasks: UPD-048 — Public Signup at Default Tenant Only

**Input**: Design documents in `specs/098-default-tenant-signup/`
**Prerequisites**: `plan.md` ✅, `spec.md` ✅, `research.md` ✅, `data-model.md` ✅, `contracts/` ✅, `quickstart.md` ✅
**Branch**: `098-default-tenant-signup`

**Tests**: Tests are included for this feature because (a) the spec lists 10 measurable success criteria covering enumeration-resistance, MFA-mandatory enforcement, idempotent invitation lifecycle, and cross-tenant identity correctness; (b) constitutional rule SaaS-3 (tenants are not self-serve) and SaaS-19 (opaque 404 byte-identity) demand automated verification; (c) the cross-tenant invitation acceptance is the existential security boundary for the multi-tenant identity model.

**Organization**: Tasks are grouped by user story (US1 through US6). User stories US1–US4 are P1 (gating); US5 is P2 (wizard polish); US6 is P3 (multi-tenant switcher). Phase 1 (Setup) and Phase 2 (Foundational) MUST complete before any user-story phase can begin.

## Format: `[TaskID] [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Story label (US1–US6) — required for user-story phases; absent in Setup, Foundational, and Polish

## Path Conventions

- **Backend**: `apps/control-plane/src/platform/<bc>/...`; `apps/control-plane/migrations/versions/...`; `apps/control-plane/tests/{unit,integration,e2e}/...`
- **Frontend**: `apps/web/app/...`; `apps/web/components/...`; `apps/web/lib/hooks/...`; `apps/web/locales/...`
- **Helm/Ops**: `deploy/helm/...`; `deploy/runbooks/...`
- **CI**: `.github/workflows/...`; `apps/control-plane/scripts/lint/...`

## Dependency on Prior Features

UPD-046 (`tenants` architecture, hostname middleware, opaque 404 helper, platform-staff role) and UPD-047 (`SubscriptionService.provision_for_default_workspace`) MUST be live before any task in this list begins. UPD-037 (signup core), UPD-042 (workspace invitations), UPD-014 (MFA enrolment), UPD-016 (`accounts.events` Kafka topic) provide the substrate this feature extends.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configuration plumbing, settings additions, Helm value scaffolding, BC module skeletons.

- [x] T001 Confirm working branch is `098-default-tenant-signup` (`git status` shows clean tree, branch matches) and migrations 096–105 (UPD-046 + UPD-047) are present at `apps/control-plane/migrations/versions/`.
- [x] T002 [P] Add new Pydantic settings to `apps/control-plane/src/platform/common/config.py`: `SIGNUP_AUTO_CREATE_RETRY_SECONDS: int = 30`, `SIGNUP_FIRST_ADMIN_INVITE_TTL_DAYS: int = 7`, `SIGNUP_ONBOARDING_WIZARD_ENABLED: bool = True`, `SIGNUP_DEFAULT_WORKSPACE_NAME_TEMPLATE: str = "{display_name}'s workspace"`. Document each in the docstring with constitutional rule references (SaaS-3, audit-pass rule 38 for the i18n implications of the template).
- [x] T003 [P] Add the `signup:` Helm value block to `deploy/helm/platform/values.yaml` mirroring the new settings. Mirror to `deploy/helm/platform/values.dev.yaml` and `values.prod.yaml`.
- [x] T004 [P] Create empty `apps/control-plane/src/platform/accounts/onboarding.py`, `apps/control-plane/src/platform/accounts/first_admin_invite.py`, `apps/control-plane/src/platform/accounts/memberships.py` so subsequent tasks can target the modules. Each starts with a module docstring referencing the relevant FRs from `specs/098-default-tenant-signup/spec.md`.
- [x] T005 [P] Create empty `apps/control-plane/src/platform/accounts/setup_router.py`, `accounts/onboarding_router.py`, `accounts/memberships_router.py`. Each starts with `router = APIRouter()` and a module docstring.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migrations 106 + 107, the four new service modules' skeletons, audit-chain integration, and the workspace-auto-creation hook into UPD-037's `verify_email`. **All user-story phases depend on this phase being complete.**

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Schema migrations

- [x] T006 Author Alembic migration `apps/control-plane/migrations/versions/106_user_onboarding_states.py`: create `user_onboarding_states` table per `data-model.md` Entity 1 (all columns, UNIQUE on `user_id`, `tenant_id` index, RLS policy `tenant_isolation`); also add the partial unique index `workspaces_user_default_unique ON workspaces (created_by_user_id) WHERE is_default = true` (per `data-model.md` "Modification — Workspace.is_default partial unique index"). Include reverse migration.
- [x] T007 Author Alembic migration `apps/control-plane/migrations/versions/107_tenant_first_admin_invitations.py`: create `tenant_first_admin_invitations` table per `data-model.md` Entity 2 (all columns, UNIQUE on `token_hash`, partial active-invitation index, target_email index, RLS policy). Include reverse migration.

### Service skeletons

- [x] T008 [P] Author the SQLAlchemy `UserOnboardingState` model at `apps/control-plane/src/platform/accounts/models.py` matching the `user_onboarding_states` table per `data-model.md`. Use existing `Base`, `UUIDMixin`, `TimestampMixin` patterns. Add the model alongside existing accounts models (extend the file; do not move existing models).
- [x] T009 [P] Author the SQLAlchemy `TenantFirstAdminInvitation` model at `apps/control-plane/src/platform/accounts/models.py` matching the `tenant_first_admin_invitations` table per `data-model.md`.
- [x] T010 [P] Author Pydantic schemas in `apps/control-plane/src/platform/accounts/schemas.py` (extending the existing file): `OnboardingStateView`, `OnboardingStepWorkspaceName`, `OnboardingStepInvitations`, `OnboardingStepFirstAgent`, `OnboardingStepTour`, `TenantFirstAdminInviteCreate`, `TenantFirstAdminInviteValidationResponse`, `SetupStepTos`, `SetupStepCredentials`, `SetupStepWorkspace`, `MembershipsListResponse`, `MembershipEntry`. Each maps to the contracts under `specs/098-default-tenant-signup/contracts/`.
- [x] T011 [P] Extend `apps/control-plane/src/platform/accounts/exceptions.py` with: `TenantSignupNotAllowedError`, `SetupTokenInvalidError`, `MfaEnrollmentRequiredError`, `OnboardingWizardAlreadyDismissedError`, `CrossTenantInviteAcceptanceError`, `DefaultWorkspaceNotProvisionedError`. Each subclasses `PlatformError` with a stable error code matching `contracts/*-rest.md`.
- [x] T012 [P] Implement `OnboardingWizardService` in `apps/control-plane/src/platform/accounts/onboarding.py` with methods: `get_or_create_state(user_id)`, `advance_step(user_id, step, payload)`, `dismiss(user_id)`, `relaunch(user_id)`, `is_first_agent_step_available()` (reads UPD-022 feature flag from `/api/v1/me/feature-flags`). Each lifecycle action emits the corresponding Kafka event per `contracts/signup-events-kafka.md` and an audit-chain entry.
- [x] T013 [P] Implement `TenantFirstAdminInviteService` in `apps/control-plane/src/platform/accounts/first_admin_invite.py` with methods: `issue(tenant_id, target_email, super_admin_id)` (creates row, sends invitation email via UPD-042 channels, records audit-chain entry, publishes `accounts.first_admin_invitation.issued` Kafka event), `validate(token)` (returns `TenantFirstAdminInviteValidationResponse` or raises `SetupTokenInvalidError`), `consume(token, user_id)`, `resend(invitation_id, super_admin_id)` (sets `prior_token_invalidated_at` on the existing row, calls `issue` for a fresh token, publishes `accounts.first_admin_invitation.resent`).
- [x] T014 Implement `MembershipsService` in `apps/control-plane/src/platform/accounts/memberships.py` with method `list_for_user(authenticated_user) -> list[MembershipEntry]`. Uses `get_platform_staff_session()` per UPD-046 conventions; runs `SELECT users.tenant_id, tenants.slug, tenants.display_name, tenants.kind, memberships.role FROM users JOIN tenants ON users.tenant_id = tenants.id LEFT JOIN memberships ON memberships.user_id = users.id WHERE users.email = :email AND users.status = 'active'`. Filters server-side per research R2.

### MFA-mandatory guard

- [x] T015 [P] Add `assert_role_mfa_requirement(role: str, user: User) -> None` helper to `apps/control-plane/src/platform/auth/service.py`. Raises `MfaEnrollmentRequiredError` (mapped to HTTP 403) if `role == 'tenant_admin'` and the user has no verified `MfaEnrollment` row. Public function used by every `/api/v1/setup/step/*` endpoint past `step/mfa/verify`.

### Workspace auto-creation hook

- [x] T016 Modify `apps/control-plane/src/platform/accounts/service.py:AccountsService.verify_email()` to call `WorkspacesService.create_default_workspace(user_id)` (the method already exists at `workspaces/service.py:153–185`) and then `SubscriptionService.provision_for_default_workspace(workspace_id)` (UPD-047). On exception, the verification still rolls forward (the user is verified) and a deferred-retry job (T017) picks up the gap. Emit `accounts.signup.completed` Kafka event with `workspace_id` and `subscription_id`. Audit-chain entry `accounts.signup.completed`.
- [x] T017 Add APScheduler job `build_workspace_auto_create_retry(app)` in `apps/control-plane/src/platform/accounts/jobs/workspace_auto_create.py` (clones the pattern from `cost_governance/jobs/anomaly_job.py`). Runs every `SIGNUP_AUTO_CREATE_RETRY_SECONDS` (default 30s). Selects users whose state is `active` and who have no default workspace; creates one. Idempotent via the partial unique index added in T006.
- [x] T018 Wire `build_workspace_auto_create_retry` into the `scheduler` runtime profile at `apps/control-plane/src/platform/main.py:create_app()` next to existing scheduler builders.

### Tenants service hook

- [x] T019 Modify `apps/control-plane/src/platform/tenants/service.py:TenantsService.provision_enterprise_tenant()` to call `TenantFirstAdminInviteService.issue(tenant_id, first_admin_email, super_admin_id)` after the tenant row is committed. The first-admin invitation is part of the provisioning workflow, not a separate operator step.
- [x] T020 Add `POST /api/v1/admin/tenants/{id}/resend-first-admin-invitation` endpoint to `apps/control-plane/src/platform/tenants/admin_router.py`. Calls `TenantFirstAdminInviteService.resend(invitation_id, super_admin_id)`. Gated by `require_superadmin`. Records audit-chain entry.

### Foundational tests

- [x] T021 [P] Migration smoke test at `apps/control-plane/tests/integration/migrations/test_106_user_onboarding_states.py`: load fixtures, run migration 106, assert `user_onboarding_states` table exists with RLS policy active and the `workspaces_user_default_unique` partial index created.
- [x] T022 [P] Migration smoke test at `apps/control-plane/tests/integration/migrations/test_107_tenant_first_admin_invitations.py`: run migration 107, assert table + indexes + RLS.
- [x] T023 [P] Unit test `apps/control-plane/tests/unit/accounts/test_onboarding_state.py`: idempotent state creation; step advances are idempotent; dismiss preserves state; relaunch clears `dismissed_at`.
- [x] T024 [P] Unit test `apps/control-plane/tests/unit/accounts/test_first_admin_invite.py`: issue creates row + email; validate happy / expired / consumed paths; resend invalidates prior and creates fresh token; resend records audit-chain entry naming both token IDs.
- [x] T025 [P] Unit test `apps/control-plane/tests/unit/accounts/test_memberships_resolver.py`: 0 / 1 / 3 / 5 membership scenarios; users with the same email but different tenants both see all matching tenants; an isolated user's call returns only their own tenants.

**Checkpoint**: Foundation ready. The two new tables exist; the four service modules are skeletoned; the verify-email path now provisions the default workspace and Free subscription; super admin's `provision_enterprise_tenant` issues the first-admin invitation. User-story phases can now begin.

---

## Phase 3: User Story 1 — Public signup at the default tenant (Priority: P1) 🎯 MVP

**Goal**: A public user signs up at `app.musematic.ai/signup`, verifies their email, and lands on a working Free workspace with the onboarding wizard ready.

**Independent Test**: Per spec User Story 1 — submit signup form at `app.musematic.ai/signup`, verify email, confirm working Free workspace + Free subscription + wizard launch.

### Tests for User Story 1

- [ ] T026 [P] [US1] Integration test `apps/control-plane/tests/integration/accounts/test_signup_at_default_succeeds.py`: full happy path — register, verify, default workspace exists with `is_default=true`, Free subscription provisioned, `accounts.signup.completed` Kafka event published, audit-chain entry recorded.
- [ ] T027 [P] [US1] Integration test `apps/control-plane/tests/integration/accounts/test_free_workspace_auto_created.py`: verify `WorkspacesService.create_default_workspace` is invoked from the verify-email path; the `workspaces_user_default_unique` index makes a second concurrent call return the existing workspace (no duplicates).
- [ ] T028 [P] [US1] Integration test `apps/control-plane/tests/integration/accounts/test_free_workspace_deferred_retry.py`: simulate transient failure of `create_default_workspace` during verify-email; verify the user is still marked verified; the deferred-retry job picks up the gap within `SIGNUP_AUTO_CREATE_RETRY_SECONDS` and creates the workspace.
- [ ] T029 [P] [US1] Integration test `apps/control-plane/tests/integration/accounts/test_signup_oauth_default.py`: OAuth signup at default tenant skips the email-verification step (provider attests), still triggers the workspace auto-creation path.
- [ ] T030 [US1] E2E test `apps/control-plane/tests/e2e/suites/signup_default_only/test_signup_at_default.py`: full browser flow — load `app.localhost:8080/signup`, submit form, verify email via dev SMTP relay, assert redirect to `/onboarding`, assert workspace exists. Extends J19.

### Implementation for User Story 1

- [x] T031 [US1] Modify `apps/control-plane/src/platform/accounts/router.py` to read `request.state.tenant.kind` at the top of `register`, `verify_email`, and `resend_verification` handlers. If `kind != 'default'`, return UPD-046's `_build_opaque_404_response()`. Otherwise proceed with the existing UPD-037 logic.
- [x] T032 [US1] Frontend: modify `apps/web/app/(auth)/signup/page.tsx` to read `useTenantContext().kind` during SSR; if not `'default'`, call Next.js `notFound()`.
- [x] T033 [US1] Frontend: modify `apps/web/app/(auth)/verify-email/page.tsx` to redirect to `/onboarding` (instead of `/dashboard`) on successful verification when the user has no completed onboarding state.
- [x] T034 [US1] [P] Update Helm `signup.*` block to expose `autoCreateRetrySeconds` and the default workspace name template; document defaults in `deploy/runbooks/tenant-first-admin-onboarding.md` (created later in Polish).

**Checkpoint**: User Story 1 fully functional. Default-tenant signup → verification → workspace auto-create works end-to-end. The MVP can be demonstrated.

---

## Phase 4: User Story 2 — Signup at Enterprise subdomain returns opaque 404 (Priority: P1)

**Goal**: Probing `/signup` at any non-default tenant subdomain returns the canonical opaque 404, byte-identical to the unknown-host 404. No information leak about provisioned tenants.

**Independent Test**: Per spec User Story 2 — issue requests with at least 50 candidate hostnames combining real Enterprise tenants and unknown subdomains; assert byte-identical response across all (SC-002).

### Tests for User Story 2

- [ ] T035 [P] [US2] Integration test `apps/control-plane/tests/integration/accounts/test_signup_at_enterprise_subdomain_404.py`: issue 50 candidate signup-adjacent requests at Enterprise subdomains AND at unknown subdomains; assert 100% return byte-identical 404 (body, headers minus per-request request-id) per SC-002.
- [ ] T036 [P] [US2] Integration test `apps/control-plane/tests/integration/accounts/test_signup_gate_no_audit_or_special_log.py`: probe `/signup` at an Enterprise subdomain; assert no audit-chain entry; assert structlog has only the standard request line (no special "signup blocked" tag) per FR-009.
- [ ] T037 [US2] E2E test `apps/control-plane/tests/e2e/suites/signup_default_only/test_signup_at_enterprise_404.py`: browser-level check that `acme.localhost:8080/signup` renders the canonical "Page not found" surface, byte-identical to a navigation to `bogus.localhost:8080/signup`.

### Implementation for User Story 2

- [x] T038 [US2] CI rule `apps/control-plane/scripts/lint/check_signup_tenant_gate.py`: AST-walk `accounts/router.py` and assert that every signup-adjacent endpoint handler invokes the tenant-kind gate before any business logic per `contracts/signup-gate.md`. Wire into `.github/workflows/ci.yml`.
- [x] T039 [US2] Verify the existing UPD-046 `_build_opaque_404_response()` helper is exported from `apps/control-plane/src/platform/common/middleware/tenant_resolver.py` for reuse by the signup router. If not exported, expose it via the module's `__all__`.
- [x] T040 [US2] [P] Frontend: ensure `apps/web/app/(auth)/signup/not-found.tsx` (Next.js convention) renders the canonical 404 surface — no tenant-specific copy, no "signup disabled" wording per FR-008.

**Checkpoint**: User Story 2 fully validated. Enumeration vector closed; no special log entries; CI rule prevents regressions.

---

## Phase 5: User Story 3 — Enterprise tenant first-admin onboarding via `/setup` (Priority: P1)

**Goal**: After tenant provisioning, the first tenant admin completes a hardened multi-step setup flow at `<slug>.musematic.ai/setup` with mandatory MFA enrolment.

**Independent Test**: Per spec User Story 3 — provision Enterprise tenant, receive invitation, walk every step, verify token single-use + expiry + MFA-cannot-be-skipped + audit chain entries per step.

### Tests for User Story 3

- [ ] T041 [P] [US3] Integration test `apps/control-plane/tests/integration/accounts/test_setup_token_lifecycle.py`: happy path validate-token; expired token returns 410; consumed token returns 410; superseded token (post-resend) returns 410 with the same opaque body as expired.
- [ ] T042 [P] [US3] Integration test `apps/control-plane/tests/integration/accounts/test_setup_flow_mandatory_mfa.py`: automated probe — after completing `step/credentials`, attempt every subsequent step's endpoint without first verifying MFA; all return 403 `mfa_enrollment_required`. Verifies SC-004.
- [ ] T043 [P] [US3] Integration test `apps/control-plane/tests/integration/accounts/test_setup_resend.py`: super admin resends; prior token immediately invalidated; new token works; both tokens record audit-chain entries.
- [ ] T044 [P] [US3] Integration test `apps/control-plane/tests/integration/accounts/test_setup_step_persistence.py`: complete steps 1–3, simulate page reload, verify step state persists (`setup_step_state` JSONB) and resume position is correct.
- [ ] T045 [US3] E2E test `apps/control-plane/tests/e2e/suites/signup_default_only/test_tenant_admin_setup.py`: full kind-cluster walk-through of all 6 setup steps including the `recovery_codes` acknowledgement.

### Implementation for User Story 3 — Backend

- [x] T046 [US3] Author `POST /api/v1/setup/validate-token` endpoint in `apps/control-plane/src/platform/accounts/setup_router.py` per `contracts/enterprise-setup-rest.md`. Sets the setup-session cookie scoped to the tenant subdomain. Returns the resume position from `setup_step_state`.
- [x] T047 [US3] Author `POST /api/v1/setup/step/tos` endpoint. Records TOS acceptance into `setup_step_state`. Records audit-chain entry. Emits `accounts.setup.step_completed` Kafka event with `step=tos`.
- [x] T048 [US3] Author `POST /api/v1/setup/step/credentials` endpoint. Supports both `method=password` (creates credential row in the Acme tenant — the user record is created here) and `method=oauth` (links the user to the tenant's existing OAuth provider per UPD-046 migration 102). Records audit-chain entry.
- [x] T049 [US3] Author `POST /api/v1/setup/step/mfa/start` endpoint. Calls `mfa.generate_totp_secret()` + `mfa.create_provisioning_uri()`. Returns the secret + URI for the frontend QR code render.
- [x] T050 [US3] Author `POST /api/v1/setup/step/mfa/verify` endpoint. Calls `mfa.verify_totp_code()`, persists the `MfaEnrollment` row with status `enrolled`, generates 10 recovery codes via `mfa.generate_recovery_codes()`, stores the bcrypt hashes, returns the plaintext codes ONCE in the response. Records audit-chain entry.
- [x] T051 [US3] Author `POST /api/v1/setup/step/workspace` endpoint. Invokes `assert_role_mfa_requirement('tenant_admin', user)` first. Creates a workspace via `WorkspacesService.create_workspace(name, owner_id)`. Records audit-chain entry.
- [x] T052 [US3] Author `POST /api/v1/setup/step/invitations` endpoint. Invokes `assert_role_mfa_requirement('tenant_admin', user)`. Sends invitations via UPD-042's `AccountsService.create_invitation()` for each entry; empty array skips.
- [x] T053 [US3] Author `POST /api/v1/setup/complete` endpoint. Invokes `assert_role_mfa_requirement('tenant_admin', user)`. Sets `consumed_at` on the invitation row; consumes the setup-session cookie; establishes the standard tenant-admin login session for the user. Emits `accounts.setup.completed` Kafka event. Records audit-chain entry.
- [x] T054 [US3] Wire the new `setup_router` into `apps/control-plane/src/platform/main.py:create_app()` router-registration. Place it AFTER UPD-046's hostname middleware so `request.state.tenant` is populated.

### Implementation for User Story 3 — Frontend

- [x] T055 [US3] [P] Frontend hook `apps/web/lib/hooks/use-tenant-setup.ts`: TanStack Query for `/api/v1/setup/validate-token`; mutations for each `step/*` endpoint plus `setup/complete`. State is preserved server-side; the hook just routes UI events to the backend.
- [x] T056 [US3] [P] Frontend component `apps/web/components/features/auth/TenantSetupWizard.tsx` — orchestrates the 6-step flow. Reads server-returned `current_step` to decide what to render. Refuses to render later steps without server confirmation that prior steps completed (matches the server-side state machine).
- [x] T057 [US3] [P] Frontend component `apps/web/components/features/auth/MandatoryMfaStep.tsx` — refuses to advance without local TOTP verification. Renders QR code via existing `qrcode.react` package. Renders the 10 recovery codes ONCE with a mandatory "I have saved these" acknowledgement checkbox before advancing.
- [x] T058 [US3] Frontend page `apps/web/app/(auth)/setup/page.tsx` — reads `?token=` query param, calls `/api/v1/setup/validate-token`, on success renders `<TenantSetupWizard />`. On 410 renders the canonical "Request a new invitation" surface (no detail about which mailbox). The page lives in the `(auth)` route group so `TenantBrandingProvider` already wraps it.
- [x] T059 [US3] Frontend `(auth)/setup/[token]/error/page.tsx` — error page with "Request a new invitation" CTA. Linked from the validate-token 410 path.

**Checkpoint**: User Story 3 fully validated. The full Enterprise tenant first-admin flow works end-to-end with mandatory MFA, audit-chain entries per step, and proper resume-on-reload behaviour.

---

## Phase 6: User Story 4 — Cross-tenant invitation creates independent identities (Priority: P1)

**Goal**: A user already in the default tenant accepts an invitation to an Enterprise tenant; two independent user records exist (one per tenant); sessions never cross.

**Independent Test**: Per spec User Story 4 — pre-create user in default; tenant admin invites; user accepts; verify exactly two records by SQL count grouped on `(tenant, email)`.

### Tests for User Story 4

- [ ] T060 [P] [US4] Integration test `apps/control-plane/tests/integration/accounts/test_cross_tenant_invitation.py`: full flow — create user in default; tenant admin in Acme creates invitation; user accepts at `acme.musematic.ai/accept-invite`; assert two `users` rows exist (one per tenant) with the same email but distinct identifiers; assert default-tenant credentials and MFA state untouched (SC-006).
- [ ] T061 [P] [US4] Integration test `apps/control-plane/tests/integration/accounts/test_cross_tenant_session_isolation.py`: simulate Juan signed in at the default tenant; visit `acme.musematic.ai`; assert the default-tenant cookie is rejected at the Acme subdomain (FR-019).
- [ ] T062 [P] [US4] Integration test `apps/control-plane/tests/integration/accounts/test_cross_tenant_oauth_per_tenant.py`: default tenant uses email/password; Acme uses OAuth-Google; the same user authenticates at each subdomain via the appropriate provider; both methods produce valid sessions in their respective tenants.
- [ ] T063 [US4] E2E test `apps/control-plane/tests/e2e/suites/signup_default_only/test_cross_tenant_invitation.py`: full browser flow including session-isolation assertions.

### Implementation for User Story 4

- [x] T064 [US4] Modify `apps/control-plane/src/platform/accounts/service.py:AccountsService.accept_invitation()` to handle the cross-tenant case: when the invitation's `tenant_id` differs from any user record matching the email, create a NEW user record in the invitation's tenant (rather than re-using an existing record). The new user gets its own credential row, MFA state, and role assignments per FR-017.
- [x] T065 [US4] Add `CrossTenantInviteAcceptanceError` handling: if the user is currently signed in to a different tenant when accepting, the flow refuses with a clear "Sign out of <other tenant> first" message per spec edge case.
- [x] T066 [US4] Author the `MembershipsService.list_for_user()` method (already skeletoned in T014); wire it into `apps/control-plane/src/platform/accounts/memberships_router.py` as `GET /api/v1/me/memberships` per `contracts/memberships-rest.md`.
- [x] T067 [US4] Mount `memberships_router` under the existing `/api/v1/me/*` prefix in `apps/control-plane/src/platform/me/router.py`.
- [x] T068 [US4] [P] Frontend hook `apps/web/lib/hooks/use-memberships.ts`: TanStack Query for `/api/v1/me/memberships`. Returns the list and a derived `currentMembership` value.
- [x] T069 [US4] [P] Frontend page `apps/web/app/(main)/me/memberships/page.tsx` — list view of the user's tenants with role + login URL per tenant. Each row clickable as a tenant-switcher entry (same redirect mechanic as US6's switcher).
- [x] T070 [US4] [P] Frontend component `apps/web/components/features/auth/CrossTenantInvitationAccept.tsx` — handles the invite acceptance for already-existing-in-default-tenant users. Shows clearly that a new identity will be created in the inviting tenant; refuses to proceed if signed in to a different tenant.

**Checkpoint**: User Story 4 fully validated. Cross-tenant identities are independent; sessions never cross subdomains; `/me/memberships` returns accurate cross-tenant listing.

---

## Phase 7: User Story 5 — Onboarding wizard guides first-run experience (Priority: P2)

**Goal**: After default-tenant verification, the user lands on a 4-step onboarding wizard. State persists; dismissible; re-launchable.

**Independent Test**: Per spec User Story 5 — sign up via US1, land on wizard; verify default workspace name pre-populated; reload mid-step (state persists); dismiss; re-launch from settings.

### Tests for User Story 5

- [ ] T071 [P] [US5] Integration test `apps/control-plane/tests/integration/accounts/test_onboarding_dismiss_relaunch.py`: dismiss after step 2; reload; state preserved with `dismissed_at != null`; relaunch from `POST /api/v1/onboarding/relaunch`; resume position is at step 3 (first incomplete) per SC-007.
- [ ] T072 [P] [US5] Integration test `apps/control-plane/tests/integration/accounts/test_onboarding_step_idempotency.py`: re-calling each step's endpoint with same payload does NOT create duplicate state.
- [ ] T073 [P] [US5] Integration test `apps/control-plane/tests/integration/accounts/test_onboarding_first_agent_hidden_when_upd022_missing.py`: simulate UPD-022 absent (feature flag false); assert `first_agent_step_available=false` in `GET /api/v1/onboarding/state`; the wizard's step 3 is hidden.
- [ ] T074 [US5] E2E test `apps/control-plane/tests/e2e/suites/signup_default_only/test_onboarding_wizard.py`: full browser walk-through of the 4-step wizard.

### Implementation for User Story 5 — Backend

- [x] T075 [US5] Author the onboarding endpoints in `apps/control-plane/src/platform/accounts/onboarding_router.py` per `contracts/onboarding-wizard-rest.md`: `GET /api/v1/onboarding/state`, `POST /api/v1/onboarding/step/workspace-name`, `POST /api/v1/onboarding/step/invitations`, `POST /api/v1/onboarding/step/first-agent`, `POST /api/v1/onboarding/step/tour`, `POST /api/v1/onboarding/dismiss`, `POST /api/v1/onboarding/relaunch`.
- [x] T076 [US5] Wire `onboarding_router` registration in `apps/control-plane/src/platform/main.py:create_app()`.

### Implementation for User Story 5 — Frontend

- [x] T077 [US5] [P] Frontend hook `apps/web/lib/hooks/use-onboarding.ts`: TanStack Query for `/api/v1/onboarding/state` (query) + mutations for each step + dismiss + relaunch. Auto-invalidates on every mutation.
- [x] T078 [US5] [P] Frontend component `apps/web/components/features/onboarding/OnboardingWizard.tsx` — orchestrates 4 steps. Reads `last_step_attempted` from server to decide initial step. Handles the UPD-022-absent case by skipping step 3.
- [x] T079 [US5] [P] Frontend step component `apps/web/components/features/onboarding/OnboardingStepWorkspaceName.tsx` — pre-populated default workspace name; user may edit; advance with `POST /step/workspace-name`.
- [x] T080 [US5] [P] Frontend step component `apps/web/components/features/onboarding/OnboardingStepInvitations.tsx` — embeds the existing UPD-042 invitation form; "Send" sends and advances; "Skip" advances with empty array.
- [x] T081 [US5] [P] Frontend step component `apps/web/components/features/onboarding/OnboardingStepFirstAgent.tsx` — embeds the existing UPD-022 agent-creation wizard. Hidden when the feature flag indicates UPD-022 is absent.
- [x] T082 [US5] [P] Frontend step component `apps/web/components/features/onboarding/OnboardingStepTour.tsx` — interactive product tour or "Skip and finish".
- [x] T083 [US5] Frontend page `apps/web/app/(main)/onboarding/page.tsx` — renders `<OnboardingWizard />`. Auto-redirects from this page to `/dashboard` when state is `done` or `dismissed_at != null`.
- [x] T084 [US5] Frontend page `apps/web/app/(main)/settings/onboarding/page.tsx` — surfaces the "Re-launch wizard" action per FR-030.

**Checkpoint**: User Story 5 fully validated. Wizard renders, persists state, dismisses cleanly, re-launches from settings.

---

## Phase 8: User Story 6 — Multi-tenant user switches between tenants via tenant switcher (Priority: P3)

**Goal**: A user with 2+ memberships sees a tenant switcher in the shell; clicking another tenant redirects to that tenant's login surface.

**Independent Test**: Per spec User Story 6 — pre-provision user in 3 tenants; sign in at one; switcher renders all 3; click another → redirect; cookies don't cross.

### Tests for User Story 6

- [ ] T085 [P] [US6] Integration test `apps/control-plane/tests/integration/accounts/test_tenant_switcher_visibility.py`: user with 1 membership sees no switcher (`/api/v1/me/memberships` returns count=1; the frontend hides the component); user with 3 memberships sees all 3.
- [ ] T086 [P] [US6] Browser test `apps/web/tests/e2e/tenant-switcher.spec.ts` (Playwright): renders the switcher; clicking a non-current tenant redirects to that tenant's login URL (verified via `page.url()`); no cookies cross the subdomain boundary (verified via `page.context().cookies()`).
- [ ] T087 [US6] E2E test `apps/control-plane/tests/e2e/suites/signup_default_only/test_tenant_switcher.py` for the full kind-cluster validation including SC-005 (under 3 seconds click-to-redirect).

### Implementation for User Story 6

- [x] T088 [US6] Frontend component `apps/web/components/features/shell/TenantSwitcher.tsx` — shadcn/ui `DropdownMenu` listing each tenant's display name + role + current-tenant indicator. Renders `null` when memberships.length < 2 per FR-023. Uses `useMemberships` hook from T068.
- [x] T089 [US6] Modify `apps/web/app/(main)/layout.tsx` to render `<TenantSwitcher />` in the header, placed immediately to the right of the platform logo per research R7.
- [x] T090 [US6] [P] Localization for switcher strings — add to `apps/web/locales/{en,es,de,fr,it,zh}/billing.json` (extend existing accounts namespace rather than creating a new locale file).

**Checkpoint**: User Story 6 fully validated. Multi-tenant switcher renders, redirects correctly, hides for single-tenant users.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Audit-chain wiring completeness, observability, runbook, regression coverage, localization, CI rules.

### Audit chain wiring completeness

- [x] T091 Audit completeness check at `apps/control-plane/scripts/lint/check_signup_audit_coverage.py` (CI rule): grep for every method in `accounts/service.py`, `accounts/onboarding.py`, `accounts/first_admin_invite.py`, `accounts/memberships.py` that mutates state; assert each calls `audit_chain_service.append`. Wire into `.github/workflows/ci.yml`.

### Observability

- [x] T092 [P] Extend the existing accounts Grafana dashboard `deploy/helm/observability/templates/dashboards/accounts.yaml` with new panels: signups-per-day at default tenant, first-admin-invitation issuance rate, MFA-enrolment-skip-attempt rate (the SC-004 probe count), cross-tenant invitation acceptance rate, onboarding-wizard completion-vs-dismissed rate. (No new dashboard; this BC was not new.)
- [x] T093 [P] Add Prometheus metrics in `accounts/onboarding.py` and `accounts/first_admin_invite.py`: `accounts_onboarding_step_advanced_total{from_step,to_step}`, `accounts_onboarding_dismissed_total{at_step}`, `accounts_first_admin_invitation_issued_total`, `accounts_first_admin_invitation_resent_total`, `accounts_first_admin_invitation_consumed_seconds` (histogram of issue→consume latency), `accounts_setup_mfa_skip_attempt_total` (the SC-004 metric).

### Runbook

- [x] T094 Author operator runbook `deploy/runbooks/tenant-first-admin-onboarding.md`: provisioning the first Enterprise tenant; resending a first-admin invitation; troubleshooting MFA enrolment (recovery code reset path); diagnosing missing default workspace (deferred-retry job inspection); cross-tenant invitation acceptance for users with existing default-tenant identities.

### Regression coverage

- [x] T095 Extend the J19 New User Signup journey at `tests/e2e/journeys/j19_new_user_signup.py` (UPD-037 file) with explicit default-tenant assertions: the signup form renders ONLY when `useTenantContext().kind == 'default'`; the workspace auto-creation step exists post-verification; the onboarding wizard launches.
- [ ] T096 Run the existing UPD-037 test suite against the post-UPD-048 code to confirm no regressions in anti-enumeration neutrality, OAuth signup, or password rules.

### Localization

- [x] T097 [P] Add localization strings for all new UPD-048 frontend surfaces in `apps/web/locales/{en,es,de,fr,it,zh}/accounts.json`: signup-page (extends UPD-037 strings), `/setup` wizard, onboarding wizard, `/me/memberships` page, tenant switcher, error page for expired setup token. Audit-pass rule 38 — UPD-083 locale parity.

### CI rules summary

- [x] T098 Verify all four CI rules added during this feature are wired in `.github/workflows/ci.yml`: `check_signup_tenant_gate.py` (T038), `check_signup_audit_coverage.py` (T091), and the existing UPD-046 + UPD-047 rules continue to pass.

### Quickstart validation

- [ ] T099 Validate the quickstart walkthrough end-to-end on a fresh kind cluster against the UPD-046 + UPD-047 harness; capture any drift and update `specs/098-default-tenant-signup/quickstart.md`. Note: the UPD-047 quickstart documented a kind harness blocker on 2026-05-02; UPD-048's quickstart inherits that posture and should be re-run once the harness recovers.

### CHANGELOG and root-level updates

- [x] T100 [P] Update root `CHANGELOG.md` to mention UPD-048 — Public Signup at Default Tenant Only.
- [x] T101 [P] Update `docs/system-architecture.md` and `docs/software-architecture.md` to describe the tenant-aware signup, the Enterprise `/setup` flow, the cross-tenant identity model, and `/me/memberships` introspection.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Depends on UPD-046 + UPD-047 being live. No other dependencies.
- **Phase 2 (Foundational)**: Depends on Setup. **BLOCKS all user stories**. Migrations 106 + 107 must run before any test that needs the schema.
- **Phase 3 (US1 — default signup)**: Depends on Phase 2 (workspace auto-creation hook + `accounts.signup.completed` event).
- **Phase 4 (US2 — Enterprise 404)**: Depends on Phase 2 (the tenant-kind gate is the same code path); largely independent of US1.
- **Phase 5 (US3 — Enterprise `/setup`)**: Depends on Phase 2 (tenants service hook calling `TenantFirstAdminInviteService.issue`). The 6-step setup-router endpoints are the largest single-story implementation block.
- **Phase 6 (US4 — cross-tenant invitation)**: Depends on Phase 2 (`MembershipsService` skeleton). Soft dependency on US3 (Enterprise tenants need to exist first to be invitable).
- **Phase 7 (US5 — wizard)**: Depends on Phase 2 (OnboardingWizardService skeleton); soft dependency on US1 (the wizard is the post-verification experience).
- **Phase 8 (US6 — switcher)**: Depends on US4 (`/me/memberships` must work first).
- **Phase 9 (Polish)**: Depends on all user-story phases.

### User Story Dependencies

- **US1, US2, US3 are independent** once Phase 2 lands.
- **US4 depends on US3** (need an Enterprise tenant to issue cross-tenant invitations against).
- **US5 has a soft dependency on US1** (wizard launches post-default-signup).
- **US6 depends on US4** (`/me/memberships` is the data source for the switcher).

---

## Parallel Execution Opportunities

- **Phase 1**: T002, T003, T004, T005 are all parallel (different files).
- **Phase 2**: Models/schemas/exceptions/services skeletons (T008–T015) are mutually parallel after migrations land. Migrations 106 + 107 are sequential.
- **Phase 3 (US1)**: T026–T029 (tests) parallel; T031–T034 (implementation) parallel after the verify-email hook lands.
- **Phase 5 (US3)**: T041–T045 (tests), T046–T053 (8 endpoint implementations — same router file but mostly independent handlers; can be authored sequentially by one engineer or split across two), T055–T059 (5 frontend components/pages parallel).
- **Phase 7 (US5)**: T077–T084 (8 frontend tasks) all parallel after backend endpoints (T075) land.
- **Phase 9 (Polish)**: T091–T101 are largely parallel cleanup tasks.

### Parallel Example — Phase 5 endpoint implementation

```bash
# Two engineers can divide the 8 endpoints; the file is one (setup_router.py) but the handlers are independent.
Engineer A: T046 validate-token + T047 step/tos + T048 step/credentials + T049 step/mfa/start
Engineer B: T050 step/mfa/verify + T051 step/workspace + T052 step/invitations + T053 setup/complete
```

---

## Implementation Strategy

### MVP First — User Story 1 only

1. Complete Phase 1 (Setup) — half a day.
2. Complete Phase 2 (Foundational) — ~1 day.
3. Complete Phase 3 (User Story 1 — default signup) — ~half a day.
4. **STOP and VALIDATE**: A new user can sign up at `app.localhost`, verify, and land on a working Free workspace. Demo if ready.

### Incremental Delivery

1. Foundation ready (Phase 1 + Phase 2).
2. Add User Story 1 (default signup) → demo MVP.
3. Add User Story 2 (Enterprise 404) → close the enumeration vector.
4. Add User Story 3 (Enterprise `/setup`) → first Enterprise customer can onboard.
5. Add User Story 4 (cross-tenant invitation) → multi-tenant identity model live.
6. Add User Story 5 (onboarding wizard) → first-run polish.
7. Add User Story 6 (tenant switcher) → multi-tenant UX polish.
8. Polish (Phase 9) → audit completeness, observability, runbook, localization, regressions.

### Parallel Team Strategy (2 engineers)

- **Day 0**: Both on Phase 1 + Phase 2 migrations + service skeletons.
- **Day 1**: Engineer A on US1 (default signup) + US2 (Enterprise 404); Engineer B starts US3 (Enterprise `/setup`).
- **Day 2**: Engineer A on US4 (cross-tenant invitation) + US5 (wizard); Engineer B finishes US3 + starts US6 (switcher).
- **Day 3**: Both converge on Phase 9 polish (CI rules, dashboard, runbook, localization, regression).

---

## Notes

- [P] tasks = different files, no dependencies on incomplete prior tasks.
- [Story] label maps task to its user story for traceability.
- Each user story is independently testable — the journey suite (J19 extension, J22 with first-admin onboarding, J24 Enterprise Tenant Provisioning in UPD-054) covers this.
- Verify tests fail before implementing the production code path.
- Commit after each task or logical group.
- The Enterprise `/setup` flow's mandatory MFA gate (T015 + T046–T053) is the most security-critical path; treat T042 (the SC-004 probe test) as a release blocker.
- The cross-tenant `/me/memberships` query (T014, T066) is the only path in this feature that uses `BYPASSRLS`; the CI rule from UPD-046 (`check_platform_staff_role_scope.py`) extends to allow `accounts/memberships.py` as a sanctioned platform-staff session consumer.
