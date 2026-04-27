# Feature Specification: Administrator Workbench and Super Admin Bootstrap

**Feature Branch**: `086-administrator-workbench-and`
**Created**: 2026-04-27
**Status**: Draft
**Input**: User description: "Build a comprehensive Administrator Workbench at `/admin` with a dedicated Next.js route group, ~40 pages organised into ten functional sections (Identity & Access, Tenancy & Workspaces, System Configuration, Security & Compliance, Operations & Health, Cost & Billing, Observability, Integrations, Platform Lifecycle, Audit & Logs), a complete admin REST API surface under `/api/v1/admin/*`, headless super-admin provisioning via `PLATFORM_SUPERADMIN_*` environment variables (alongside the existing CLI bootstrap), a clear `admin` (tenant-scoped) vs `superadmin` (platform-wide) role distinction enforced at both the API and UI layers, and the cross-cutting admin primitives — two-person authorization (2PA), impersonation with full audit, read-only mode, change preview / dry-run, break-glass recovery, real-time updates via WebSocket, embedded Grafana panels, signed configuration export/import, and platform tenant-mode toggle (single vs multi)."

> **Constitutional anchor:** This feature IS the constitutionally-named **UPD-036** ("Administrator Workbench and Super Admin Bootstrap"), the **first feature of platform v1.3.0** (Constitution lines 6, 40, 110, 476). Every constitutional rule that bears on the admin surface — RBAC's `superadmin` role at FR-012, FR-004 / FR-004a / FR-004b super-admin bootstrap, FR-488 (WCAG 2.1 AA — admin workbench fully compliant per FR-570), FR-489 (i18n across the 6 supported locales — admin workbench fully translated per FR-570), FR-490 (theming — admin workbench honours user preference per FR-571), FR-510 (AI interaction disclosure — preserved across admin flows), FR-526 (axe-core CI gate — extended to cover the admin workbench per FR-581), FR-561 (2PA — codified here), FR-562 (impersonation — codified here), FR-563 (read-only mode — codified here), FR-579 (break-glass — codified here) — is the canonical contract this feature delivers.

> **Scope discipline:** This feature builds on, but does NOT re-implement, the artifacts owned by:
> - **Feature 014 (Auth bounded context)** — `superadmin` role and `admin` role already exist in `apps/control-plane/src/platform/auth/`; UPD-036 enforces them at admin-API + admin-UI gates and adds the `bootstrap_superadmin_from_env()` startup hook.
> - **Feature 027 (Admin Settings Panel)** — the existing 7-item settings panel at `apps/web/app/(main)/admin/settings/` is **absorbed** into the new `/admin/settings` page in the new `(admin)` route group; the existing route is removed (not redirected — clean cut, since this is platform v1.3.0's first feature).
> - **Feature 045 (Installer-operations CLI)** — UPD-036 extends the existing `platform-cli` Typer surface with two new sub-commands: `platform-cli superadmin recover` (the FR-579 break-glass path) and `platform-cli superadmin reset --force` (the FR-004b reset path); the existing CLI extension pattern from `apps/ops-cli/src/platform_cli/main.py:62-67` is reused.
> - **Feature 047 + 084 + 085 (Observability stack and dashboards)** — UPD-036 EMBEDS the 21-22 Grafana dashboards on the workbench's Operations & Health and Observability pages via the Grafana renderer plugin (already configured in feature 085's umbrella chart `standard` and `enterprise` presets).
> - **Feature 074-085 (audit-pass bounded contexts)** — every new BC's admin REST surface is exposed by adding an `admin_router.py` module to that BC; UPD-036 owns the **composition layer** (`apps/control-plane/src/platform/admin/`) that mounts all `admin_router.py` modules at `/api/v1/admin/*` plus the cross-cutting primitives (2PA, impersonation, read-only, change preview); UPD-036 does NOT own the per-BC routes themselves — those live with their BCs (e.g., `privacy_compliance/admin_router.py` is owned by feature 076's namespace).
> - **Feature 083 (Accessibility & i18n / `localization/`)** — UPD-036 follows the established next-intl + axe-core CI gate pattern; every new admin string passes through `t()`; the workbench inherits the `localization/` BC's translation drift CI check.
> - **Feature 015 (Next.js app scaffold)** — UPD-036 follows the established route-group + shared-component patterns; the new `(admin)` group is the third route group alongside `(main)` and `(auth)`.
> - **Feature 064 (User Profile and Workspace Settings — UPD-013)** — UPD-036 is the admin-side counterpart; user-side settings remain at `/profile` and `/workspaces/{id}/settings`.

> **Brownfield-input reconciliations** (full detail captured in planning-input.md and re-verified during the plan phase):
> 1. The brownfield input nominates `apps/web/app/(admin)/` as a new route group; the on-disk codebase has `apps/web/app/(main)/admin/` from feature 027. **Resolution:** UPD-036 creates a **new** `(admin)` route group at the top level (sibling to `(main)` and `(auth)`) and migrates feature 027's settings page contents into `(admin)/settings/page.tsx`. The old `(main)/admin/` directory is removed (not redirected — clean cut for v1.3.0).
> 2. The brownfield input enumerates **40+ pages**; counting the FR document's enumeration (FR-548 through FR-557) yields exactly **44 pages** (Identity & Access 7 + Tenancy & Workspaces 4 + System Configuration 5 + Security & Compliance 10 + Operations & Health 8 + Cost & Billing 6 + Observability 4 + Integrations 5 + Platform Lifecycle 4 + Audit & Logs 4 — **57 pages including super-admin-only ones**, of which 13 are super-admin-only). The "40+" wording is a lower bound; the canonical count is 57 pages enumerated across FR-548 through FR-557.
> 3. The brownfield input mentions `/admin/lifecycle/installer/page.tsx` exposes "initial install metadata (date, method, environment variables used, excluding secrets)" — this is FR-556's "Installer State" page; the FR docs FR-004 and FR-004b explicitly require the bootstrap method (`env_var` vs `cli`) be recorded in the audit chain — the installer-state page reads from this audit history, not from a separate config file.
> 4. The brownfield input proposes admin REST routers as `admin_router.py` per BC; this is consistent with the constitutional pattern established by features 074-085 (the canonical `service.py` + `router.py` per BC plus an additive `admin_router.py` for admin-scoped endpoints).
> 5. The brownfield input nominates `bootstrap_superadmin_from_env()` runs "once on startup" — clarified here: this runs as part of FastAPI's `lifespan` async context manager (the same hook used by every BC's startup-time work in this codebase), gated by the presence of the `PLATFORM_SUPERADMIN_USERNAME` env var (no env var → no bootstrap, leaves the existing CLI-bootstrap path untouched).
> 6. The brownfield input describes `2pa_service.py` and `2pa_router.py` filenames; Python module names cannot start with a digit — **canonical filenames are `two_person_auth_service.py` and `two_person_auth_router.py`**. The brownfield-input filenames are corrected here.
> 7. The brownfield input lists "21 Grafana dashboards" for the embed-grid (FR-554); the actual on-disk count from feature 084's audit and feature 085's chart inventory is **22** (the 22nd is `trust-content-moderation.yaml` from feature 078). The workbench's Observability section embeds all 22 — the brownfield-input "21" is consistent with the FR-516 enumeration that omitted the trust-content-moderation dashboard.
> 8. The brownfield input acceptance-criterion 11 mentions "extended J01 Platform Administrator journey and new J18 Super Admin Platform-Lifecycle journey" — these journey numbers are introduced by feature 085 (UPD-035) for J01 extension and FR-581 for J18; UPD-036's E2E coverage extends them with admin-workbench-specific assertions (every page loads, every action's confirmation tier is correct, axe-core AA on every page, every super-admin-only page returns 403 to a non-super admin).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Headless Super-Admin Provisioning via GitOps (Priority: P1)

A GitOps pipeline deploys the platform to a fresh Kubernetes cluster. The super admin MUST be provisioned without any interactive step — no CLI prompt, no captured stdout, no human in the loop. Credentials live in the organisation's sealed-secrets vault (or its equivalent — Docker secrets, sealed-secrets-controller, External Secrets Operator pulling from AWS / GCP / Vault). The installer reads the credential, creates the super admin, records the bootstrap method, and emits an audit chain entry. The installer is **idempotent**: re-running it with identical inputs does NOT create a duplicate user nor overwrite the existing super admin's password (the FR-004b safety contract). The dangerous path — `--force-reset-superadmin` — is gated by an additional `ALLOW_SUPERADMIN_RESET=true` flag in production.

**Why this priority**: Without headless provisioning, the platform cannot be deployed by any GitOps / CI/CD / container-platform path that does not have a human at a CLI. P1 because (a) the constitutional FR-004 / FR-004a / FR-004b contract names this as the canonical bootstrap path; (b) every customer who deploys via GitOps is blocked without it; (c) every UPD-036 page in the workbench is unreachable until *some* super admin exists.

**Independent Test**: On a fresh Kubernetes cluster, deploy the platform with `PLATFORM_SUPERADMIN_USERNAME=alice`, `PLATFORM_SUPERADMIN_EMAIL=alice@example.com`, `PLATFORM_SUPERADMIN_PASSWORD_FILE=/run/secrets/superadmin-password` (the sealed-secret mounted into the install Job). Verify (a) the install Job completes with exit code 0 in ≤ 5 minutes; (b) `alice` exists in the auth BC with role `superadmin`; (c) the password sourced from the sealed-secret matches the stored Argon2 hash (verified by an automated login attempt); (d) NO secret value appears in stdout, stderr, container logs, or any Kubernetes event; (e) the audit chain has a `platform.superadmin.bootstrapped` entry with `method=env_var` and a non-secret-bearing payload; (f) re-running the install Job with identical inputs produces an audit chain entry recording "skipped — super admin alice already exists" and does NOT change the password; (g) re-running with `--force-reset-superadmin=true` and WITHOUT `ALLOW_SUPERADMIN_RESET=true` in `PLATFORM_ENV=production` is REJECTED with a clear error and exit code 2.

**Acceptance Scenarios**:

1. **Given** the env vars `PLATFORM_SUPERADMIN_USERNAME`, `PLATFORM_SUPERADMIN_EMAIL`, and `PLATFORM_SUPERADMIN_PASSWORD_FILE` (sealed-secret mounted) are present at install time, **When** the installer runs in headless mode (no `tty`), **Then** the super admin is created, the audit chain entry recording the bootstrap is emitted, and the installer exits with code 0 in ≤ 5 minutes; no secret material appears in any log stream.
2. **Given** the same env vars produce the same outcome on a re-run, **When** the install runs a second time, **Then** the operation is a no-op (audit entry recording "skipped") and the existing super admin's password / MFA state is unchanged.
3. **Given** `PLATFORM_SUPERADMIN_USERNAME` is set but `PLATFORM_SUPERADMIN_EMAIL` is missing, **When** the installer parses env vars, **Then** the install fails fast with a clear error naming the missing variable; no super admin is created and no audit entry is emitted.
4. **Given** both `PLATFORM_SUPERADMIN_PASSWORD` and `PLATFORM_SUPERADMIN_PASSWORD_FILE` are set, **When** the installer parses env vars, **Then** the install fails fast with a clear conflict error; the operator must remove one before re-running.
5. **Given** `PLATFORM_SUPERADMIN_PASSWORD` is absent (no file either), **When** the installer reaches bootstrap, **Then** it generates a cryptographically random password (≥ 16 chars, ≥ 4 character classes), writes it to stdout exactly once with a clear "save this — it will not be shown again" warning, AND writes it to a Kubernetes Secret `platform-superadmin-bootstrap` flagged with `kubernetes.io/auto-delete-after-retrieval` (the conventional one-shot retrieval pattern from FR-004 line 103); the operator's tooling retrieves the secret post-install and deletes it.
6. **Given** the install runs with `--force-reset-superadmin=true` AND `ALLOW_SUPERADMIN_RESET=true` AND `PLATFORM_ENV != production`, **When** the installer reaches bootstrap, **Then** the existing super admin's password is reset to the new value and a CRITICAL audit chain entry is emitted (severity `critical`, FR-004b's "critical audit chain entry" requirement).
7. **Given** the install runs with `--force-reset-superadmin=true` AND `PLATFORM_ENV=production` AND `ALLOW_SUPERADMIN_RESET` is unset OR `false`, **When** the installer parses flags, **Then** the install is REJECTED with a clear error and exit code 2; no audit entry is emitted (the operation never began).
8. **Given** the installer's bootstrap path requires a Kubernetes Secret reference via Helm values `superadmin.passwordSecretRef`, **When** the operator sets `passwordSecretRef: my-sealed-superadmin` and the secret is unreadable, **Then** the install fails fast naming the unreadable secret; idempotency is preserved (no partial-create).

---

### User Story 2 - Super Admin First Login and Onboarding Checklist (Priority: P1)

A newly-bootstrapped super admin logs into the platform for the first time. They MUST be greeted with a guided first-install checklist that walks through the highest-priority initial-configuration tasks: verify the platform's instance name + tenant mode, configure OAuth providers (optional), invite other admins, install / verify the observability stack, run the first backup, review security settings, and **mandatory MFA enrollment** (cannot be skipped except when `ALLOW_INSECURE=true`, which is dev-only). Each checklist item links to its target admin page; completion (or skip-with-justification) persists per super admin. The checklist is dismissible; once dismissed, it is reachable from the admin help menu.

**Why this priority**: Without a guided first-install checklist, every super admin is on their own to discover where the most-critical first-day tasks live. P1 because (a) the security posture of the entire deployment depends on these tasks being done EARLY (MFA enrollment + observability stack + first backup); (b) without onboarding, the workbench's 57 pages are an undifferentiated maze; (c) constitution rule for FR-568 explicitly requires this checklist for super admins on bootstrap.

**Independent Test**: Create a fresh super admin via the FR-004 path; log in via `/login` with the super admin credentials; verify (a) the post-login redirect lands on `/admin` (not `/home`); (b) the first-install checklist renders with all 7 items in priority order; (c) every item links to its target admin page (clicking item 4 "configure OAuth providers" navigates to `/admin/oauth-providers`); (d) marking an item complete via the checklist persists the state per the super admin's record; (e) MFA enrollment cannot be marked complete without a successful TOTP verification; (f) dismissing the checklist via the "Hide for now" action persists; the checklist is reachable from the admin help menu's "First-install checklist" link; (g) the second super admin (created later by the first) does NOT see the checklist again — the checklist is bootstrap-scoped, not per-super-admin.

**Acceptance Scenarios**:

1. **Given** a freshly-bootstrapped super admin logs in for the first time, **When** post-login redirect runs, **Then** they land on the first-install checklist on `/admin`; the 7 items appear in priority order with their target-page links.
2. **Given** an item is marked complete (e.g., MFA enrollment), **When** the super admin returns to `/admin`, **Then** the item shows as complete and is no longer the highlighted next-action.
3. **Given** the super admin attempts to skip MFA enrollment without `ALLOW_INSECURE=true` set in the platform's environment, **When** they click "Skip MFA", **Then** the action is REFUSED with a clear "MFA enrollment is mandatory in this deployment" error.
4. **Given** the super admin dismisses the checklist via "Hide for now", **When** they next visit `/admin`, **Then** the checklist does NOT appear by default but is reachable from the admin help menu's "Run setup checklist" link.
5. **Given** a second super admin is created later (by the first super admin via `/admin/users`), **When** the second super admin logs in for the first time, **Then** they do NOT see the first-install checklist (the checklist is for the bootstrap super admin only) — they see the regular admin tour per FR-568 instead.

---

### User Story 3 - Tenant Admin Manages Their Tenant Without Cross-Tenant Visibility (Priority: P1)

A regular `admin` (tenant-scoped, NOT super admin) manages users, workspaces, quotas, audit logs, and configuration **within their tenant** and is rigorously blocked from seeing or affecting any other tenant. Every page in the workbench either (a) renders with a tenant-scoped result set, (b) is hidden in the navigation entirely (super-admin-only pages: `/admin/tenants`, `/admin/regions`, `/admin/lifecycle/*`), or (c) returns 403 if accessed via a deep link. Every admin REST endpoint enforces the same scope — a regular admin's `GET /api/v1/admin/users` returns ONLY users in their tenant; a regular admin's `GET /api/v1/admin/tenants` returns 403.

**Why this priority**: Without tenant-scoping enforcement, any admin would have cross-tenant visibility, which is a hard security failure for multi-tenant deployments. P1 because (a) `PLATFORM_TENANT_MODE=multi` is the deployment mode where this matters and is fully supported; (b) the FR-549 + FR-565 contracts explicitly enumerate "super admin only" pages — this story is the executable proof that the gate works.

**Independent Test**: Seed two tenants T1 and T2 with users, workspaces, and audit entries each; create regular admin A1 in T1 and regular admin A2 in T2; verify (a) A1 logged into the workbench sees only T1's users on `/admin/users`, only T1's workspaces on `/admin/workspaces`, only T1's audit entries on `/admin/audit`; (b) A1 deep-linking to `/admin/tenants` (the super-admin-only page) renders a 403 page (not a route-not-found 404); (c) A1's API call `GET /api/v1/admin/tenants` returns HTTP 403 with a clear `"error_code": "superadmin_required"` payload per FR-583; (d) A1 deep-linking to a workspace in T2 (`/admin/workspaces/{T2-workspace-id}`) returns 403; (e) the super admin S sees BOTH T1 and T2 on every page with a tenant filter (default "All tenants").

**Acceptance Scenarios**:

1. **Given** regular admin A1 in tenant T1 opens `/admin/users`, **When** the page queries the admin API, **Then** the response includes only users with `tenant_id=T1`; no T2 user appears.
2. **Given** regular admin A1 opens any super-admin-only page (`/admin/tenants`, `/admin/regions`, `/admin/lifecycle/*`), **When** the page renders, **Then** a 403 error page renders (NOT a 404 — the route exists; the user is simply not authorised) with a clear "Super admin role required" message and a link back to `/admin`.
3. **Given** the workbench navigation renders for regular admin A1, **When** the sidebar is built, **Then** super-admin-only sections (Tenants in Tenancy & Workspaces, Multi-Region Operations in Operations & Health, the Platform Lifecycle section in its entirety) are hidden — not just disabled — to reduce confusion per FR-577 phrasing.
4. **Given** the platform is in `PLATFORM_TENANT_MODE=single` (the FR-585 default), **When** ANY admin (regular or super) opens the workbench, **Then** the Tenants page is hidden and tenant-scoping UI elements (filters, columns) are suppressed; the workbench operates as a single-tenant deployment per FR-585.
5. **Given** super admin S attempts to switch the platform from `PLATFORM_TENANT_MODE=multi` to `single` and there are 2 tenants, **When** the operation is attempted, **Then** the operation is REJECTED with a clear "Cannot downgrade — 2 tenants exist; remove all but one before downgrading" error per FR-585.

---

### User Story 4 - Super Admin Initiates a Failover Test with 2PA (Priority: P1)

A super admin initiates a quarterly multi-region failover test (per feature 081 / UPD-025). Per FR-561, this is a **critical action** that requires two-person authorization (2PA): the initiating super admin enters their credentials and a 2PA request is created; a SECOND super admin (logged in from a separate session) reviews the request payload and either approves or rejects within the configurable window (default 15 minutes); on approval, the failover proceeds; on rejection or expiry, the failover is cancelled. Both decisions emit critical audit chain entries.

**Why this priority**: 2PA is the constitutional contract for every irreversible-or-near-irreversible platform action (super-admin password reset, tenant deletion, platform-wide failover, mass secret rotation, audit chain truncation). P1 because (a) FR-561 is the canonical contract and UPD-036 is the implementation; (b) without 2PA, a single compromised super-admin session can cause platform-wide damage; (c) the J18 super-admin journey explicitly exercises 2PA as one of its end-to-end stages.

**Independent Test**: Seed two super admins S1 and S2 in two separate browser sessions. From S1's session, open `/admin/regions` and click "Initiate failover test". The 2PA dialog appears requiring S1 to re-authenticate (MFA step-up per FR-573). On submit, a `TwoPersonAuthRequest` is created with payload (source region, target region, expected RPO/RTO impact, initiator). From S2's session, the 2PA bell shows a notification; opening it shows the request payload. S2 approves. The failover proceeds. Verify (a) the 2PA token is single-use and bound to the action; (b) S1 cannot approve their own request (the approver MUST be a different principal); (c) if S2 takes more than 15 minutes, the request expires automatically and S1 must reinitiate; (d) the audit chain has 3 entries: `2pa.requested`, `2pa.approved`, `region.failover.initiated` — all linked by the same `correlation_id`.

**Acceptance Scenarios**:

1. **Given** super admin S1 initiates failover from `/admin/regions`, **When** the 2PA dialog requires re-authentication, **Then** S1 enters their credentials with MFA step-up (per FR-573) and submits; a `TwoPersonAuthRequest` is created with a 15-minute expiry and a unique single-use token bound to the `region.failover.initiate` action.
2. **Given** the request is created, **When** S2 opens the 2PA notifications bell, **Then** they see the request payload with full context (source region, target region, expected impact); S2 can approve or reject.
3. **Given** S2 attempts to approve a request they themselves initiated, **When** they submit the approval, **Then** the operation is REJECTED with a clear "Approver must be a different principal than the initiator" error per the spec edge-case.
4. **Given** S2 rejects the request with reason "scheduled maintenance is in progress", **When** the rejection is recorded, **Then** the action does NOT proceed; both decisions (request + rejection) are audit-logged with the rejection reason.
5. **Given** the request is created and 15 minutes elapse without approval, **When** the next 2PA scanner cycle runs, **Then** the request is marked expired and S1's failover attempt fails with a clear "2PA request expired; please reinitiate" error; the expired request is audit-logged.
6. **Given** an admin in read-only mode (per FR-563) attempts to initiate a 2PA request, **When** the request is submitted, **Then** the operation is REJECTED with a clear "Read-only sessions cannot initiate 2PA requests; toggle read-only mode off first" error per the spec edge-case.

---

### User Story 5 - Super Admin Impersonates a User for Troubleshooting (Priority: P2)

A user reports their workspace goal behaves unexpectedly. A super admin (the only role permitted to impersonate per FR-562) starts an impersonation session with a written justification (≥ 20 characters). The impersonation session lasts at most 30 minutes (configurable down, never up). The impersonated user receives an immediate notification via their configured channel. The UI watermarks the session prominently with an "Impersonating {username}" banner. Every action performed during impersonation is audited as a dual-principal entry: `impersonation_user=<admin>, effective_user=<target>`. Impersonating another super admin requires an additional 2PA step.

**Why this priority**: Impersonation is the canonical troubleshooting tool and one of the most-abused privileges in any platform. P2 because (a) it is not on the deployment-time hot path; (b) abuse mitigation depends on the audit-trail + notification + banner being correct, all of which UPD-036 delivers; (c) the J18 super-admin journey exercises this end-to-end.

**Independent Test**: Super admin S logs in. Opens `/admin/users`, finds user U, clicks "Impersonate". Justification dialog requires ≥ 20 chars; on submit, a notification is sent to U via U's configured channel ("Super admin S impersonated your account at HH:MM:SS"). The UI shows the "Impersonating U" banner persistently in the header. S performs an action (e.g., views U's workspace goal). The audit log records `impersonation_user=S, effective_user=U, action=workspace.goal.viewed`. After 30 minutes, the session auto-ends and U receives a "session ended" notification. Verify (a) the banner is visible on every page during impersonation; (b) the audit entry has both principals; (c) S cannot impersonate another super admin without 2PA approval; (d) S cannot start a new impersonation session from inside an existing one.

**Acceptance Scenarios**:

1. **Given** super admin S clicks "Impersonate U" on `/admin/users`, **When** the justification dialog renders, **Then** S MUST enter a justification of ≥ 20 characters; the impersonation cannot start without it.
2. **Given** the impersonation starts, **When** S performs any action, **Then** the audit log records `impersonation_user=S, effective_user=U` per FR-562; the activity-feed entry shows both principals clearly.
3. **Given** the impersonation session is active, **When** S navigates anywhere in the workbench, **Then** the "Impersonating U" banner is visible in the header on every page; the banner has an "End impersonation" button.
4. **Given** the impersonation session reaches 30 minutes, **When** the timeout scanner runs, **Then** the session is auto-ended; S returns to their own session; U receives an "impersonation ended" notification.
5. **Given** S attempts to impersonate another super admin S2, **When** the impersonation is requested, **Then** a 2PA request is created naming S2 as the target; only after approval by a third super admin S3 does the impersonation start.
6. **Given** S has an active impersonation session, **When** S attempts to start a SECOND impersonation, **Then** the operation is REJECTED with "End the current impersonation before starting a new one"; nested impersonation is not supported.
7. **Given** the platform is in `FEATURE_IMPERSONATION_ENABLED=false` (the FR-584 toggle), **When** S attempts to start an impersonation, **Then** the action is REJECTED with a clear "Impersonation is disabled in this deployment" error and the `Impersonate` button is hidden in the UI.

---

### User Story 6 - Admin Exports and Imports Platform Configuration as a Signed Bundle (Priority: P2)

An admin preparing to bootstrap a new staging environment from production exports the platform configuration (settings, policies, quotas, roles, connectors, feature flags, model catalog entries — **excluding secrets**) as a signed YAML bundle. A super admin in the new environment imports the bundle; the import shows a diff preview (what will be created / updated / unchanged); on confirmation, the import applies. The bundle's signature is verifiable using the source platform's published public key. This is FR-572's contract.

**Why this priority**: Without configuration export/import, every new environment is configured by hand — error-prone and slow. P2 because (a) it is not on the every-deployment hot path; (b) it is critical for staging / DR / multi-tenant standardisation; (c) signed bundles + diff previews + secret-exclusion are the safety primitives that make the workflow trustworthy.

**Independent Test**: From `/admin/lifecycle/installer` on the source platform, click "Export configuration". A YAML bundle is downloaded with a sidecar `.sig` signature file. Verify (a) the bundle contains settings, policies, quotas, roles, connectors, feature flags, model catalog entries; (b) the bundle does NOT contain any secret material (every credential field is either a `vault://` reference or omitted entirely); (c) the signature is verifiable using the public key from `GET /api/v1/audit/public-key`. On the target platform, the super admin uploads the bundle to `/admin/lifecycle/installer`; a diff preview renders showing what will change. On confirmation, the import applies; an audit chain entry records the import with the bundle's hash.

**Acceptance Scenarios**:

1. **Given** the admin exports configuration on the source platform, **When** the bundle is generated, **Then** it contains the documented categories (settings, policies, quotas, roles, connectors, feature flags, model catalog) AND nothing else; the bundle is signed using the source platform's audit-chain key.
2. **Given** the bundle is downloaded, **When** the admin inspects it, **Then** every secret field is either a `vault://path/to/secret` reference (preserving the path but not the value) or is omitted entirely (e.g., user passwords are never exported).
3. **Given** the super admin uploads the bundle on the target platform, **When** the import is initiated, **Then** the diff preview renders showing per-resource Create / Update / Unchanged status with diffs for changed fields.
4. **Given** the diff preview is acceptable, **When** the super admin confirms with a typed-confirmation per FR-577, **Then** the import applies; the audit chain records `platform.config.imported` with the bundle's hash and the source platform's public key fingerprint.
5. **Given** the bundle's signature does NOT verify against any trusted public key on the target platform, **When** the import is initiated, **Then** the operation is REJECTED with a clear "Bundle signature does not verify; the bundle may have been tampered with" error.

---

### User Story 7 - Admin Operates in Read-Only Mode for Safe Exploration (Priority: P3)

A new admin wants to learn the workbench without risk of accidental changes. They toggle read-only mode in the header. From that point on, every write button in the UI is **disabled** (NOT hidden — disabled with an explanatory tooltip, preserving learnability per FR-563), and every non-GET API call returns 403 from the read-only middleware. Toggle deactivation requires MFA step-up (per FR-573). The mode is per-session.

**Why this priority**: Read-only mode is a safety primitive for training and exploration. P3 because (a) it does not block any production workflow; (b) it is the lowest-risk feature in this story set; (c) but it MUST work correctly to be useful — half-implemented (e.g., UI hides buttons but API still allows writes) would be worse than not having it.

**Independent Test**: Toggle read-only in the header. Verify (a) the header shows the "Read-only mode" badge persistently; (b) every "Save" / "Delete" / "Apply" / "Confirm" / "Approve" button on every visited page is **disabled** with the tooltip "Disabled — this session is in read-only mode"; (c) attempting any non-GET API call (e.g., `POST /api/v1/admin/users/123/suspend`) via curl with the session cookie returns HTTP 403 with `error_code=admin_read_only_mode` per the brownfield middleware; (d) toggling read-only OFF requires MFA step-up; (e) the toggle state persists across page navigations within the session but is reset on logout.

**Acceptance Scenarios**:

1. **Given** the admin toggles read-only mode in the header, **When** the session marker is set, **Then** the badge shows "Read-only mode" persistently on every page; every write-capable button is disabled with a clear tooltip.
2. **Given** the admin (or a script with the session cookie) issues `POST /api/v1/admin/users/123/suspend`, **When** the read-only middleware evaluates, **Then** the response is HTTP 403 with `{"error_code": "admin_read_only_mode", "message": "..."}` per FR-583; the action does NOT execute.
3. **Given** the admin toggles read-only OFF, **When** MFA is enabled for the session, **Then** the toggle requires a fresh TOTP verification before deactivating per FR-573.
4. **Given** the admin is in read-only mode AND attempts to initiate a 2PA request, **When** the request is submitted, **Then** the operation is REJECTED per User Story 4 acceptance scenario 6 — read-only sessions cannot initiate 2PA requests.
5. **Given** the platform is in `FEATURE_READ_ONLY_ADMIN_MODE=false` (FR-584 toggle), **When** the admin attempts to toggle, **Then** the toggle is hidden in the UI; the middleware does not enforce the mode (no header check needed).

---

### User Story 8 - Admin Performs a Bulk Action with Change Preview (Priority: P3)

An admin needs to bulk-suspend 50 users for a security review. From `/admin/users`, they multi-select 50 users and click "Bulk suspend". A change preview renders showing (a) the affected users, (b) cascade implications (active sessions revoked, in-flight executions paused), (c) irreversibility classification (reversible — suspended users can be reactivated), (d) estimated execution duration. The admin confirms with a typed-confirmation. The action runs and emits a single consolidated audit chain entry naming all 50 users — NOT 50 separate entries.

**Why this priority**: Bulk actions with change preview are the FR-559 + FR-560 contracts; without them, the workbench is impractical for large-tenant operations. P3 because (a) bulk operations are not on every-day hot path; (b) the per-action implementations (e.g., user suspension is feature 016's existing endpoint) already exist; UPD-036 only adds the bulk + preview UI.

**Independent Test**: From `/admin/users`, multi-select 50 users; click "Bulk suspend". Verify (a) the change preview shows 50 users with their currently-active sessions count; (b) the irreversibility classification renders as "Reversible — suspended users can be reactivated"; (c) typed-confirmation requires the admin to type `SUSPEND 50 USERS` per FR-577; (d) on confirm, all 50 users are suspended within the documented duration; (e) ONE audit chain entry records the bulk action (not 50) per FR-559.

**Acceptance Scenarios**:

1. **Given** the admin multi-selects 50 users on `/admin/users`, **When** the bulk-action bar renders, **Then** it shows the available bulk actions (suspend, reject, force-MFA-enrollment, force-password-reset, delete) with the count "50 selected".
2. **Given** the admin clicks "Bulk suspend", **When** the change preview renders, **Then** it shows the 50 affected users, the cascade implications (active sessions revoked, in-flight executions paused), the irreversibility classification, and the estimated duration.
3. **Given** the typed-confirmation dialog renders, **When** the admin types the wrong phrase, **Then** the "Confirm" button stays disabled; only the exact phrase enables it per FR-577.
4. **Given** the bulk action runs, **When** the audit chain entry is emitted, **Then** ONE entry covers all 50 users with a `bulk_action_id` correlating per-user-effect rows in the audit projection.
5. **Given** the bulk-action operation crosses a tenant boundary for a regular admin (one of the 50 users is in a different tenant — a stale reference in the seed data), **When** the API processes the action, **Then** the operation is REJECTED at the API with a clear "Bulk action crosses tenant boundary; max scope is your tenant" error per the spec edge-case; no users are suspended.

---

### User Story 9 - Super Admin Performs Break-Glass Recovery (Priority: P3)

The platform's only super admin is unavailable (long-term illness, departure). Another super admin must be created via a **break-glass** path that does not depend on UI access. The recovery operator runs `platform-cli superadmin recover --username eve --email eve@example.com` from a console with physical cluster access AND an emergency key (a sealed file present on the cluster). The CLI performs the recovery, emits a CRITICAL audit chain entry, and notifies any remaining super admins via every configured notification channel. This is FR-579's contract.

**Why this priority**: Break-glass recovery is the canonical "what happens when normal access is broken" contract. P3 because (a) it should ideally NEVER be invoked; (b) frequency is low but stakes are extreme; (c) testability requires a deliberate test fixture; (d) the constitutional FR-579 explicitly requires the path.

**Independent Test**: Place an emergency-key file at the documented path on the cluster (test fixture). Run `platform-cli superadmin recover --username eve --email eve@example.com`. Verify (a) the CLI authenticates by reading the emergency key (mismatch → reject); (b) a new super admin `eve` is created with a generated password printed exactly once; (c) the audit chain has a `platform.superadmin.break_glass_recovery` entry with severity `critical`; (d) every configured notification channel receives a "Break-glass recovery used" alert; (e) the recovery is idempotent — re-running with the same username/email is a no-op (auditable). The emergency key MUST be a file requiring physical cluster access (not an env var, not a Kubernetes Secret reachable from outside) per FR-579.

**Acceptance Scenarios**:

1. **Given** the operator runs `platform-cli superadmin recover --username eve --email eve@example.com` on the cluster console with the emergency key present at the documented path, **When** the CLI executes, **Then** super admin `eve` is created and a critical audit entry is emitted.
2. **Given** the emergency key is missing or the operator is not on the cluster console, **When** the CLI is invoked, **Then** the operation is REJECTED with a clear error; no audit entry is emitted (the operation never began).
3. **Given** other super admins exist in the platform, **When** the break-glass recovery emits the audit entry, **Then** every remaining super admin receives a notification via every configured channel — Slack, Email, SMS, webhook, etc. — per FR-579.
4. **Given** the recovery completes, **When** super admin `eve` logs in for the first time, **Then** they see the FR-568 first-install checklist (User Story 2) and MUST enroll MFA before any administrative action.
5. **Given** the break-glass recovery has been used in the last 30 days, **When** any compliance auditor opens `/admin/audit/admin-activity`, **Then** the recent break-glass usage is highlighted on the activity feed with a distinct visual treatment (e.g., red border) per FR-567.

---

### User Story 10 - Admin Workbench Embeds Live Grafana Panels (Priority: P3)

Every admin opens `/admin/health` for the daily check-in. Instead of jumping between the workbench and Grafana, the page MUST embed live Grafana panels from the 21-22 platform dashboards (per FR-580 + feature 084's dashboard inventory + feature 085's umbrella chart). The embed respects the admin's scope (super admin sees platform-wide; regular admin sees tenant-scoped). The embed renders via auth-proxied iframe with a CSP that prevents framejacking.

**Why this priority**: Embedding Grafana reduces tool-switching during routine ops. P3 because (a) the underlying dashboards already exist (feature 084); (b) the auth-proxy + CSP work is the only new code in this story.

**Independent Test**: Open `/admin/health`; verify (a) the page embeds the Platform Overview Grafana dashboard via iframe with `Content-Security-Policy: frame-ancestors 'self'`; (b) the iframe URL passes the admin's session token through an auth-proxy (no Grafana login prompt for the admin); (c) the panel respects scope (super admin sees all-tenants version; regular admin sees tenant-scoped version via Grafana's user-context variable). Visit `/admin/observability/dashboards` and verify the grid renders thumbnails of all 22 dashboards with click-through to the full Grafana view.

**Acceptance Scenarios**:

1. **Given** an admin opens `/admin/health`, **When** the page renders, **Then** the embedded Grafana panel for Platform Overview displays correctly without requiring a separate Grafana login.
2. **Given** a regular admin embeds a Grafana panel, **When** the iframe's data is fetched, **Then** the result set is filtered by the admin's tenant scope per FR-580 (no cross-tenant data leaks).
3. **Given** the embed iframe attempts to be embedded on a third-party site, **When** the browser evaluates the CSP, **Then** the `frame-ancestors 'self'` directive PREVENTS framejacking (the iframe refuses to load).
4. **Given** Grafana is unreachable, **When** the page tries to embed the panel, **Then** a clear placeholder card renders ("Grafana unavailable — see /admin/health for status") with a link to the panel's direct Grafana URL.

---

### Edge Cases

- **Install with `PLATFORM_SUPERADMIN_USERNAME` set but `PLATFORM_SUPERADMIN_EMAIL` missing**: install fails fast naming the missing variable; idempotency preserved (no partial create).
- **Install with both `PLATFORM_SUPERADMIN_PASSWORD` and `PLATFORM_SUPERADMIN_PASSWORD_FILE`**: install fails with a clear conflict error; the operator resolves by removing one.
- **Reinstall with `--force-reset-superadmin` without `ALLOW_SUPERADMIN_RESET=true` in production**: REJECTED per FR-004b.
- **Super admin attempts to delete themselves**: BLOCKED with a clear "you cannot delete the only super admin; another super admin must remove you" error; the workbench's `/admin/users` UI hides the "Delete" action on the current user's row to reduce confusion.
- **Last super admin attempts to remove super admin role from themselves**: BLOCKED; "must first promote another user" error.
- **2PA approver attempts to approve their own initiated request**: BLOCKED with "approver must be a different principal".
- **Bulk user deletion crosses tenant boundary for non-super admin**: BLOCKED at the API.
- **Impersonation during maintenance mode**: BLOCKED; admins must exit maintenance mode first (operational discipline — impersonating during maintenance creates ambiguous audit entries).
- **Read-only mode and 2PA initiation**: read-only admins cannot initiate 2PA requests (per User Story 4 / 7 cross-reference).
- **Downgrade from `PLATFORM_TENANT_MODE=multi` to `single` with more than one tenant**: BLOCKED with a clear list of tenants that must be removed first.
- **Super admin attempts to switch tenant mode without 2PA approval**: BLOCKED — tenant-mode switch is in the FR-561 critical-actions list.
- **`/admin/lifecycle/installer` page accessed by a regular admin**: 403 (super-admin-only section).
- **First-install checklist persistence across cluster restart**: the checklist state is persisted to PostgreSQL (the `auth/` BC's user-record `first_install_checklist_state` column or an equivalent additive column from feature 014); a cluster restart preserves the state.
- **Feature flag `FEATURE_READ_ONLY_ADMIN_MODE=false` in `/admin/feature-flags`**: the toggle hides the read-only header switch globally per FR-584.
- **Configuration export bundle imports onto a platform with a different audit-chain public key**: the import is REJECTED unless the target platform's super admin explicitly trusts the source's public key (a separate "import trust roots" admin operation, NOT in scope for UPD-036 — flagged for follow-up).
- **Impersonation banner is removed via DOM manipulation by a malicious admin**: the audit log is the source of truth; banner removal does NOT affect the dual-principal audit. The banner is a UX safety net, not a security boundary.
- **Bootstrap with `MFA_ENROLLMENT=required_before_first_login`**: the install includes an MFA-enrollment substep where the TOTP secret is generated and displayed once; the operator MUST scan it before the install completes. If the scan-confirmation step is skipped, the install fails (the contract is "MFA must be enrolled before login is possible").
- **Activity feed for a deleted admin user**: historical audit entries reference the principal by user ID; the activity feed renders the principal as `(deleted user — ID 0xab12)` with a tooltip linking to the deletion audit entry.
- **Mobile viewport (≥ 768 px wide tablet) accesses an admin page that requires desktop**: a banner indicates "this page requires a desktop viewport" with a clear link to the read-mostly tasks that ARE supported on tablet per FR-582.

## Requirements *(mandatory)*

### Functional Requirements (canonical citations from `docs/functional-requirements-revised-v6.md`)

**Section 109 — Administrator Workbench** (FR-546 through FR-585):

- **FR-546**: Workbench at `/admin` accessible only to `admin` or `superadmin` role; ten functional sections; keyboard-navigable; WCAG AA per FR-488; i18n per FR-489.
- **FR-547**: Landing page with operational summary (totals, pending approvals, active incidents, maintenance windows, audit-chain integrity, observability stack health, last successful backup, critical alerts).
- **FR-548 through FR-557**: Full page enumeration across the ten sections (Identity & Access 7 pages, Tenancy & Workspaces 4 pages, System Configuration 5 pages, Security & Compliance 10 pages, Operations & Health 8 pages, Cost & Billing 6 pages, Observability 4 pages, Integrations 5 pages, Platform Lifecycle 4 pages super-admin-only, Audit & Logs 4 pages — total 57 pages of which 13 are super-admin-only).
- **FR-558**: Universal admin search (Cmd/Ctrl+K) — role-aware result scoping.
- **FR-559**: Bulk actions — multi-select on every list page; consolidated audit entry per batch.
- **FR-560**: Change preview / dry-run for destructive or high-impact actions.
- **FR-561**: 2PA for critical admin actions — codified in this feature.
- **FR-562**: Impersonation with full dual-principal audit — codified in this feature.
- **FR-563**: Read-only mode per session — codified in this feature.
- **FR-564**: Real-time updates via WebSocket on the dashboard, Incidents, Queue Health, Warm Pool, Maintenance, Multi-Region pages.
- **FR-565**: `/api/v1/admin/*` endpoint surface (40+ endpoint groups enumerated) — segregated in OpenAPI.
- **FR-566**: Admin API rate limits distinct from user-facing limits.
- **FR-567**: Admin activity feed with diffs.
- **FR-568**: First-login tour (regular admin) and first-install checklist (super admin on bootstrap).
- **FR-569**: Inline admin help context per page.
- **FR-570**: Admin workbench WCAG AA + i18n.
- **FR-571**: Admin workbench theming + optional elevated-context visual distinction.
- **FR-572**: Configuration export/import as signed YAML bundle.
- **FR-573**: Stricter session security for admin sessions (shorter idle timeout, MFA step-up, IP allowlist option, session binding).
- **FR-574**: Admin-specific notification preferences.
- **FR-575**: URL scheme + breadcrumbs.
- **FR-576**: Standard data-table pattern (server-side pagination, sorting, filters, search, CSV export, saved views).
- **FR-577**: Confirmation rules tiered by impact (no-confirmation, simple, typed, 2PA).
- **FR-578**: Feature flag granularity — global / tenant / workspace / per-user.
- **FR-579**: Super admin break-glass via `platform-cli superadmin recover` — physical cluster access + emergency key.
- **FR-580**: Embedded Grafana panels with auth-proxied iframe.
- **FR-581**: J01 + J18 E2E coverage with axe-core scanning per FR-526.
- **FR-582**: Mobile/tablet read-mostly layout (≥ 768 px); desktop required for full workflows.
- **FR-583**: Structured error responses (machine-readable code, human message, suggested action, correlation ID).
- **FR-584**: Admin-controlled feature flags inventory: `FEATURE_SIGNUP_ENABLED`, `FEATURE_SIGNUP_REQUIRES_APPROVAL`, `FEATURE_SOCIAL_LOGIN_ENABLED`, `FEATURE_MAINTENANCE_MODE`, `FEATURE_API_RATE_LIMITING`, `FEATURE_DLP_ENABLED`, `FEATURE_COST_HARD_CAPS`, `FEATURE_CONTENT_MODERATION`, `FEATURE_IMPERSONATION_ENABLED`, `FEATURE_TWO_PERSON_AUTHORIZATION`, `FEATURE_READ_ONLY_ADMIN_MODE`.
- **FR-585**: `PLATFORM_TENANT_MODE` switch (single | multi); single is default; downgrade blocked when > 1 tenant exists; switch requires 2PA.

**Section 3 — Installer extensions** (FR-004, FR-004a, FR-004b — already in the FR document):

- **FR-004**: Original CLI bootstrap PLUS env-var-driven super-admin provisioning.
- **FR-004a**: `admin` (tenant-scoped) vs `superadmin` (platform-wide) distinction.
- **FR-004b**: Bootstrap idempotency + safety rails (`--force-reset-superadmin` requires `ALLOW_SUPERADMIN_RESET=true` in production).

### Key Entities

- **Administrator Workbench (`apps/web/app/(admin)/`)** — New top-level Next.js route group (sibling to `(main)` and `(auth)`); contains the 57 pages enumerated in FR-548 through FR-557; shared layout `(admin)/layout.tsx` enforces role gate (admin or superadmin) at the layer-0 boundary; super-admin-only routes additionally guarded by per-route `requireSuperadmin` checks.
- **Admin REST surface (`/api/v1/admin/*`)** — Composition layer at `apps/control-plane/src/platform/admin/router.py` mounting per-BC `admin_router.py` modules; OpenAPI tags segregate admin endpoints from user-facing endpoints per FR-565.
- **Admin RBAC gates** — `require_admin` and `require_superadmin` FastAPI dependencies in `apps/control-plane/src/platform/admin/rbac.py` per the brownfield input pattern; reused by every admin endpoint and by the read-only middleware.
- **Two-Person Authorization** (`apps/control-plane/src/platform/admin/two_person_auth_service.py` and `two_person_auth_router.py`) — `TwoPersonAuthRequest` PostgreSQL table tracks: `request_id`, `action`, `payload`, `initiator_id`, `created_at`, `expires_at` (default 15 min), `approved_by_id`, `approved_at`, `rejected_by_id`, `rejected_at`, `rejection_reason`, `consumed`. Single-use bound-to-action token released to the initiator on approval.
- **Impersonation Service** (`apps/control-plane/src/platform/admin/impersonation_service.py` and `impersonation_router.py`) — `ImpersonationSession` PostgreSQL table tracks: `session_id`, `impersonating_user_id` (admin), `effective_user_id` (target), `justification`, `started_at`, `expires_at` (max 30 min), `ended_at`, `end_reason`. Session token used by the FastAPI auth dependency to compose dual-principal context for audit emission.
- **Read-Only Middleware** (`apps/control-plane/src/platform/admin/read_only_middleware.py`) — FastAPI BaseHTTPMiddleware; reads the session marker `admin_read_only_mode`; returns HTTP 403 with `error_code=admin_read_only_mode` on any non-GET to `/api/v1/admin/*`; registered ABOVE auth so the rejection is reached BEFORE the per-endpoint logic.
- **Bootstrap service** (`apps/control-plane/src/platform/admin/bootstrap.py`) — `bootstrap_superadmin_from_env()` runs in the FastAPI lifespan; gated on `PLATFORM_SUPERADMIN_USERNAME` env var presence; idempotent; emits `platform.superadmin.bootstrapped` audit entry with `method=env_var|cli`.
- **Activity feed** (`apps/control-plane/src/platform/admin/activity_feed.py`) — Aggregated read-side query over the audit chain filtered for admin-principal events; powers FR-567's activity feed and the landing-page activity widget.
- **Installer state read** (`apps/control-plane/src/platform/admin/installer_state.py`) — Reads the `platform.superadmin.bootstrapped` audit entries to surface the FR-556 Installer State page; secrets are NEVER returned.
- **`platform-cli superadmin` sub-app** (`apps/ops-cli/src/platform_cli/commands/superadmin.py`) — Two new commands: `recover` (FR-579 break-glass — emergency-key check + super-admin creation + critical audit) and `reset --force` (FR-004b — `ALLOW_SUPERADMIN_RESET=true` in production).
- **Helm values additions** (`deploy/helm/platform/values.yaml`) — `superadmin: { username, email, passwordSecretRef, mfaEnrollment, forcePasswordChange }`, `platformInstanceName`, `tenantMode` per the brownfield input.
- **Shared admin UI components** (`apps/web/components/features/admin/`) — `AdminLayout`, `AdminPage`, `AdminTable`, `BulkActionBar`, `ChangePreview`, `TwoPersonAuthDialog`, `ImpersonationBanner`, `ReadOnlyIndicator`, `AdminHelp`, `ConfirmationDialog`, `EmbeddedGrafanaPanel` per the brownfield input.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Headless super-admin provisioning via `PLATFORM_SUPERADMIN_*` env vars completes on a fresh cluster in ≤ 5 minutes wall-clock; no secret material leaks into stdout / stderr / logs / Kubernetes events.
- **SC-002**: Re-running the installer with identical env vars is a no-op (idempotency contract per FR-004b); no duplicate user, no password change.
- **SC-003**: `--force-reset-superadmin` is REJECTED in `PLATFORM_ENV=production` without `ALLOW_SUPERADMIN_RESET=true`; the dangerous path emits a CRITICAL audit entry when permitted.
- **SC-004**: All 57 enumerated admin pages exist under `apps/web/app/(admin)/`; every super-admin-only page (13 pages) renders 403 to a regular admin via deep link AND is hidden in the workbench navigation.
- **SC-005**: Every admin REST endpoint enforces `require_admin` or `require_superadmin` (verified by an automated route audit at CI time); zero admin endpoints accessible without the appropriate role.
- **SC-006**: Workbench universal search (Cmd/Ctrl+K) returns role-scoped results: super admin sees all tenants; regular admin sees only their tenant; verified by an E2E test.
- **SC-007**: 2PA flow works end-to-end for every action in the FR-561 critical-actions list (super-admin password reset, tenant deletion, platform-wide failover, mass secret rotation, audit chain truncation, `--force-reset-superadmin` via CLI); 2PA expiry is honoured (default 15 minutes); approver MUST be a different principal.
- **SC-008**: Impersonation works end-to-end with: justification ≥ 20 chars, target-user notification within 5 seconds, session auto-expiry at 30 minutes, dual-principal audit entries on every action, super-admin-on-super-admin requires 2PA.
- **SC-009**: Read-only mode enforces non-GET 403 at the middleware layer for every `/api/v1/admin/*` endpoint; the CI-time route audit verifies the middleware is registered ABOVE auth.
- **SC-010**: Break-glass recovery via `platform-cli superadmin recover` works with the documented emergency-key path; emits a critical audit entry; notifies all remaining super admins via every configured channel.
- **SC-011**: Workbench passes axe-core AA scan with zero violations on every visited page (extends J01 + adds J18 per FR-581); the J18 journey exercises tenant creation, settings, maintenance mode, failover test, break-glass simulation, 2PA, audit export.
- **SC-012**: Workbench is fully translated into the 6 supported locales (matching feature 083's `localization/` BC); every admin string passes through `t()`; the translation drift CI check (constitution rule 38, owned by feature 083) passes.
- **SC-013**: All admin write actions emit audit chain entries with field diffs (FR-567); the activity feed renders the diffs inline with click-through to the underlying audit entry.
- **SC-014**: Configuration export bundle is verifiable via the source platform's audit-chain public key; the bundle contains zero secret material; import on a target platform produces a diff preview before apply.
- **SC-015**: `PLATFORM_TENANT_MODE` switch is gated by 2PA; downgrade from `multi` to `single` is BLOCKED when > 1 tenant exists per FR-585.
- **SC-016**: Admin session security: idle timeout default 30 min (configurable down to 5 min); MFA step-up required for destructive actions; new IP+UA combination requires re-authentication per FR-573.
- **SC-017**: Embedded Grafana panels work without a separate Grafana login (auth-proxy); the CSP `frame-ancestors 'self'` prevents framejacking; the iframe respects admin's tenant scope per FR-580.
- **SC-018**: Real-time updates on the dashboard + Incidents + Queue Health + Warm Pool + Maintenance + Multi-Region pages reflect changes within 2 seconds of the underlying event (WebSocket subscription per FR-564); a connection-status indicator is visible.
- **SC-019**: Bulk actions emit a single consolidated audit entry per batch with a `bulk_action_id` correlating per-user-effect rows in the audit projection per FR-559.
- **SC-020**: All destructive actions render change preview with cascade implications, irreversibility classification, and estimated duration before confirmation per FR-560.

## Assumptions

- **Feature 014 (Auth) ships with `superadmin` role enforcement.** The role is in `apps/control-plane/src/platform/auth/schemas.py`; UPD-036 enforces it at the admin-API gates.
- **Feature 045 (Installer-operations CLI) supports sub-app registration.** The new `platform-cli superadmin` sub-app follows the existing pattern; no new CLI framework.
- **Feature 027 (Admin Settings Panel) is replaced, not extended.** The existing `apps/web/app/(main)/admin/settings/` tree is removed; UPD-036 owns the new `(admin)/settings/page.tsx` migration. This is a clean cut for v1.3.0; no backwards-compat redirect.
- **Feature 074-085 (audit-pass BCs) ship with their `service.py` and `router.py` modules.** UPD-036 ADDS an `admin_router.py` to each affected BC and wires them into the composition layer at `apps/control-plane/src/platform/admin/router.py`; the per-BC routes are owned by their BCs.
- **Feature 083 (Accessibility & i18n) ships the next-intl + axe-core CI gate.** UPD-036 follows the established pattern; every admin string passes through `t()`.
- **Feature 084 + 085 (observability stack and umbrella chart) ship the 21-22 dashboards as ConfigMaps and the Grafana renderer plugin in the `standard` and `enterprise` presets.** UPD-036 EMBEDS via auth-proxied iframe; the renderer is unavailable on `minimal` and `e2e` presets — those presets render the embed as a "preview unavailable" placeholder with a click-through.
- **Feature 077 (Notifications) ships with channel-routing for impersonation notifications.** The impersonated-user notification (User Story 5) and break-glass-recovery notifications (User Story 9) use the existing notification BC's outbound delivery surface.
- **Feature 080 (Incident Response) ships with the incident-integration mock for J18.** The J18 super-admin journey uses the same mock-PagerDuty fixture established by feature 085.
- **Feature 081 (Multi-region operations) ships with maintenance gate + failover orchestrator.** UPD-036's User Story 4 (failover with 2PA) calls into feature 081's `/api/v1/regions/failover/execute` endpoint; UPD-036 owns the 2PA wrapper, not the failover logic.
- **Feature 029 (Workflow execution engine) ships with execution control endpoints.** UPD-036's `/admin/executions` page wraps feature 029's existing `pause`, `resume`, `cancel`, `rollback` endpoints with the admin's elevated scope.
- **Out of scope:**
  - **New BC creation** — UPD-036 is a composition layer + UI; per-BC admin routes live with their BCs.
  - **Per-BC business logic** — UPD-036 wires existing endpoints; if a BC does not yet expose an admin-scoped endpoint, the gap is filed back into that BC's roadmap.
  - **External-policy / OPA admin integration** — admin RBAC uses the constitutional FR-012 RBAC engine, not OPA.
  - **Trust-roots store for cross-platform configuration import** — the User Story 6 import currently requires the source key to be one of the trusted keys; cross-platform trust establishment is a follow-up feature.
  - **Mobile-only workflows** — FR-582 explicitly limits mobile to read-mostly tasks; full workflows require desktop. No PWA workflow is in scope.
  - **Native mobile apps** — out of scope; the web workbench at tablet viewport is the only mobile path.
  - **Automated platform-version upgrade orchestration** — `/admin/lifecycle/version` shows version + launches an upgrade with dry-run; the upgrade orchestration logic is owned by feature 045 (installer-operations CLI).
  - **Audit chain truncation** — listed in FR-561's critical-actions enumeration but the FR document and this spec deliberately leave the implementation as a DEFERRED operation; if-and-when implemented, it will require 2PA per the constitutional contract.
