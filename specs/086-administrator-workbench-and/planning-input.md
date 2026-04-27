# Planning Input — UPD-036 Administrator Workbench and Super Admin Bootstrap

> **Captured verbatim from the user's `/speckit.specify` invocation on 2026-04-27.** This file is the immutable record of the brownfield context that authored spec.md. Edits MUST NOT be made here; if a correction is needed, edit spec.md and append a note to the corrections list at the top of this file.

## Corrections Applied During Spec Authoring

1. **Route-group placement.** Brownfield input nominates `apps/web/app/(admin)/`; on-disk codebase has `apps/web/app/(main)/admin/` from feature 027. Spec resolves with a NEW `(admin)` route group at the top level (sibling to `(main)` and `(auth)`); the old `(main)/admin/` directory is removed (clean cut for v1.3.0, no backwards-compat redirect).
2. **Page count.** Brownfield input claims "40+ pages organised into 10 functional sections"; counting the FR-548 through FR-557 enumeration yields **57 pages** (Identity & Access 7 + Tenancy & Workspaces 4 + System Configuration 5 + Security & Compliance 10 + Operations & Health 8 + Cost & Billing 6 + Observability 4 + Integrations 5 + Platform Lifecycle 4 super-admin-only + Audit & Logs 4 = 57; 13 are super-admin-only). The "40+" is a lower bound; canonical count is 57.
3. **Dashboard count.** Brownfield input cites 21 Grafana dashboards (FR-554); the actual count from feature 084 + 085 is 22 (the 22nd is `trust-content-moderation.yaml` from feature 078). The workbench's Observability section embeds all 22.
4. **2PA module filenames.** Brownfield input has `2pa_service.py` and `2pa_router.py` — Python module names cannot start with a digit; canonical filenames are `two_person_auth_service.py` and `two_person_auth_router.py`.
5. **Bootstrap startup hook.** Brownfield input says `bootstrap_superadmin_from_env()` runs "once on startup"; clarified to run inside FastAPI's `lifespan` async context manager, gated on the `PLATFORM_SUPERADMIN_USERNAME` env var.

---

# UPD-036 — Administrator Workbench and Super Admin Bootstrap

## Brownfield Context

**Extends:**
- FR-004 (Admin Bootstrap, expanded with FR-004a and FR-004b for super-admin distinction and idempotency).
- FR-022 (Admin User Lifecycle Actions — these become one page in the new workbench).
- FR-123 (Admin Settings UI — the minimal 7-item list is replaced by a full settings page).
- FR-295 (Operator Workbench — companion to the new admin workbench; admin and operator are distinct).
- UPD-017 through UPD-035 (all audit-pass features — the admin workbench exposes management UIs for their data).
- Feature 027-admin-settings-panel (existing, minimal settings panel — absorbed into the workbench).

**Adds:**
1. A comprehensive **Administrator Workbench** (`/admin` route tree in the Next.js frontend) with 40+ pages organized into 10 functional sections.
2. Complete **admin REST API surface** under `/api/v1/admin/*` backing every workbench page.
3. **Super Admin provisioning via environment variables** during installation, alongside the existing CLI bootstrap.
4. **Super Admin distinction** from regular admin (cross-tenant visibility, platform-lifecycle powers).
5. **Critical admin controls**: two-person authorization, impersonation with audit, read-only mode, break-glass recovery, change preview and dry-run.

**FRs:** FR-546 through FR-585 (section 109), plus extensions to FR-004, FR-004a, FR-004b.

---

## Summary

Today the platform has a fragmented administrator experience:
- `admin` is created at install via CLI-displayed one-shot password (FR-004).
- A minimal settings panel exists (feature 027) covering 7 configuration items (FR-123).
- Some admin capabilities are scattered across other surfaces (operator workbench has pause/resume; trust workbench has policies).
- There is **no dedicated administrator surface** — nothing at `/admin`.
- There is **no `superadmin` role enforcement** in the existing UI; the distinction exists in `auth/schemas.py` but is not surfaced to users.
- **Installation-time provisioning via environment variables** does not exist, which blocks headless and automated installs (CI/CD pipelines, GitOps, container platforms where interactive password capture is not possible).

UPD-036 closes all five gaps in a single cohesive feature:
- Single `/admin` workbench with consistent navigation, search, bulk actions, change preview, and strict role gating.
- Full admin REST API matching every UI page, exposed separately in the OpenAPI specification.
- Installer support for `PLATFORM_SUPERADMIN_*` environment variables with idempotency and safety rails.
- Clear separation of `admin` vs `superadmin` roles, with super-admin-only sections gated at both API and UI levels.
- 2PA, impersonation, read-only mode, break-glass access, and change preview as first-class primitives.

---

## User Scenarios

### User Story 1 — Headless super-admin provisioning via GitOps (Priority: P1)

A GitOps pipeline deploys the platform to a fresh Kubernetes cluster. The super admin must be created without any interactive step: no CLI prompt, no captured stdout, no human in the loop. The platform credentials are already stored in the organization's sealed-secrets vault.

**Independent Test:** Install the platform with `PLATFORM_SUPERADMIN_USERNAME`, `PLATFORM_SUPERADMIN_EMAIL`, `PLATFORM_SUPERADMIN_PASSWORD_FILE` environment variables set via a sealed secret. Verify super admin exists, MFA is pending enrollment on first login, and no credential appears in any log.

**Acceptance:**
1. Install completes without interactive prompts.
2. `superadmin` user exists in PostgreSQL with the expected username/email.
3. Password matches the sealed-secret content (verified by login attempt).
4. No secret value appears in stdout, stderr, or container logs.
5. Audit chain entry exists recording bootstrap method = `env_var` with timestamp.
6. Running the install again with identical inputs is idempotent (no duplicate user, no credential overwrite).
7. Running with `--force-reset-superadmin` is rejected in production mode without `ALLOW_SUPERADMIN_RESET=true`.

### User Story 2 — Super admin first login and onboarding (Priority: P1)

A super admin logs in for the first time immediately after install. They see a guided first-install checklist and can complete initial configuration without hunting through docs.

**Independent Test:** New super admin logs into `/admin` for the first time. Verify checklist appears, all items link correctly, and completing each marks it done.

**Acceptance:**
1. `/admin` redirects to a first-install checklist on first super admin login.
2. Checklist items: verify instance settings, configure OAuth providers (optional), invite other admins, install observability stack (links to docs), run first backup, review security settings, enroll MFA.
3. Each item links to its target admin page.
4. Completing an item (or marking it skipped with justification) persists state.
5. Checklist is dismissible; accessible from admin help menu afterward.
6. MFA enrollment cannot be skipped without `ALLOW_INSECURE=true` (dev/test only).

### User Story 3 — Tenant admin manages their tenant (Priority: P1)

A regular `admin` (tenant-scoped) manages users, workspaces, and quotas within their tenant. They cannot see other tenants.

**Independent Test:** Admin A in tenant X cannot see users/workspaces/audit entries in tenant Y. Admin A's API calls to cross-tenant endpoints return 403.

**Acceptance:**
1. `/admin/users` shows only users in admin A's tenant.
2. `/admin/workspaces` shows only workspaces in admin A's tenant.
3. `/admin/tenants` page is not rendered for regular admin (UI) and `/api/v1/admin/tenants/*` returns 403.
4. `/admin/regions` returns 403 for regular admin.
5. `/admin/lifecycle/*` returns 403 for regular admin.
6. Super admin sees all tenants and can filter by tenant on every page.

### User Story 4 — Super admin failover test with 2PA (Priority: P1)

A super admin initiates a quarterly multi-region failover test. Per FR-561, this requires two-person authorization.

**Independent Test:** Super admin A initiates failover from `/admin/regions`. Must enter credentials. Super admin B receives 2PA request, reviews, and approves from a separate session. Failover executes. If B does not approve within 15 minutes, request expires.

**Acceptance:**
1. Initiating failover triggers a 2PA request with full context (source region, target region, expected RPO/RTO impact).
2. 2PA request is visible to all super admins.
3. Second super admin from separate session can approve or reject.
4. Approval triggers failover; rejection cancels and audits both decisions.
5. 2PA expiry window is respected; expired requests return error and must be reinitiated.
6. Audit chain entries are emitted: request initiated, approval/rejection, action result.

### User Story 5 — Admin impersonates a user for troubleshooting (Priority: P2)

A user reports their workspace goal is behaving unexpectedly. A super admin impersonates the user (with justification) to reproduce the issue.

**Independent Test:** Super admin starts impersonation of user U with justification. Banner appears. User U receives notification. Admin performs actions; all actions audited with both principals. Session ends automatically after 30 minutes.

**Acceptance:**
1. Impersonation is only available to super admin.
2. Impersonation requires justification text (minimum 20 characters).
3. Impersonated user U receives notification via their configured channel.
4. UI shows "Impersonating {U.username}" banner prominently.
5. Actions during impersonation audited as `impersonation_user=<admin>, effective_user=<U>`.
6. Session auto-expires after 30 minutes (configurable down, not up).
7. Super admin cannot impersonate another super admin without 2PA.
8. Impersonation is tracked in a dedicated admin report.

### User Story 6 — Admin operates in read-only mode (Priority: P3)

A new admin wants to explore the workbench without risk of accidental changes. They toggle read-only mode for their session.

**Independent Test:** Toggle read-only in header; verify all write buttons disabled; try to POST via API and receive 403 from read-only middleware.

**Acceptance:**
1. Header toggle activates read-only mode per session.
2. Header shows "Read-only mode" badge while active.
3. All write action buttons in the UI are disabled (not hidden, to preserve learnability) and tooltip explains why.
4. API calls for non-GET methods return 403 with a clear message referencing read-only mode.
5. Toggle deactivation is immediate and requires MFA step-up if enabled.

---

### Edge Cases

- **Install with `PLATFORM_SUPERADMIN_USERNAME` set but `PLATFORM_SUPERADMIN_EMAIL` missing**: install fails fast with clear error naming the missing variable.
- **Install with both `PASSWORD` and `PASSWORD_FILE`**: install fails with conflict error.
- **Reinstall with `--force-reset-superadmin` without `ALLOW_SUPERADMIN_RESET=true` in production**: rejected.
- **Super admin attempts to delete themselves**: blocked with clear error (one super admin must always exist; only another super admin can remove them).
- **Last super admin attempts to remove super admin role from themselves**: blocked; must first promote another user.
- **2PA approver attempts to approve their own initiated request**: blocked; approver must be a different principal.
- **Bulk user deletion crosses tenant boundary for non-super admin**: blocked at API with clear message.
- **Impersonation during maintenance mode**: blocked; admins must exit maintenance mode first.
- **Read-only mode and 2PA initiation**: read-only admins cannot initiate 2PA requests (they're in read-only mode).
- **Downgrade from `PLATFORM_TENANT_MODE=multi` to `single` with more than one tenant**: blocked at the API level with a list of tenants that must be removed first.

---

## Requirements

### Functional Requirements

See **FR-546 through FR-585** in section 109 of the FR document. Summarized:

- **FR-546 to FR-557**: Workbench structure and 10 functional sections (40+ pages total).
- **FR-558 to FR-564**: Admin UX primitives — search, bulk actions, change preview, 2PA, impersonation, read-only, real-time.
- **FR-565, FR-566**: Complete admin REST API surface with dedicated rate limits.
- **FR-567 to FR-576**: Admin workbench usability — activity feed, tour, help, accessibility, i18n, theming, export, session security, notifications, URL scheme, data-table standards.
- **FR-577, FR-578**: Confirmation rules and feature flag granularity.
- **FR-579**: Super admin break-glass access.
- **FR-580**: Embedded Grafana panels.
- **FR-581**: E2E coverage (extends J01 and adds J18).
- **FR-582, FR-583**: Mobile layout and error handling.
- **FR-584, FR-585**: Admin-controlled feature flags and tenant mode.

Plus installer changes:
- **FR-004 (extended)**: `PLATFORM_SUPERADMIN_*` environment variables for headless install.
- **FR-004a**: super admin vs. admin distinction.
- **FR-004b**: idempotency and safety rails for bootstrap.

---

## Installer Changes

### New environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PLATFORM_SUPERADMIN_USERNAME` | Yes (for headless mode) | — | Super admin username. |
| `PLATFORM_SUPERADMIN_EMAIL` | Yes (for headless mode) | — | Super admin email. Must be valid RFC 5322. |
| `PLATFORM_SUPERADMIN_PASSWORD` | No | — | Password. Exclusive with `PASSWORD_FILE`. |
| `PLATFORM_SUPERADMIN_PASSWORD_FILE` | No | — | Path to file containing password. Exclusive with `PASSWORD`. |
| `PLATFORM_SUPERADMIN_MFA_ENROLLMENT` | No | `required_on_first_login` | `required_on_first_login` \| `required_before_first_login` \| `disabled` (insecure). |
| `PLATFORM_SUPERADMIN_FORCE_PASSWORD_CHANGE` | No | `true` | Force password change on first login. |
| `PLATFORM_INSTANCE_NAME` | No | `Musematic Platform` | Display name shown in admin header. |
| `PLATFORM_TENANT_MODE` | No | `single` | `single` \| `multi`. |
| `ALLOW_INSECURE` | No | `false` | Allow insecure bootstrap options in non-production envs. |
| `ALLOW_SUPERADMIN_RESET` | No | `false` | Safety flag required alongside `--force-reset-superadmin`. |

### Helm values additions

```yaml
# deploy/helm/platform/values.yaml
superadmin:
  username: ""           # Overridden by env var
  email: ""              # Overridden by env var
  passwordSecretRef: ""  # Reference to existing K8s secret with key 'password'
  mfaEnrollment: required_on_first_login
  forcePasswordChange: true
platformInstanceName: "Musematic Platform"
tenantMode: single
```

If `passwordSecretRef` is set, installer reads from that secret at install time and never generates a random password.

### Installer flow

1. Parse env vars. Reject conflicts (e.g., both `PASSWORD` and `PASSWORD_FILE`).
2. Check idempotency: if superadmin with given username/email already exists and no `--force-reset-superadmin`, skip provisioning and log that super admin already exists.
3. If `--force-reset-superadmin` is set: in production, require `ALLOW_SUPERADMIN_RESET=true`; emit critical audit event; reset password.
4. If password is not provided: generate cryptographically secure random password; write to ephemeral K8s secret `platform-superadmin-bootstrap` with owner reference to the install Job; print to stdout exactly once with clear warning; mark secret for deletion post-bootstrap-retrieval.
5. Create superadmin user in PostgreSQL with role `superadmin`.
6. Emit audit chain entry: `platform.superadmin.bootstrapped` with method (`env_var` / `cli`), timestamp, non-sensitive metadata only.
7. If `MFA_ENROLLMENT=required_before_first_login`: trigger MFA enrollment during install (requires a non-UI path — this is limited; TOTP secret is generated and displayed once, user must scan before first login).
8. Set platform settings: `instance_name`, `tenant_mode`.

---

## UI Implementation

### Route tree (Next.js App Router)

```
apps/web/app/(admin)/
├── layout.tsx                            # Role gate; admin-only layout with top bar and sidebar
├── page.tsx                              # Landing dashboard (FR-547)
├── users/
│   ├── page.tsx                          # List
│   └── [id]/page.tsx                     # Detail drawer
├── roles/
│   ├── page.tsx
│   └── [id]/page.tsx
├── groups/page.tsx
├── sessions/page.tsx
├── oauth-providers/page.tsx
├── ibor/
│   ├── page.tsx
│   └── [connector_id]/page.tsx
├── api-keys/page.tsx
├── tenants/                              # Super admin only; hidden in single-tenant mode
│   ├── page.tsx
│   └── [id]/page.tsx
├── workspaces/
│   ├── page.tsx
│   └── [id]/
│       ├── page.tsx
│       └── quotas/page.tsx
├── namespaces/page.tsx
├── settings/page.tsx
├── feature-flags/page.tsx
├── model-catalog/
│   ├── page.tsx
│   └── [id]/page.tsx
├── policies/page.tsx
├── connectors/page.tsx
├── audit-chain/page.tsx
├── security/
│   ├── sbom/page.tsx
│   ├── pentests/page.tsx
│   ├── rotations/page.tsx
│   └── jit/page.tsx
├── privacy/
│   ├── dsr/page.tsx
│   ├── dlp/page.tsx
│   ├── pia/page.tsx
│   └── consent/page.tsx
├── compliance/page.tsx
├── health/page.tsx
├── incidents/
│   ├── page.tsx
│   └── [id]/page.tsx
├── runbooks/
│   ├── page.tsx
│   └── [id]/page.tsx
├── maintenance/page.tsx
├── regions/page.tsx                      # Super admin only
├── queues/page.tsx
├── warm-pool/page.tsx
├── executions/page.tsx
├── costs/
│   ├── overview/page.tsx
│   ├── budgets/page.tsx
│   ├── chargeback/page.tsx
│   ├── anomalies/page.tsx
│   ├── forecasts/page.tsx
│   └── rates/page.tsx
├── observability/
│   ├── dashboards/page.tsx               # Embed grid of 21 Grafana dashboards
│   ├── alerts/page.tsx
│   ├── log-retention/page.tsx
│   └── registry/page.tsx
├── integrations/
│   ├── webhooks/page.tsx
│   ├── incidents/page.tsx
│   ├── notifications/page.tsx
│   ├── a2a/page.tsx
│   └── mcp/page.tsx
├── lifecycle/                            # Super admin only
│   ├── version/page.tsx
│   ├── migrations/page.tsx
│   ├── backup/page.tsx
│   └── installer/page.tsx
└── audit/
    ├── page.tsx
    └── admin-activity/page.tsx
```

### Shared admin components

- `<AdminLayout>`: top bar with instance name, admin identity badge, read-only toggle, 2PA notifications bell, help menu, theme switcher; collapsible sidebar with grouped navigation.
- `<AdminPage>`: breadcrumbs, page title, help panel, action bar, data area.
- `<AdminTable>`: standard data-table with pagination, sorting, column filters, search, CSV export, saved views (FR-576).
- `<BulkActionBar>`: shown when rows selected, with confirmation rules per FR-577.
- `<ChangePreview>`: renders change diff for dry-run mode (FR-560).
- `<TwoPersonAuthDialog>`: 2PA initiation and approval UI (FR-561).
- `<ImpersonationBanner>`: persistent banner during impersonation sessions.
- `<ReadOnlyIndicator>`: header badge during read-only mode.
- `<AdminHelp>`: collapsible inline help.
- `<ConfirmationDialog>`: tiered confirmation (simple, typed, 2PA).
- `<EmbeddedGrafanaPanel>`: renders Grafana panel with auth-proxied iframe.

---

## Backend Implementation

### New bounded context organization

The admin REST surface does NOT introduce a new bounded context. Instead, each existing bounded context exposes an `admin_router.py` module. A top-level `admin` composition layer wires them together.

```
apps/control-plane/src/platform/
├── admin/                                 # NEW: composition layer (NOT a bounded context)
│   ├── __init__.py
│   ├── router.py                          # Mounts all admin_router modules at /api/v1/admin
│   ├── rbac.py                            # Role gates: require_admin, require_superadmin
│   ├── 2pa_service.py                     # Two-person authorization
│   ├── 2pa_router.py
│   ├── impersonation_service.py
│   ├── impersonation_router.py
│   ├── read_only_middleware.py            # 403 on non-GET when read-only mode active
│   ├── change_preview.py                  # Shared dry-run primitives
│   ├── activity_feed.py                   # Aggregated admin audit query
│   ├── installer_state.py                 # Surface installer metadata
│   └── bootstrap.py                       # Handles PLATFORM_SUPERADMIN_* env vars on startup
├── auth/
│   └── admin_router.py                    # /api/v1/admin/users, roles, sessions, etc.
├── accounts/
│   └── admin_router.py                    # /api/v1/admin/api-keys
├── workspaces/
│   └── admin_router.py                    # /api/v1/admin/workspaces, tenants, namespaces, quotas
├── policies/
│   └── admin_router.py                    # /api/v1/admin/policies
├── connectors/
│   └── admin_router.py                    # /api/v1/admin/connectors
├── privacy_compliance/
│   └── admin_router.py                    # /api/v1/admin/dsr, dlp, pia, consent
├── security_compliance/
│   └── admin_router.py                    # /api/v1/admin/sbom, scans, pentests, rotations, jit, audit
├── cost_governance/
│   └── admin_router.py
├── multi_region_ops/
│   └── admin_router.py
├── model_catalog/
│   └── admin_router.py
├── notifications/
│   └── admin_router.py
├── incident_response/
│   └── admin_router.py
└── audit/
    └── admin_router.py
```

### RBAC gates

```python
# admin/rbac.py
from fastapi import Depends, HTTPException, status

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not (current_user.has_role("admin") or current_user.has_role("superadmin")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return current_user

def require_superadmin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.has_role("superadmin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Super admin role required")
    return current_user
```

### Read-only middleware

```python
# admin/read_only_middleware.py
class AdminReadOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/api/v1/admin/") \
                and request.method != "GET" \
                and request.session.get("admin_read_only_mode"):
            return JSONResponse(status_code=403, content={
                "error_code": "admin_read_only_mode",
                "message": "This session is in read-only mode. Toggle it off to perform write actions.",
            })
        return await call_next(request)
```

### 2PA service

```python
# admin/2pa_service.py
class TwoPersonAuthService:
    """
    Manages 2PA tokens. Flow:
    1. Admin initiates critical action. Service creates a TwoPersonAuthRequest.
    2. Other admins see the request via real-time notification.
    3. A different admin approves or rejects within the window (default 15 min).
    4. If approved, the original request can proceed by presenting the 2PA token.
    """
    async def initiate(self, action: str, payload: dict, initiator: User) -> TwoPersonAuthRequest: ...
    async def approve(self, request_id: UUID, approver: User) -> str: ...
    async def reject(self, request_id: UUID, approver: User, reason: str) -> None: ...
    async def validate_token(self, token: str, action: str) -> bool: ...
```

### Bootstrap service

```python
# admin/bootstrap.py
def bootstrap_superadmin_from_env() -> None:
    """
    Runs once on startup. Creates super admin if env vars are set and not already present.
    Idempotent by default; requires explicit --force-reset-superadmin flag to overwrite.
    """
    username = os.getenv("PLATFORM_SUPERADMIN_USERNAME")
    email = os.getenv("PLATFORM_SUPERADMIN_EMAIL")
    if not username or not email:
        return  # Not using env-var bootstrap
    # ... validate, idempotency check, create, emit audit chain entry
```

---

## Acceptance Criteria

- [ ] `/admin` route tree exists in Next.js with 40+ pages per FR-548 to FR-557
- [ ] `/api/v1/admin/*` endpoints exist for every page and enforce role gates
- [ ] Regular admin cannot access super-admin-only pages (UI hidden, API returns 403)
- [ ] Super admin provisioning via env vars works headlessly (no interactive prompts)
- [ ] Bootstrap is idempotent; `--force-reset-superadmin` is gated by `ALLOW_SUPERADMIN_RESET=true` in production
- [ ] 2PA flow works end-to-end for critical actions per FR-561
- [ ] Impersonation works with banner, notification, auto-expiry, dual-principal audit per FR-562
- [ ] Read-only mode blocks non-GET via middleware and UI per FR-563
- [ ] Break-glass recovery via `platform-cli superadmin recover` works and audits
- [ ] Admin workbench passes axe-core AA with zero violations
- [ ] Admin workbench fully translated into the 6 supported languages
- [ ] Admin workbench covered by extended J01 Platform Administrator journey and new J18 Super Admin Platform-Lifecycle journey
- [ ] Changes to platform settings emit audit chain entries with diffs
- [ ] Configuration export as signed YAML bundle works; import produces diff preview
- [ ] PLATFORM_TENANT_MODE downgrade from multi to single is blocked when multiple tenants exist
