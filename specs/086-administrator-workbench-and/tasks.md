# Tasks: UPD-036 — Administrator Workbench and Super Admin Bootstrap

**Feature**: 086-administrator-workbench-and
**Branch**: `086-administrator-workbench-and`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

User stories (from spec.md):
- **US1 (P1)** — Headless GitOps super-admin provisioning via `PLATFORM_SUPERADMIN_*` env vars (the Track A MVP — every other US is unreachable until SOME super admin exists)
- **US2 (P1)** — Super-admin first login + first-install checklist (the bootstrap super admin's onboarding)
- **US3 (P1)** — Tenant-scoped admin (regular admin sees only their tenant; super-admin-only pages return 403 to non-super admins)
- **US4 (P1)** — Super-admin failover with 2PA (the canonical 2PA contract per FR-561)
- **US5 (P2)** — Super-admin impersonation with full dual-principal audit (FR-562)
- **US6 (P2)** — Configuration export / import as signed YAML bundle (FR-572)
- **US7 (P3)** — Read-only mode per session (FR-563)
- **US8 (P3)** — Bulk action with change preview (FR-559 + FR-560)
- **US9 (P3)** — Break-glass recovery via `platform-cli superadmin recover` (FR-579)
- **US10 (P3)** — Embedded Grafana panels via auth-proxy (FR-580)

Independent-test discipline: every US MUST be runnable in isolation against a kind cluster with feature 086's Helm chart installed; the J18 Super Admin Platform-Lifecycle journey (T091) and the 6 BC-suite tests (T093-T098) are the primary verification surfaces; the CI gate (T099-T102) catches the constitutional rule 30 violations and the bootstrap-secret-leak class.

**Wave-11 sub-division** (per plan.md §"Wave layout"):
- W11A — Bootstrap (Track A): T001-T015
- W11B — Admin REST API (Track B): T016-T056
- W11C — Workbench UI (Track C): T057-T085
- W11D — Validation + polish: T086-T108

---

## Phase 1: Setup

- [x] T001 Create Alembic migration `apps/control-plane/migrations/versions/065_admin_workbench.py` per plan.md research R3 + correction §11: declares (a) `two_person_auth_requests` table (request_id UUID PK, action TEXT, payload JSONB, initiator_id UUID FK→users, created_at TIMESTAMP, expires_at TIMESTAMP, approved_by_id UUID NULL, approved_at TIMESTAMP NULL, rejected_by_id UUID NULL, rejected_at TIMESTAMP NULL, rejection_reason TEXT NULL, consumed BOOLEAN DEFAULT FALSE; UNIQUE single-use index on request_id WHERE consumed=FALSE); (b) `impersonation_sessions` table (session_id UUID PK, impersonating_user_id UUID FK→users, effective_user_id UUID FK→users, justification TEXT NOT NULL, started_at TIMESTAMP, expires_at TIMESTAMP, ended_at TIMESTAMP NULL, end_reason TEXT NULL); (c) ALTER TABLE `users` ADD COLUMN `first_install_checklist_state` JSONB NULL; (d) INDEX `audit_chain_entries_actor_role_created_at_idx` ON `audit_chain_entries(actor_role, created_at DESC)` per research R8. Run `make migrate` to verify the migration applies cleanly.
- [x] T002 [P] Add `admin.events` to the constitutional Kafka topic registry per plan.md correction §6: edit `.specify/memory/constitution.md` § "Kafka topics registry" (lines ~726-779) appending the new row `| admin.events | — | admin composition layer | audit, notifications, all admin consumers |`. The topic is the canonical home for events with no other Kafka home (e.g., `admin.bootstrap.completed`, `admin.tenant_mode.changed`, `admin.2pa.requested`, `admin.2pa.approved`, `admin.2pa.rejected`, `admin.impersonation.started`, `admin.impersonation.ended`, `admin.config.exported`, `admin.config.imported`).
- [x] T003 [P] Inventory the 13 per-BC routers that will receive an `admin_router.py` sibling: write the inventory into `specs/086-administrator-workbench-and/contracts/per-bc-admin-router-inventory.md` (NEW file). Per BC: existing `router.py` path, the BC's primary entity table, the FR section the admin router serves (FR-548 through FR-557 mapping). The 13 BCs: `auth`, `accounts`, `workspaces`, `policies`, `connectors`, `privacy_compliance`, `security_compliance`, `cost_governance`, `multi_region_ops`, `model_catalog`, `notifications`, `incident_response`, `audit`. The inventory is the contract T035-T047 reads.
- [x] T004 [P] Inventory the 57 admin pages from FR-548 through FR-557: write the enumeration into `specs/086-administrator-workbench-and/contracts/admin-page-inventory.md` (NEW file). Per page: route path, FR section, role gate (admin OR superadmin), backing API endpoint(s), page-level data dependencies. Used by T076-T085 (the 10 page-section tasks) as the per-section work breakdown.

---

## Phase 2: Foundational Track A — Bootstrap (US1 P1 MVP)

**Story goal**: Headless super-admin provisioning via `PLATFORM_SUPERADMIN_*` env vars, idempotent across re-runs, with safety rails for `--force-reset-superadmin`. Once this lands, every other US is reachable.

### `bootstrap.py` core

- [x] T005 [US1] [W11A] Create `apps/control-plane/src/platform/admin/__init__.py` (empty package marker) AND `apps/control-plane/src/platform/admin/bootstrap.py` per plan.md design Track A: implements `bootstrap_superadmin_from_env()` per the 11-step flow in the design diagram. Reads env vars (`PLATFORM_SUPERADMIN_USERNAME`, `_EMAIL`, `_PASSWORD`, `_PASSWORD_FILE`, `_MFA_ENROLLMENT`, `_FORCE_PASSWORD_CHANGE`, `PLATFORM_INSTANCE_NAME`, `PLATFORM_TENANT_MODE`); validates presence + exclusivity (PASSWORD vs PASSWORD_FILE — fail fast on conflict per spec edge-case) + RFC 5322 email format. Returns immediately if `PLATFORM_SUPERADMIN_USERNAME` is unset (preserves the existing CLI bootstrap path per plan.md correction §4). The `--force-reset-superadmin` flag is read from env var `PLATFORM_FORCE_RESET_SUPERADMIN` (the brownfield input nominates a CLI flag; the Helm Job translates the flag to an env var). The module exposes BOTH a function (called from FastAPI `lifespan`) AND a CLI entrypoint via `if __name__ == "__main__":` so `python -m platform.admin.bootstrap` invokes the same code from the Helm Job.
- [x] T006 [US1] [W11A] Implement the **idempotency check** in `bootstrap.py` per plan.md research R4: combined `users` table query + `audit_chain_entries` query for `event_type='platform.superadmin.bootstrapped'`. The 4 paths: (a) user exists AND audit entry exists → no-op (canonical idempotent re-run; emit informational log line, exit 0); (b) user exists AND NO audit entry → write the audit entry only (recovery for pre-audit-chain installs); (c) user does NOT exist → create user + audit entry; (d) `--force-reset-superadmin` set → enter the reset path (T008). The check is read in a single transaction to avoid TOCTOU.
- [x] T007 [US1] [W11A] Implement the **password resolution + hashing** in `bootstrap.py` per plan.md research R6: priority order `PLATFORM_SUPERADMIN_PASSWORD_FILE` (read from path) > `PLATFORM_SUPERADMIN_PASSWORD` (env var) > generated `secrets.token_urlsafe(32)`. The generated path writes to stdout EXACTLY ONCE with the warning "save this — it will not be shown again" AND writes to a Kubernetes Secret `platform-superadmin-bootstrap` flagged for one-time retrieval per FR-004 line 103. The password is Argon2id-hashed via the existing `argon2-cffi` 23+ dep (the same hasher used by feature 014's auth BC); the password variable is overwritten with `\0`-bytes after hashing (defence in depth). Constitution Rule 31 — NO logger.* call in `bootstrap.py` may reference the password variable; T100 verifies via static analysis.
- [x] T008 [US1] [W11A] Implement the **`--force-reset-superadmin` safety rail** in `bootstrap.py` per plan.md research R5: when the flag is set, gate by `ALLOW_SUPERADMIN_RESET=true` env var in production (`PLATFORM_ENV=production`); reject with exit code 2 if missing. On reset: update the user's `user_credentials` row with the new Argon2 hash; emit an audit chain entry with `severity="critical"` and `event_type="platform.superadmin.force_reset"` per research R5 (the audit-chain integrity verifier from feature 074 / UPD-024 treats `severity="critical"` entries as MUST-be-verifiable on every chain integrity check); notify any remaining super admins via every configured notification channel (uses feature 077's `NotificationService`).
- [x] T009 [US1] [W11A] Implement the **user + role + settings creation** in `bootstrap.py` per plan.md design Track A steps 7-8: in a single transaction — INSERT into `users` (username, email, mfa_pending if MFA_ENROLLMENT=required_before_first_login, force_password_change if FORCE_PASSWORD_CHANGE=true, first_install_checklist_state=null per T001), INSERT into `user_credentials` (Argon2 hash from T007), INSERT into `user_roles` (role=`RoleType.SUPERADMIN.value` per `auth/schemas.py:21-33`), UPSERT into `platform_settings` (instance_name, tenant_mode). The transaction commits or rolls back atomically.
- [x] T010 [US1] [W11A] Implement the **audit chain emission** in `bootstrap.py` per plan.md design Track A step 9: call `AuditChainService.append()` (existing at `audit/service.py:50-81`) with `event_type="platform.superadmin.bootstrapped"`, `audit_event_source="platform.admin"`, `canonical_payload` containing ONLY non-secret fields (username, email, method=`env_var` or `cli`, mfa_enrollment, force_password_change, instance_name, tenant_mode — EXCLUDING password/password_file paths). The audit append is in the SAME transaction as T009's user creation so a failed audit emit rolls back the user creation (the documented inversion: "logged event that wasn't logged would mislead operators" — same transactional pattern as feature 084 T020 audit-BC log emission).
- [x] T011 [US1] [W11A] Implement the **MFA enrollment substep** in `bootstrap.py` per plan.md correction §5 + spec edge-case "Bootstrap with `MFA_ENROLLMENT=required_before_first_login`": when set, generate TOTP secret via `pyotp` (existing dep from feature 014); render the TOTP URI as a QR code (terminal-printable or PNG to a one-shot retrievable Secret); write the manual-entry secret + QR code to stdout EXACTLY ONCE; mark `users.mfa_pending=true` AND `users.mfa_required_before_login=true`. If the operator does not scan the QR within the install Job's timeout (10 min default), the install fails — the contract is "MFA must be enrolled before login is possible".

### Helm + CLI

- [x] T012 [US1] [W11A] Modify `deploy/helm/platform/values.yaml` per plan.md correction §4 + the brownfield input's "Helm values additions" section: add the `superadmin:` block (`username: ""`, `email: ""`, `passwordSecretRef: ""`, `mfaEnrollment: required_on_first_login`, `forcePasswordChange: true`); add `platformInstanceName: "Musematic Platform"`; add `tenantMode: single`. The brownfield input cites `passwordSecretRef` as the documented production pattern; the chart consumes it via the Helm Job from T013.
- [x] T013 [US1] [W11A] Create `deploy/helm/platform/templates/platform-bootstrap-job.yaml` per plan.md correction §5: Helm hook annotations `helm.sh/hook: post-install,post-upgrade`, `helm.sh/hook-weight: "10"`, `helm.sh/hook-delete-policy: before-hook-creation,hook-succeeded`. The Job runs the control-plane image with command `python -m platform.admin.bootstrap`. Env vars are pulled from values via `valueFrom.secretKeyRef` for `PASSWORD` (per research R6 — Secret mount preferred); Helm values map: `PLATFORM_SUPERADMIN_USERNAME` ← `.Values.superadmin.username`, etc. The Job has `restartPolicy: Never` and a 10-minute timeout. The Job depends on the existing migrations Job's completion (the migrations Job has lower hook-weight or runs in `pre-install`). Include the JOB's ServiceAccount with permissions to read the Secret and write to PostgreSQL.
- [x] T014 [US1] [W11A] Create `apps/ops-cli/src/platform_cli/commands/superadmin.py` per plan.md correction §7: new top-level Typer sub-app `superadmin_app = typer.Typer(help="Manage super admins")`. Commands: `recover` (FR-579 break-glass — T015) and `reset --force` (FR-004b — invokes `bootstrap.py` with `--force-reset-superadmin` flag). Register the sub-app in `apps/ops-cli/src/platform_cli/main.py:75` adding `app.add_typer(superadmin_app, name="superadmin")` AFTER the existing `admin_app` registration at line 71.
- [x] T015 [US1] [W11A] Implement the **break-glass `recover` command** in `superadmin.py` per plan.md research R7 (FR-579): `--username`, `--email` Typer options. Pre-flight check: emergency-key file at `/etc/musematic/emergency-key.bin` (path documented; configurable via `--emergency-key-path`); the file's SHA-256 content hash MUST match the documented expected hash (sealed at install time, recorded in the Helm chart's installation manifest). On match: invoke `bootstrap_superadmin_from_env()` with the recovery flag set; emit audit chain entry with `severity="critical"` and `event_type="platform.superadmin.break_glass_recovery"`; send notifications to ALL remaining super admins via every configured channel via feature 077's NotificationService. On mismatch: refuse with clear error and exit code 2. The CLI's command is documented as REQUIRING physical cluster access (the constitutional FR-579 contract).

---

## Phase 3: Foundational Track B — Composition + Cross-Cutting Primitives

**Story goal**: The admin composition layer + every cross-cutting primitive (RBAC dependencies, read-only middleware, 2PA service, impersonation service, change preview, activity feed, installer state). These are SHARED — every per-BC admin router uses them.

### Composition + RBAC

- [x] T016 [W11B] Create `apps/control-plane/src/platform/admin/router.py` per plan.md design Track B: `admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])`; mount as a child of the FastAPI app via `main.py` (T056). The router will eventually `include_router()` every per-BC admin router (T035-T047) + every cross-cutting router (T020/T023/T030/T033/T036). Set `dependencies=[Depends(rate_limit_admin)]` (the rate-limit group from T017) per FR-566.
- [x] T017 [W11B] Create `apps/control-plane/src/platform/admin/rbac.py` per plan.md design Track B canonical signatures: `require_admin` and `require_superadmin` FastAPI dependencies. Mirror the existing `_require_platform_admin` pattern at `auth/router.py:54-58`. Both functions raise `HTTPException(403)` with the FR-583-compliant structured error payload (error_code, message, suggested_action, correlation_id). Also create the `rate_limit_admin` dependency that consults the existing rate-limit middleware (`common/middleware/rate_limit_middleware.py`) with a separate per-admin-principal counter per FR-566 + the brownfield input security note.
- [x] T018 [W11B] Create `apps/control-plane/src/platform/admin/read_only_middleware.py` per plan.md design Track B canonical signature: `AdminReadOnlyMiddleware(BaseHTTPMiddleware)` that returns 403 on any non-GET request to `/api/v1/admin/*` when the session has `admin_read_only_mode=true`. Modify `apps/control-plane/src/platform/common/app_factory.py` to register the new middleware ABOVE the existing `AuthMiddleware` per the plan's middleware-stack diagram. The flag itself is populated by the existing `AuthMiddleware` from a session record's boolean column (the `sessions` table from feature 014 — adds a column `admin_read_only_mode BOOLEAN DEFAULT FALSE` via the Alembic migration T001 if not already present).

### 2PA service

- [x] T019 [W11B] Create `apps/control-plane/src/platform/admin/two_person_auth_models.py` per plan.md correction §3: SQLAlchemy model `TwoPersonAuthRequest` matching the T001 migration's `two_person_auth_requests` table.
- [x] T020 [W11B] Create `apps/control-plane/src/platform/admin/two_person_auth_service.py` per plan.md research R2 (PostgreSQL storage, 60s scanner): `TwoPersonAuthService` with methods `async initiate(action, payload, initiator) -> TwoPersonAuthRequest`, `async approve(request_id, approver) -> str (token)`, `async reject(request_id, approver, reason) -> None`, `async validate_token(token, action) -> bool` (Constitution Rule 33 — re-validates fresh at apply-time; transactional read-modify-write to set `consumed=true`). The 60s expiry scanner is registered as an APScheduler background task (the established pattern in features 077/079/080). The approver-MUST-be-different-from-initiator check is enforced in `approve()` per spec User Story 4 acceptance scenario 3.
- [x] T021 [W11B] Create `apps/control-plane/src/platform/admin/two_person_auth_router.py`: REST endpoints `POST /2pa/requests` (initiate — per-action permitted-actions list), `POST /2pa/requests/{id}/approve`, `POST /2pa/requests/{id}/reject`, `GET /2pa/requests` (list pending — visible to all super admins per spec User Story 4 acceptance scenario 2), `GET /2pa/requests/{id}` (detail). All endpoints depend on `require_admin` or `require_superadmin` (per the action's criticality — failover endpoint requires `require_superadmin`).

### Impersonation service

- [x] T022 [W11B] Create `apps/control-plane/src/platform/admin/impersonation_models.py` per plan.md correction §3 + research R3: SQLAlchemy model `ImpersonationSession` matching the T001 migration's `impersonation_sessions` table.
- [x] T023 [W11B] Create `apps/control-plane/src/platform/admin/impersonation_service.py` per plan.md research R3: `ImpersonationService` with methods `async start(impersonating_user, target_user, justification) -> ImpersonationSession` (validates justification ≥ 20 chars per spec User Story 5 acceptance scenario 1; refuses nested impersonation per spec User Story 5 acceptance scenario 6; refuses target=super-admin without 2PA token per scenario 5; auto-expires at 30 min via the 60s scanner from T020 — reuses the same APScheduler instance), `async end(session_id, end_reason)`, `async get_active_session(impersonating_user_id)` (used by `get_current_user` to compose the dual-principal request context per Constitution Rule 34). Sends a notification to the impersonated user via feature 077's NotificationService on start. Issues a fresh JWT with claim `impersonation_session_id` (the auth dependency at `common/dependencies.py:38-66` is extended in T024 to read this claim).
- [x] T024 [W11B] Modify `apps/control-plane/src/platform/common/dependencies.py:38-66` (`get_current_user`) per plan.md research R3: when the JWT claims include `impersonation_session_id`, the function fetches the active impersonation session, populates the request context with BOTH `impersonation_user_id` (the admin) AND `effective_user_id` (the target), and returns the effective user's identity for the request body. The `request.scope` is decorated with both IDs for the audit-emit path to read (T025).
- [x] T025 [W11B] Modify `apps/control-plane/src/platform/audit/service.py:50-81` (`AuditChainService.append`) per Constitution Rule 34 + plan.md design: when called inside a request scope where `impersonation_user_id` is set, the appended `canonical_payload` includes BOTH `actor_user_id` (= effective_user_id) AND `impersonation_user_id` (the admin). The audit-row's `actor_role` is the EFFECTIVE user's role; the row's `impersonation_user_id` column is added via the Alembic migration T001 (additive — defaults to NULL). Single-principal audits during impersonation are a regression — T100's static-analysis check verifies every audit emit goes through this path.
- [x] T026 [W11B] Create `apps/control-plane/src/platform/admin/impersonation_router.py`: REST endpoints `POST /impersonation/start` (admin-only — initiates impersonation with justification + target_user_id), `POST /impersonation/end`, `GET /impersonation/active` (returns the admin's current active session if any). All endpoints depend on `require_superadmin` per spec User Story 5 acceptance scenario 1 ("only available to super admin").

### Other primitives

- [x] T027 [W11B] Create `apps/control-plane/src/platform/admin/change_preview.py` per FR-560: shared dry-run primitives. Functions `compute_affected_count(operation, query) -> int`, `classify_irreversibility(operation) -> Literal["reversible","partially_reversible","irreversible"]`, `estimate_duration(operation) -> timedelta`. Used by every per-BC admin router that exposes a destructive endpoint (T035-T047 use these primitives in their bulk endpoints).
- [x] T028 [W11B] Create `apps/control-plane/src/platform/admin/activity_feed.py` per FR-567 + plan.md research R8: read-side aggregation over `audit_chain_entries`. Functions `async list_admin_activity(tenant_id: UUID | None, limit: int = 50, since: datetime | None) -> list[AuditEntry]` (super admin sees all tenants when `tenant_id=None`; regular admin's tenant_id is enforced server-side per spec User Story 3). Uses the new `audit_chain_entries_actor_role_created_at_idx` index from T001.
- [x] T029 [W11B] Create `apps/control-plane/src/platform/admin/installer_state.py` per FR-556: `async get_installer_state() -> InstallerState`. Reads the most recent `platform.superadmin.bootstrapped` audit chain entry to surface the FR-556 Installer State page. Returns date, method (`env_var` or `cli`), instance_name, tenant_mode, mfa_enrollment policy — explicitly EXCLUDING any secret material.
- [x] T030 [W11B] Create `apps/control-plane/src/platform/admin/feature_flags_service.py` per FR-578: 4-level granularity (global / tenant / workspace / per-user). Backed by the existing `platform_settings` table — extended with a `scope` column (global, tenant, workspace, user) and a `scope_id` column. The flag inventory matches FR-584. Emits audit chain entries with diffs on every flag change (FR-584 last sentence).
- [x] T031 [W11B] Create `apps/control-plane/src/platform/admin/settings_router.py` per FR-550: `GET /api/v1/admin/settings` returns the platform settings; `PUT /api/v1/admin/settings` updates them with diff audit emission (the diff is computed before vs after; the audit entry's `canonical_payload` includes both). Migrates the feature 027 `AdminSettingsPanel` API surface — the existing endpoints stay; this router exposes them under `/admin`.
- [x] T032 [W11B] Create `apps/control-plane/src/platform/admin/tenant_mode_service.py` per FR-585 + plan.md research R10: `upgrade_to_multi()` (no entity-count check; bootstrap exemption applies when only one super admin exists), `downgrade_to_single()` (rejects with the list of tenant IDs that must be removed first per spec edge-case). Both methods require a 2PA token (T020 `validate_token`). Emits `admin.tenant_mode.changed` event on `admin.events` topic (T002) AND audit chain entry with `severity="critical"`.
- [x] T033 [W11B] Create `apps/control-plane/src/platform/admin/tenant_mode_router.py`: `POST /api/v1/admin/tenant-mode/upgrade-to-multi`, `POST /api/v1/admin/tenant-mode/downgrade-to-single`. Both depend on `require_superadmin` AND require a valid 2PA token in the request header.

---

## Phase 4: Per-BC Admin Routers (13 BCs — parallel)

**Story goal**: Each existing BC gains an `admin_router.py` that exposes admin-scoped endpoints. The composition layer (T016) mounts them all under `/api/v1/admin/`. Every method depends on `require_admin` or `require_superadmin` per Constitution Rule 30.

### Per-BC routers (each task is one BC's admin_router.py — parallelizable)

- [x] T034 [P] [W11B] Create `apps/control-plane/src/platform/auth/admin_router.py` per FR-548: endpoints for users (list with bulk actions per FR-559, get, suspend, reactivate, force-MFA-enrollment, force-password-reset, delete; the suspend / reactivate flow already exists in feature 016's accounts BC — this router COMPOSES that endpoint at the admin scope), roles (list, get, edit permissions, clone, assign), groups (list, get, map to roles), sessions (list active, revoke individual, bulk-revoke), oauth-providers (CRUD per FR-548 + the existing oauth provider config from feature 014's `auth/router_oauth.py`), ibor (list connectors, trigger sync, view sync history per feature 056's IBOR), api-keys (list, rotate, revoke).
- [x] T035 [P] [W11B] Create `apps/control-plane/src/platform/accounts/admin_router.py`: `/api/v1/admin/api-keys/*` endpoints. Wraps feature 014's existing service-account API key endpoints with admin scope (cross-tenant for super admin; tenant-scoped for regular admin).
- [x] T036 [P] [W11B] Create `apps/control-plane/src/platform/workspaces/admin_router.py` per FR-549: workspaces (list, create, configure, archive, delete with cascade preview), tenants (list, create, suspend, delete — `require_superadmin`), namespaces (CRUD), workspace quotas (configure max agents, max fleets, max executions, max storage, max cost; apply templates).
- [x] T037 [P] [W11B] Create `apps/control-plane/src/platform/policies/admin_router.py`: platform policies (create, edit, attach to tenants/workspaces, preview policy evaluation against sample executions per the existing policy engine from feature 028).
- [x] T038 [P] [W11B] Create `apps/control-plane/src/platform/connectors/admin_router.py`: connector plugin config endpoints (enable/disable Slack/Telegram/Webhook/Email; rotate credentials via vault; test connectivity).
- [x] T039 [P] [W11B] Create `apps/control-plane/src/platform/privacy_compliance/admin_router.py` per FR-551: DSR queue (list pending, approve, execute, deny, view cascade preview), DLP rules (CRUD + per-workspace overrides), PIA approvals (review, approve, request changes), consent records (view, revoke on behalf with justification).
- [x] T040 [P] [W11B] Create `apps/control-plane/src/platform/security_compliance/admin_router.py` per FR-551: SBOM (view, list past releases, filter CVEs), pentests (schedule, view, upload attestation), rotations (view schedules, trigger manual rotation), JIT credentials (view active, approve pending, revoke), audit chain integrity (trigger ad-hoc verification, export signed audit log — wraps feature 074's existing endpoints).
- [x] T041 [P] [W11B] Create `apps/control-plane/src/platform/cost_governance/admin_router.py` per FR-553: budgets (CRUD), chargeback (export reports per period), anomalies (list, acknowledge, mark false positive), forecasts (per-workspace + platform-wide), provider cost rates (configure per model provider / compute type / storage tier).
- [x] T042 [P] [W11B] Create `apps/control-plane/src/platform/multi_region_ops/admin_router.py` per FR-552: regions (list, view replication lag per data store, view RPO/RTO), failover (initiate — REQUIRES 2PA token from T020; failback). The failover endpoint is the canonical 2PA-protected action per FR-561 + spec User Story 4. Endpoint depends on `require_superadmin`.
- [x] T043 [P] [W11B] Create `apps/control-plane/src/platform/model_catalog/admin_router.py` per FR-550: catalog (list, add/update/deprecate entries — wraps feature 075), model cards (upload, retrieve), fallback policies (configure), per-model usage and cost (read).
- [x] T044 [P] [W11B] Create `apps/control-plane/src/platform/notifications/admin_router.py` per FR-555: notification channels (list, create, update, delete), webhooks (manage outbound), templates (manage platform-level), incident integrations (PagerDuty/OpsGenie/VictorOps endpoints), A2A directory (when implemented), MCP catalog (when implemented).
- [x] T045 [P] [W11B] Create `apps/control-plane/src/platform/incident_response/admin_router.py` per FR-552: incidents (list, create manual, link to runbooks, generate post-mortem), runbooks (CRUD, assign to incidents, track execution history).
- [x] T046 [P] [W11B] Create `apps/control-plane/src/platform/audit/admin_router.py` per FR-557: unified query interface over the audit chain (filter by event type, actor, resource, time range), export signed selection, admin-activity-only filtered view.

### Cross-BC admin routes

- [x] T047 [W11B] Create `apps/control-plane/src/platform/admin/health_router.py` per FR-552: `GET /api/v1/admin/health` aggregates the health endpoints from every platform service + every Go satellite + the observability stack (uses the same probes that feature 085's `platform-cli observability status` uses); returns a per-component table for the workbench's `/admin/health` page.
- [x] T048 [W11B] Create `apps/control-plane/src/platform/admin/lifecycle_router.py` per FR-556 (super-admin only): version (read current platform version per component), migrations (list applied + pending Alembic migrations, launch migration with 2PA per spec open question Q7), backup (trigger manual, view history, initiate restore with confirmation), installer-state (uses T029).
- [x] T049 [W11B] Create `apps/control-plane/src/platform/admin/feature_flags_router.py` per FR-578: CRUD on flags with the 4-level granularity from T030.

### Wire-up

- [x] T050 [W11B] Modify `apps/control-plane/src/platform/admin/router.py` (T016) to `include_router()` every per-BC admin_router (T034-T046) + every cross-cutting router (T021/T026/T031/T033/T047/T048/T049). Also include the impersonation_router and two_person_auth_router and tenant_mode_router. The mount order is alphabetical for predictability.
- [x] T051 [W11B] Modify `apps/control-plane/src/platform/main.py` per plan.md correction §4 + Project Structure: register `app.include_router(admin_router)` (the composition layer top-level router from T016) alongside the existing per-BC router includes at lines 1569-1615. Also register the FastAPI `lifespan` callback to invoke `bootstrap_superadmin_from_env()` from T005 on app startup (gated by `PLATFORM_SUPERADMIN_USERNAME` presence per correction §4).

### Config export / import

- [x] T052 [W11B] Create `apps/control-plane/src/platform/admin/config_export_service.py` per FR-572 + plan.md research R9 (tarball + manifest format): `async export_config(scope: Literal["platform","tenant"], tenant_id: UUID | None) -> tuple[bytes, str]` — generates a tarball containing `config.yaml` (settings, policies, quotas, roles, connectors, feature flags, model catalog entries — EXCLUDING any secret), `manifest.json` (per-category SHA-256 hashes), `signature.bin` (signs the manifest with the platform's audit-chain private key from feature 074). Returns `(bundle_bytes, sha256_hex)`. Every secret field is either a `vault://path/to/secret` reference (preserves the path but not the value) OR is omitted entirely (e.g., user passwords are never exported).
- [x] T053 [W11B] Create `apps/control-plane/src/platform/admin/config_import_service.py` per FR-572 + research R9: `async preview_import(bundle: bytes) -> DiffPreview` — verifies the signature against the source platform's public key (retrieved via `GET /api/v1/audit/public-key` from feature 074); on failure rejects with the spec User Story 6 acceptance scenario 5 error; on success, computes a diff (per-resource Create / Update / Unchanged with field-level diffs); returns the preview. `async apply_import(bundle: bytes, confirmation_phrase: str) -> ImportResult` — applies the import after a typed-confirmation per FR-577; emits audit chain entry `platform.config.imported` with the bundle's hash + source platform's public key fingerprint.
- [x] T054 [W11B] Create `apps/control-plane/src/platform/admin/config_import_export_router.py`: `POST /api/v1/admin/config/export` (returns bundle as binary), `POST /api/v1/admin/config/import/preview` (returns the diff preview), `POST /api/v1/admin/config/import/apply` (applies after confirmation). Both `import` endpoints require `require_superadmin` per spec User Story 6.

### WebSocket admin channels

- [x] T055 [W11B] Modify `apps/control-plane/src/platform/ws_hub/subscription.py:11-50` per plan.md correction §12: extend `ChannelType` enum with `ADMIN_HEALTH`, `ADMIN_INCIDENTS`, `ADMIN_QUEUES`, `ADMIN_WARM_POOL`, `ADMIN_MAINTENANCE`, `ADMIN_REGIONS`. Extend `CHANNEL_TOPIC_MAP` mapping each to existing Kafka topics (e.g., `ADMIN_INCIDENTS` → `("incident.triggered", "incident.resolved")`). Add new set `ADMIN_SCOPED_CHANNELS` (mirroring `WORKSPACE_SCOPED_CHANNELS` at lines 39-49). Also add the new `admin.events` topic from T002 to the relevant channels (e.g., `ADMIN_HEALTH` → `("admin.events", "monitor.alerts")`).
- [x] T056 [W11B] Modify `apps/control-plane/src/platform/ws_hub/connection.py` (or equivalent — the WebSocket upgrade handler from feature 019): when a client subscribes to an `ADMIN_*` channel, verify the connecting user has `platform_admin` or `superadmin` role in the JWT claims; reject with 403 close-frame on miss.

---

## Phase 5: Track C Foundational — Shared Components + Stores

**Story goal**: 14 shared admin components + Zustand admin store + TanStack Query mutation hooks. Every page from Phase 6+ uses these.

### Shared components (parallel — each is one component)

- [x] T057 [P] [W11C] Create `apps/web/components/features/admin/AdminLayout.tsx` per plan.md design Track C component map: top bar (instance name from `process.env.NEXT_PUBLIC_PLATFORM_INSTANCE_NAME`, identity badge, read-only toggle from T065, 2PA bell from T087, help menu, theme switch via existing next-themes wiring at `apps/web/app/layout.tsx:17`) + collapsible sidebar with grouped nav (10 sections from FR-548-557; super-admin-only sections hidden when `isSuperAdmin=false`).
- [x] T058 [P] [W11C] Create `apps/web/components/features/admin/AdminPage.tsx`: page shell with breadcrumbs (FR-575) + page title + help panel (uses T067) + action bar + data area.
- [x] T059 [P] [W11C] Create `apps/web/components/features/admin/AdminTable.tsx` per FR-576: server-side pagination (default 50 per page, max 500), sortable columns, column-level filters, free-text search (debounced 300 ms), column visibility toggle, CSV export of current result set, saved views per user (per FR-512 — uses TanStack Query for the saved-views CRUD).
- [x] T060 [P] [W11C] Create `apps/web/components/features/admin/BulkActionBar.tsx` per FR-559: shown when rows are selected; available bulk actions; consolidated audit entry per batch (the API consumes `bulk_action_id` per spec User Story 8 acceptance scenario 4).
- [x] T061 [P] [W11C] Create `apps/web/components/features/admin/ChangePreview.tsx` per FR-560: renders dry-run diff (affected entities list, cascade implications, irreversibility classification badge — green/amber/red, estimated duration). Consumes the `ChangePreview` primitives from T027 via a TanStack Query call to the relevant admin endpoint's `?preview=true` query parameter.
- [x] T062 [P] [W11C] Create `apps/web/components/features/admin/TwoPersonAuthDialog.tsx` per FR-561: 2PA initiation UI (re-authentication + MFA step-up form per FR-573) and approval UI (the approver's view with full request payload). Uses TanStack Query mutations from T070.
- [x] T063 [P] [W11C] Create `apps/web/components/features/admin/ImpersonationBanner.tsx` per FR-562: persistent banner during impersonation showing "Impersonating {username}" + "End impersonation" button. Reads from `useAdminStore` (T069).
- [x] T064 [P] [W11C] Create `apps/web/components/features/admin/ReadOnlyIndicator.tsx` per FR-563: header badge showing "Read-only mode" + toggle handler. The toggle deactivation requires MFA step-up per FR-573 (uses the existing MFA-step-up modal from feature 017).
- [x] T065 [P] [W11C] Create `apps/web/components/features/admin/EmbeddedGrafanaPanel.tsx` per FR-580: iframe with `Content-Security-Policy: frame-ancestors 'self'` header (set via Next.js middleware on the proxy route — T066). The src points to the Next.js auth-proxy `/api/admin/grafana-proxy/[...path]/route.ts`. On HTTP 4xx/5xx from the proxy, renders the graceful-degrade `<a>` link "Grafana panel unavailable — open in new tab" per plan.md risk-register row 9.
- [x] T066 [P] [W11C] Create `apps/web/app/api/admin/grafana-proxy/[...path]/route.ts` per FR-580: Next.js API route handler that proxies requests to the in-cluster Grafana service, injecting the platform's session token via the existing `lib/api.ts` JWT-auth pattern. The proxy preserves the admin's tenant scope (super admin sees all-tenants version; regular admin sees tenant-scoped Grafana variable).
- [x] T067 [P] [W11C] Create `apps/web/components/features/admin/ConfirmationDialog.tsx` per FR-577: tiered confirmation dialog supporting three variants — `simple` (one-click confirm), `typed` (user types entity name or `DELETE`), `2pa` (initiates a 2PA request via `<TwoPersonAuthDialog>`). The variant is a prop; the calling code chooses based on the action's impact tier.
- [x] T068 [P] [W11C] Create `apps/web/components/features/admin/AdminHelp.tsx` per FR-569: collapsible inline help panel with content authored alongside the page (each page imports its help text from `./help.tsx`); links to runbooks where relevant; localized per FR-489 / next-intl.
- [x] T069 [P] [W11C] Create `apps/web/components/features/admin/AdminCommandPalette.tsx` per FR-558: Cmd/Ctrl+K command palette scoped to admin. Extends the existing `cmdk`-based palette at `components/layout/command-palette/CommandPaletteProvider.tsx:18`. Result categories: users, workspaces, agents (FQN), executions (ID), audit entries (keyword), configuration keys. Role-aware result scoping per spec User Story 3 (regular admin sees only their tenant's results).
- [x] T070 [P] [W11C] Create `apps/web/components/features/admin/FirstInstallChecklist.tsx` per FR-568 + spec User Story 2: 7-item checklist (verify instance settings, configure OAuth providers, invite other admins, install observability stack, run first backup, review security settings, enroll MFA). Each item links to its target admin page; completion state persists via `PATCH /api/v1/admin/users/me/checklist-state`. Dismissible via "Hide for now" — accessible from admin help menu afterwards.
- [x] T071 [P] [W11C] Create `apps/web/components/features/admin/AdminTour.tsx` per FR-568: guided tour for new regular admins (the bootstrap super admin sees `<FirstInstallChecklist>` instead, per spec User Story 2 acceptance scenario 5). Tour overlay with 5 steps covering nav, key pages (Users / Workspaces / Settings / Audit), where to find help, how to contact super admin. Dismissible + repeatable.

### Stores + hooks

- [x] T072 [W11C] Create `apps/web/lib/stores/admin-store.ts` per plan.md design Track C: Zustand store with state shape `{ readOnlyMode: boolean, activeImpersonationSession: ImpersonationSession | null, twoPersonAuthNotificationsCount: number, firstInstallChecklistDismissed: boolean }`. Actions: `setReadOnlyMode`, `setActiveImpersonationSession`, `incrementTwoPaNotifications`, `dismissChecklist`. Persists ONLY `firstInstallChecklistDismissed` to localStorage (per-session state for the others).
- [x] T073 [W11C] Create `apps/web/lib/hooks/use-admin-mutations.ts` per plan.md design Track C: TanStack Query `useMutation` hooks for every admin write action (≈ 30 hooks). Each hook wraps a `lib/api.ts` POST/PUT/PATCH/DELETE call to the relevant admin endpoint, manages optimistic updates where safe, and invalidates the relevant query keys on success. The hook factory pattern matches the existing `lib/hooks/use-api.ts` from feature 015.

---

## Phase 6: User Story 1 — Headless Bootstrap E2E (P1) 🎯 MVP VERIFICATION

**Story goal**: The bootstrap path (T005-T015) actually works end-to-end on a fresh kind cluster.

### Tests

- [x] T074 [P] [US1] [W11D] Add E2E test `tests/e2e/suites/admin/test_bootstrap_env_vars.py` per FR-004 + plan.md correction §5: on a fresh kind cluster, install the platform Helm chart with `superadmin.username=alice`, `superadmin.email=alice@example.com`, `superadmin.passwordSecretRef=test-superadmin`. Verify (a) Helm install completes in ≤ 5 min; (b) user `alice` exists with role `superadmin` (PostgreSQL query); (c) password from the sealed-secret matches the Argon2 hash (login attempt); (d) NO secret material appears in `kubectl logs` of the bootstrap Job; (e) audit chain has a `platform.superadmin.bootstrapped` entry with `method=env_var`; (f) re-running the install is idempotent (no duplicate user, no password change). Each acceptance scenario from spec User Story 1 maps to a sub-test.
- [x] T075 [P] [US1] [W11D] Add the negative-path test in the same file: install with `PLATFORM_SUPERADMIN_USERNAME` set but `PLATFORM_SUPERADMIN_EMAIL` missing → assert install fails fast with clear error. Install with both `PLATFORM_SUPERADMIN_PASSWORD` and `PLATFORM_SUPERADMIN_PASSWORD_FILE` set → assert install fails with conflict error.
- [x] T076 [P] [US1] [W11D] Add the `--force-reset-superadmin` test: re-install with `--force-reset-superadmin=true` AND `ALLOW_SUPERADMIN_RESET=true` AND `PLATFORM_ENV != production` → assert reset succeeds + critical audit entry. Re-install with `--force-reset-superadmin=true` AND `PLATFORM_ENV=production` AND `ALLOW_SUPERADMIN_RESET` unset → assert reject with exit code 2.
- [x] T077 [US1] [W11D] Add Helm unittest `deploy/helm/platform/tests/test_bootstrap_job.yaml`: assert (a) the bootstrap-job manifest renders with the correct hook annotations (`post-install,post-upgrade`, hook-weight `"10"`, hook-delete-policy); (b) env-var mappings from values.yaml resolve correctly; (c) the Secret reference path is honoured. Use `helm-unittest` plugin (already wired in feature 085 T100).

---

## Phase 7: User Story 2 — Super Admin First Login + Onboarding Checklist (P1)

**Story goal**: New super admin lands on a guided 7-item first-install checklist; MFA enrollment cannot be skipped (except `ALLOW_INSECURE=true` dev/test).

### Pages + Tests

- [x] T078 [US2] [W11C] Create `apps/web/app/(admin)/layout.tsx` per plan.md design Track C canonical sketch: Server Component reading the JWT cookie via `cookies()`; on missing token → redirect to `/login?redirectTo=/admin`; on missing `platform_admin` AND `superadmin` role → render the 403 page (NOT a redirect, per spec User Story 3 acceptance scenario 2); else wrap children in `<AdminLayout>` (T057) with `isSuperAdmin` boolean forwarded.
- [x] T079 [US2] [W11C] Create `apps/web/app/(admin)/403/page.tsx` (server component): renders a clear "Super admin role required" or "Admin role required" message with a link back to `/admin` (or `/home` for non-admins).
- [x] T080 [US2] [W11C] Create `apps/web/app/(admin)/page.tsx` per FR-547: landing dashboard with high-level operational summary (total users / workspaces / agents / fleets counts, pending approvals counter, active incidents counter, active maintenance windows, audit-chain integrity status, observability stack health, last successful backup, last 24h critical alerts). Each counter links to its detail page. Conditionally renders `<FirstInstallChecklist>` (T070) when the bootstrap super admin's `first_install_checklist_state IS NULL` (or has unfinished items + not dismissed) — server-side check on the user's row.
- [x] T081 [US2] [W11C] Create `PATCH /api/v1/admin/users/me/checklist-state` endpoint in `auth/admin_router.py` (T034 — extend it with this endpoint): updates the current user's `first_install_checklist_state` JSONB column from T001. Used by `<FirstInstallChecklist>` to persist completion / skip-with-justification state.
- [x] T082 [P] [US2] [W11C] Add E2E test `tests/e2e/suites/admin/test_first_install_checklist.py`: verify (a) freshly-bootstrapped super admin lands on the checklist on first login; (b) all 7 items appear; (c) every item links to its target page; (d) marking an item complete persists state; (e) the second super admin (created later) does NOT see the checklist (per spec User Story 2 acceptance scenario 5).
- [x] T083 [P] [US2] [W11C] Add the negative-path test in the same file: super admin attempts to skip MFA enrollment without `ALLOW_INSECURE=true` → action refused with clear error (per spec User Story 2 acceptance scenario 3).

---

## Phase 8: User Story 3 — Tenant-Scoped Admin (P1)

**Story goal**: Regular admin sees only their tenant; super-admin-only pages return 403 to non-super admins. The 57 pages enumerated in FR-548 through FR-557 ARE this user story's surface.

### Pages — split by section (10 parallel sub-tasks per FR-548 to FR-557)

- [x] T084 [P] [US3] [W11C] Create the **Identity & Access** pages (7 pages) per FR-548 + T004 inventory: `users/page.tsx` + `users/[id]/page.tsx`, `roles/page.tsx` + `roles/[id]/page.tsx`, `groups/page.tsx`, `sessions/page.tsx`, `oauth-providers/page.tsx`, `ibor/page.tsx` + `ibor/[connector_id]/page.tsx`, `api-keys/page.tsx`. Each page uses `<AdminPage>` shell + `<AdminTable>` data display + the BC's admin endpoints from T034.
- [x] T085 [P] [US3] [W11C] Create the **Tenancy & Workspaces** pages (4 pages) per FR-549: `tenants/page.tsx` + `tenants/[id]/page.tsx` (super-admin-only — server-side gate on the page component), `workspaces/page.tsx` + `workspaces/[id]/page.tsx` + `workspaces/[id]/quotas/page.tsx`, `namespaces/page.tsx`. Tenants page is HIDDEN when `tenantMode=single` per FR-585.
- [x] T086 [P] [US3] [W11C] Create the **System Configuration** pages (5 pages) per FR-550: `settings/page.tsx` (absorbs feature 027 — `import { AdminSettingsPanel } from "@/components/features/admin/AdminSettingsPanel"`; the existing component from feature 027 stays per plan.md correction §10), `feature-flags/page.tsx`, `model-catalog/page.tsx` + `model-catalog/[id]/page.tsx`, `policies/page.tsx`, `connectors/page.tsx`. ALSO delete `apps/web/app/(main)/admin/layout.tsx` and `apps/web/app/(main)/admin/settings/page.tsx` per plan.md correction §2 (clean cut for v1.3.0; the feature 027 layout's role-gate is replaced by T078's server-side gate; the feature 027 settings page's content is repointed by the new `(admin)/settings/page.tsx`).
- [x] T087 [P] [US3] [W11C] Create the **Security & Compliance** pages (10 pages) per FR-551: `audit-chain/page.tsx`, `security/sbom/page.tsx`, `security/pentests/page.tsx`, `security/rotations/page.tsx`, `security/jit/page.tsx`, `privacy/dsr/page.tsx`, `privacy/dlp/page.tsx`, `privacy/pia/page.tsx`, `compliance/page.tsx`, `privacy/consent/page.tsx`. Each page uses the appropriate BC's admin endpoints (T039, T040).
- [x] T088 [P] [US3] [W11C] Create the **Operations & Health** pages (8 pages) per FR-552: `health/page.tsx` (uses T047's `/admin/health` aggregator AND `<EmbeddedGrafanaPanel>` from T065 for live Platform Overview metrics), `incidents/page.tsx` + `incidents/[id]/page.tsx`, `runbooks/page.tsx` + `runbooks/[id]/page.tsx`, `maintenance/page.tsx`, `regions/page.tsx` (super-admin-only), `queues/page.tsx`, `warm-pool/page.tsx`, `executions/page.tsx`. The Incidents page subscribes to `ADMIN_INCIDENTS` WebSocket channel from T055 for real-time updates per FR-564.
- [x] T089 [P] [US3] [W11C] Create the **Cost & Billing** pages (6 pages) per FR-553: `costs/overview/page.tsx`, `costs/budgets/page.tsx`, `costs/chargeback/page.tsx`, `costs/anomalies/page.tsx`, `costs/forecasts/page.tsx`, `costs/rates/page.tsx`. Embeds D15 Cost Governance Grafana dashboard via `<EmbeddedGrafanaPanel>`.
- [x] T090 [P] [US3] [W11C] Create the **Observability** pages (4 pages) per FR-554: `observability/dashboards/page.tsx` (renders thumbnails of all 22 Grafana dashboards per plan.md correction §3 — the 22nd is `trust-content-moderation.yaml` from feature 078), `observability/alerts/page.tsx` (Prometheus + Loki alert rules), `observability/log-retention/page.tsx`, `observability/registry/page.tsx`.
- [x] T091 [P] [US3] [W11C] Create the **Integrations** pages (5 pages) per FR-555: `integrations/webhooks/page.tsx`, `integrations/incidents/page.tsx`, `integrations/notifications/page.tsx`, `integrations/a2a/page.tsx`, `integrations/mcp/page.tsx`.
- [x] T092 [P] [US3] [W11C] Create the **Platform Lifecycle** pages (4 pages — super-admin-only) per FR-556: `lifecycle/version/page.tsx`, `lifecycle/migrations/page.tsx` (launch migration with 2PA per spec open question Q7), `lifecycle/backup/page.tsx`, `lifecycle/installer/page.tsx` (uses T029's `installer_state.py`). Each page server-side-gates on `superadmin` role per the spec User Story 3 contract.
- [x] T093 [P] [US3] [W11C] Create the **Audit & Logs** pages (4 pages) per FR-557: `audit/page.tsx` (unified query interface), `audit/admin-activity/page.tsx` (filtered for admin actions; uses T028's `activity_feed.py`; super admin sees all tenants, regular admin sees their tenant per FR-567).
- [x] T094 [US3] [W11D] Add E2E test `tests/e2e/suites/admin/test_role_gates.py` per spec User Story 3 acceptance scenarios 1-4: seed two tenants T1 and T2; create regular admin A1 in T1, super admin S; verify A1 sees only T1's users on `/admin/users` (cross-tenant data leak negative test); A1 deep-linking to `/admin/tenants` returns 403 page (NOT 404); A1's API call `GET /api/v1/admin/tenants` returns 403 with `error_code=superadmin_required`; super admin S sees both tenants on every page.

---

## Phase 9: User Story 4 — Failover with 2PA (P1)

**Story goal**: Critical action `multi_region_ops.failover.initiate` requires 2PA — initiator + approver MUST be different super admins; expiry honoured (default 15 min).

### Wire-up + Tests

- [x] T095 [US4] [W11B] Modify `apps/control-plane/src/platform/multi_region_ops/admin_router.py` (T042) per FR-561: the `POST /admin/regions/failover/execute` endpoint requires a 2PA token in the request header `X-Two-Person-Auth-Token`. The endpoint calls `TwoPersonAuthService.validate_token(token, action="multi_region_ops.failover.execute")` from T020 — Constitution Rule 33 — re-validation is fresh at apply-time. On invalid/expired token: 403 with clear error.
- [x] T096 [US4] [W11C] Wire `<TwoPersonAuthDialog>` (T062) into `(admin)/regions/page.tsx` (T088): clicking "Initiate failover test" opens the dialog (initiator path); the dialog requires re-authentication with MFA step-up per FR-573. On submit, creates the 2PA request via T021's `POST /admin/2pa/requests` AND opens the failover endpoint with the returned token.
- [x] T097 [US4] [W11C] Wire the **2PA notifications bell** in `<AdminLayout>` (T057): subscribes to the `ADMIN_HEALTH` WebSocket channel for `admin.2pa.requested` events; renders a count badge; clicking opens a dropdown of pending requests; each request links to a per-request approval/rejection page that uses `<TwoPersonAuthDialog>` (approver path).
- [x] T098 [US4] [W11D] Add E2E test `tests/e2e/suites/admin/test_two_person_auth.py` per spec User Story 4 acceptance scenarios: seed two super admins S1 and S2; from S1 initiate failover; verify (a) 2PA request is created with 15-min expiry; (b) S2 sees the request via the bell; (c) S1 attempting to approve their own request is rejected with "approver must be a different principal"; (d) after 15 min, the request expires and S1's failover attempt fails with clear "2PA request expired" error; (e) read-only admin attempting to initiate 2PA is rejected per spec User Story 4 acceptance scenario 6.

---

## Phase 10: User Story 5 — Impersonation (P2)

**Story goal**: Super admin impersonates a user with justification ≥ 20 chars; banner; notification to the impersonated user; dual-principal audit; 30-min auto-expiry.

### Wire-up + Tests

- [x] T099 [US5] [W11C] Wire `<ImpersonationBanner>` (T063) into `<AdminLayout>` (T057): reads `useAdminStore.activeImpersonationSession` (T072); renders the banner when set; the banner has an "End impersonation" button that calls `POST /api/v1/admin/impersonation/end` from T026.
- [x] T100 [US5] [W11C] Add the **"Impersonate" action** to `(admin)/users/page.tsx` (T084) row actions: clicking opens the justification dialog (≥ 20 chars validated client + server); on submit, calls `POST /api/v1/admin/impersonation/start` from T026; on success, the new JWT (with `impersonation_session_id` claim per T023) replaces the user's current token; the page re-renders the banner; navigation continues. The button is HIDDEN for non-super-admins (also hidden when `FEATURE_IMPERSONATION_ENABLED=false` per FR-584).
- [x] T101 [US5] [W11D] Add E2E test `tests/e2e/suites/admin/test_impersonation.py` per spec User Story 5 acceptance scenarios: super admin S impersonates user U with justification "Reproducing user-reported workspace bug XYZ-1234"; verify (a) U receives notification via configured channel within 5s; (b) the banner appears on every page; (c) S performs an action (read U's workspace goal); the audit log entry has BOTH `impersonation_user_id=S` AND `effective_user_id=U`; (d) after 30 min, session auto-ends and U receives "session ended" notification; (e) S cannot impersonate another super admin without 2PA (per scenario 5); (f) S cannot start a SECOND impersonation while the first is active (per scenario 6).

---

## Phase 11: User Story 6 — Configuration Export / Import (P2)

**Story goal**: Signed YAML bundle (tarball + manifest + signature) export from one platform, import to another with diff preview.

### Wire-up + Tests

- [x] T102 [US6] [W11C] Create the export UI on `(admin)/lifecycle/installer/page.tsx` (T092): "Export configuration" button calls `POST /api/v1/admin/config/export` from T054; the response is a binary tarball; downloads to the user's machine.
- [x] T103 [US6] [W11C] Create the import UI on the same page: "Import configuration" file-upload widget; on upload, calls `POST /api/v1/admin/config/import/preview` from T054; renders the diff preview using `<ChangePreview>` (T061); on confirm (typed `IMPORT CONFIG` per FR-577), calls `POST /api/v1/admin/config/import/apply`.
- [x] T104 [US6] [W11D] Add E2E test `tests/e2e/suites/admin/test_config_export_import.py`: from source platform — export configuration; verify the bundle contains the documented categories AND zero secret material (every credential field is a `vault://` reference or omitted); the signature verifies against the source's public key. On target platform — import the bundle; verify the diff preview renders; on confirm, the import applies and an audit chain entry `platform.config.imported` records the bundle's hash + source key fingerprint. Negative test: bundle with corrupted signature is REJECTED per spec User Story 6 acceptance scenario 5.

---

## Phase 12: User Story 7 — Read-Only Mode (P3)

**Story goal**: Header toggle activates read-only mode per session; non-GET to `/api/v1/admin/*` returns 403; toggle deactivation requires MFA step-up.

### Wire-up + Tests

- [x] T105 [US7] [W11C] Wire `<ReadOnlyIndicator>` (T064) into `<AdminLayout>` (T057): renders the toggle in the header; toggling ON/OFF posts to `PATCH /api/v1/admin/sessions/me/read-only-mode` (a new endpoint added to T034's `auth/admin_router.py`). Toggling OFF requires MFA step-up per FR-573 — uses the existing MFA-step-up modal from feature 017.
- [x] T106 [US7] [W11C] Wire the **read-only signal** through every write button: every form submit / "Delete" / "Apply" / "Confirm" / "Approve" button in the workbench reads `useAdminStore.readOnlyMode` (T072); when true, the button is `disabled` (NOT hidden) with the tooltip "Disabled — this session is in read-only mode" per spec User Story 7 acceptance scenario 1.
- [x] T107 [US7] [W11D] Add E2E test `tests/e2e/suites/admin/test_read_only_mode.py` per spec User Story 7 acceptance scenarios: toggle read-only ON; verify all write buttons are disabled with the tooltip; verify `POST /api/v1/admin/users/123/suspend` returns 403 with `error_code=admin_read_only_mode` (the AdminReadOnlyMiddleware from T018); toggle OFF requires MFA step-up; verify read-only admin cannot initiate 2PA per cross-reference to spec User Story 4 scenario 6.

---

## Phase 13: User Story 8 — Bulk Action with Change Preview (P3)

**Story goal**: Multi-select on every list page; bulk-action bar; change preview with cascade implications + irreversibility classification + duration; consolidated single audit entry per batch.

### Wire-up + Tests

- [x] T108 [US8] [W11C] Wire `<BulkActionBar>` (T060) into `<AdminTable>` (T059): when rows are multi-selected, the bar renders; available actions per page (e.g., users page: suspend / reject / force-MFA-enrollment / force-password-reset / delete). Clicking an action opens `<ChangePreview>` (T061) with the dry-run via `?preview=true` query param to the relevant admin endpoint.
- [x] T109 [US8] [W11B] Modify `auth/admin_router.py` (T034) to support bulk endpoints: `POST /api/v1/admin/users/bulk/suspend` accepts a list of user IDs + `?preview=true|false`. When `preview=true`, returns a `ChangePreview` (T027) without performing the action. When `preview=false` (apply), performs the bulk suspend AND emits ONE consolidated audit chain entry with a `bulk_action_id` correlating to per-user-effect rows in the audit projection per spec User Story 8 acceptance scenario 4.
- [x] T110 [US8] [W11D] Add E2E test `tests/e2e/suites/admin/test_bulk_action.py` per spec User Story 8 acceptance scenarios: multi-select 50 users; verify the bulk-action bar shows "50 selected"; click "Bulk suspend"; verify the change preview shows 50 affected users + cascade implications + reversibility "Reversible" + estimated duration; the typed-confirmation dialog requires the exact phrase `SUSPEND 50 USERS`; on confirm, all 50 are suspended within the documented duration; ONE audit chain entry covers all 50 with a `bulk_action_id`. Negative test: bulk-action crossing tenant boundary for a regular admin is REJECTED at the API per spec User Story 8 acceptance scenario 5.

---

## Phase 14: User Story 9 — Break-Glass Recovery (P3)

**Story goal**: `platform-cli superadmin recover` works with the documented emergency-key path; emits critical audit; notifies remaining super admins.

### Tests

- [x] T111 [US9] [W11D] Add E2E test `tests/e2e/suites/admin/test_break_glass_recovery.py` per spec User Story 9 acceptance scenarios + plan.md research R7: place an emergency-key file at the documented path (test fixture); run `platform-cli superadmin recover --username eve --email eve@example.com`; verify (a) super admin `eve` is created; (b) audit chain has `platform.superadmin.break_glass_recovery` entry with `severity=critical`; (c) every remaining super admin receives a notification via every configured channel; (d) `eve` first login sees the FR-568 first-install checklist + MFA enrollment is mandatory per spec User Story 9 acceptance scenario 4; (e) recovery without the emergency key file is REJECTED with clear error and exit code 2.

---

## Phase 15: User Story 10 — Embedded Grafana Panels (P3)

**Story goal**: `/admin/health` and Observability pages embed live Grafana panels via auth-proxied iframe; admin's tenant scope honoured.

### Tests

- [x] T112 [US10] [W11D] Add E2E test `tests/e2e/suites/admin/test_grafana_embed.py` per spec User Story 10 acceptance scenarios: open `/admin/health`; verify (a) the embedded Grafana panel for Platform Overview displays without a separate Grafana login; (b) the iframe URL uses the auth-proxy `/api/admin/grafana-proxy/...` from T066; (c) `Content-Security-Policy: frame-ancestors 'self'` header is set on the proxy response; (d) regular admin sees tenant-scoped data, super admin sees all-tenants data per FR-580; (e) when Grafana is unreachable (test fixture scales it down), the panel renders the graceful-degrade `<a>` link.

---

## Phase 16: Polish + Translation + Tour Integration

- [x] T113 [P] [W11C] Extract all admin strings into the next-intl catalog files at `apps/web/messages/{en,es,fr,de,ja,zh}/admin.json` per FR-489 + plan.md correction §6 (matches feature 083's i18n pattern). Coordinate translation vendor delivery early per plan.md risk-register row 6. Verify the constitution rule 38 translation drift CI check (owned by feature 083) passes.
- [x] T114 [P] [W11C] Wire `<AdminTour>` (T071) into `(admin)/page.tsx` (T080): on first login of a regular admin (NOT super admin per spec User Story 2 acceptance scenario 5), the tour runs once. The "tour completed" state is per-user (not session) — persisted to a small `users.tour_completed_at` column added in the T001 migration.
- [x] T115 [P] [W11C] Author inline help content for every admin page in `(admin)/<page>/help.tsx` per FR-569: each help component is a small component imported by the page; localized via next-intl. The `<AdminHelp>` component (T068) reads from this colocated content.

---

## Phase 17: J01 Extension + J18 New Journey (E2E)

- [x] T116 [W11D] Modify `tests/e2e/journeys/test_j01_admin_bootstrap.py` per FR-581: extend the existing journey (already extended in feature 085 / UPD-035 T081) to walk every admin section once, performing at least one representative action per section. Verify (a) every section's nav link works; (b) every page loads; (c) at least one representative action per section emits the expected audit chain entry; (d) axe-core scan returns zero AA violations on every visited admin page (per the existing axe-core gate from feature 083 / UPD-030 T028).
- [x] T117 [W11D] Author `tests/e2e/journeys/test_j18_super_admin_lifecycle.py` (NEW per FR-581 + plan.md design): the J18 super-admin journey exercising:
  1. Super admin logs in (bootstrapped via env vars from T013-T015's headless install).
  2. Completes the first-install checklist (T070).
  3. Creates a second tenant via `/admin/tenants/page.tsx` (T085 — `multi` mode required; toggles via T032).
  4. Configures platform settings via `/admin/settings/page.tsx` (T086).
  5. Schedules a maintenance window via `/admin/maintenance/page.tsx` (T088).
  6. Initiates a failover test via `/admin/regions/page.tsx` (T088); a second super admin approves via 2PA from a separate Playwright context (T098).
  7. Performs impersonation of a regular user; verifies the banner + audit (T101).
  8. Toggles read-only mode; verifies write actions are blocked (T107).
  9. Exports configuration as signed YAML bundle (T104).
  10. Verifies audit chain integrity post-session via `POST /api/v1/audit/verify`.
  ≥ 25 assertion points spanning the entire J18 flow. Uses Playwright's `axe-playwright-python` per FR-526 to scan every visited admin page.

---

## Phase 18: CI Gates (Constitutional Rule Enforcement)

- [x] T118 [W11D] Author the **Constitution Rule 30 static-analysis check** at `apps/control-plane/scripts/lint_admin_role_gates.py`: scans every `apps/control-plane/src/platform/*/admin_router.py` file using `ast` parser; for every method decorated with `@router.get/post/put/patch/delete`, asserts `Depends(require_admin)` OR `Depends(require_superadmin)` is in the dependency list; emits a clear error per missing gate; exits 1 if any miss. Registers this check in `.github/workflows/ci.yml` `lint-python` job (existing per feature 046) as an additional step.
- [x] T119 [W11D] Author the **Constitution Rule 31 secret-leak static-analysis check** at `apps/control-plane/scripts/lint_bootstrap_secrets.py`: scans `apps/control-plane/src/platform/admin/bootstrap.py` for any `logger.*` call that references `password`, `secret`, `password_file`, or any variable named `*_password` / `*_secret`; emits a clear error per match; exits 1 if any match. Registered in the same `lint-python` job.
- [x] T120 [W11D] Author the **OpenAPI tag verification** at `apps/control-plane/scripts/verify_admin_openapi_tags.py` per Constitution Rule 29: starts the FastAPI app in test mode; downloads the OpenAPI spec; asserts every operation under `/api/v1/admin/*` has the `admin` tag in its `tags` array; exits 1 on any miss. Registered in `lint-python` job.
- [x] T121 [W11D] Author the **per-page coverage check** at `tests/e2e/scripts/verify_admin_page_coverage.py`: parses the `specs/086-administrator-workbench-and/contracts/admin-page-inventory.md` (T004) for the canonical 57-page list; verifies every page has at least one assertion in `test_j18_super_admin_lifecycle.py` OR the extended `test_j01_admin_bootstrap.py` OR a `tests/e2e/suites/admin/` BC test. Fails CI if any page is uncovered per plan.md risk-register row 1.

---

## Phase 19: Documentation + Cross-Feature Coordination

- [x] T122 [P] [W11D] Author `specs/086-administrator-workbench-and/quickstart.md` — operator's "first 30 minutes" guide: run the headless install with `PLATFORM_SUPERADMIN_*` env vars, log in, complete the first-install checklist, configure tenant mode, create a second admin, run a 2PA action, end-to-end. Reuses the speckit `quickstart.md` convention from prior features.
- [x] T123 [P] [W11D] Author `specs/086-administrator-workbench-and/contracts/admin-action-impact-tiers.md` — the canonical confirmation-tier matrix per FR-577 (no-confirmation / simple / typed / 2PA). Lists every admin action with its tier; the brownfield input + spec edge-cases populate the initial entries; ongoing additions go here.
- [x] T124 [P] [W11D] Update `apps/ops-cli/README.md` — document the new `platform-cli superadmin` sub-app with examples for `recover` (break-glass) and `reset --force`; cross-link to the constitutional FR-579 contract.
- [x] T125 [P] [W11D] Update `deploy/helm/platform/README.md` (or create if absent) — document the headless-install path with `PLATFORM_SUPERADMIN_*` env vars; document the bootstrap Job's hook semantics; document the `passwordSecretRef` Helm value pattern.
- [x] T126 [P] [W11D] Update `CLAUDE.md` (project root) per the speckit convention: append "Active Technologies" section with feature 086's stack identifiers; append "Recent Changes" with a 1-2 line summary of UPD-036's contributions; record the 12 brownfield-input corrections from plan.md correction list as future-planner reference. Keep the file under the 200-line rule.
- [x] T127 [W11D] Author the **threat-model document** at `specs/086-administrator-workbench-and/contracts/threat-model.md` per plan.md risk-register row 3: enumerate the 2PA replay / race / expiry-edge-case attacks; the impersonation-abuse vectors; the bootstrap-secret-leak vectors; the read-only-bypass vectors. Each vector with attacker model + impact + mitigation. Reviewed by a separate engineer before merge per the brownfield input's security note.
- [ ] T128 [W11D] Cross-feature coordination follow-up: confirm with feature 027's owner that the `(main)/admin/` clean-cut + repointing of `<AdminSettingsPanel>` is approved (T086 deletes the old route); confirm with feature 014's owner that the `users.first_install_checklist_state` and `sessions.admin_read_only_mode` column additions are approved; confirm with feature 045's owner that the new `superadmin` Typer sub-app is approved as a sibling to the existing `admin` sub-app. Record the sign-offs in this task's commit message.

---

## Task Count Summary

| Phase | Range | Count | Wave | Parallelizable |
|---|---|---|---|---|
| Phase 1 — Setup | T001-T004 | 4 | W11A.0 | yes (T002-T004) |
| Phase 2 — Track A Bootstrap (US1 MVP) | T005-T015 | 11 | W11A.1-W11A.2 | mostly sequential |
| Phase 3 — Track B Composition + Cross-cutting | T016-T033 | 18 | W11B.1 | mostly yes |
| Phase 4 — Per-BC admin routers + Cross-BC routes + WebSocket | T034-T056 | 23 | W11B.2-W11B.4 | yes (13 BCs parallel) |
| Phase 5 — Track C Foundational components + stores | T057-T073 | 17 | W11C.1 | yes (14 components parallel) |
| Phase 6 — US1 P1 MVP verification | T074-T077 | 4 | W11D.0 | mostly parallel |
| Phase 7 — US2 P1 First-install checklist | T078-T083 | 6 | W11C.2 + W11D.1 | partially |
| Phase 8 — US3 P1 Tenant-scoped admin (10 sections) | T084-T094 | 11 | W11C.3 + W11D.2 | yes (10 sections parallel) |
| Phase 9 — US4 P1 2PA failover | T095-T098 | 4 | W11C.4 + W11D.3 | partially |
| Phase 10 — US5 P2 Impersonation | T099-T101 | 3 | W11C.5 + W11D.4 | partially |
| Phase 11 — US6 P2 Config export/import | T102-T104 | 3 | W11C.6 + W11D.5 | partially |
| Phase 12 — US7 P3 Read-only mode | T105-T107 | 3 | W11C.7 + W11D.6 | partially |
| Phase 13 — US8 P3 Bulk action | T108-T110 | 3 | W11C.8 + W11D.7 | partially |
| Phase 14 — US9 P3 Break-glass | T111 | 1 | W11D.8 | n/a |
| Phase 15 — US10 P3 Embedded Grafana | T112 | 1 | W11D.9 | n/a |
| Phase 16 — Polish + Translation + Tour | T113-T115 | 3 | W11C.9 | yes |
| Phase 17 — J01 + J18 E2E | T116-T117 | 2 | W11D.10 | partially |
| Phase 18 — CI gates | T118-T121 | 4 | W11D.11 | yes |
| Phase 19 — Docs + cross-feature coordination | T122-T128 | 7 | W11D.12 | yes |
| **Total** | | **128** | | |

## MVP Definition

**The MVP is US1 (Phase 2 + Phase 6 — headless bootstrap completes on a fresh kind cluster with idempotency + safety rails verified).** Without US1, every subsequent US is unreachable (no super admin → no admin login → no workbench access). After US1 lands, US2 (first-install checklist) and US3 (tenant-scoped pages) are the next P1 must-haves; US4 (2PA failover) is the P1 critical-action contract proof.

## Dependency Notes

- **T001 (Alembic migration) → all of W11B + W11C**: every cross-cutting primitive needs the new tables / columns.
- **T005-T015 (Track A bootstrap) → US1 verification (T074-T077) → US2 (first login)**: the bootstrap path must work before any super admin can log in.
- **T016-T033 (Track B foundational) → T034-T056 (per-BC routers)**: the composition layer + cross-cutting primitives are upstream of every admin endpoint.
- **T034-T056 (Track B routers) → T084-T094 (Track C pages)**: every page has at least one backing admin endpoint.
- **T057-T073 (Track C foundational) → T078-T093 (Track C pages)**: every page uses `<AdminLayout>` + `<AdminPage>` + `<AdminTable>`.
- **T020 (TwoPersonAuthService) → T095-T098 (US4 wiring)**: 2PA service is upstream of any 2PA-protected endpoint.
- **T023 (ImpersonationService) → T099-T101 (US5 wiring)**: same logic.
- **T025 (audit dual-principal logic) → all impersonated actions**: Constitution Rule 34 — every audit emit during impersonation must include both principals.
- **T118 (Constitution Rule 30 static-analysis) → T034-T046 (per-BC routers)**: the gate must pass on every PR adding a new admin endpoint.
- **All UPD-023 through UPD-035 features → W11**: UPD-036 is the post-audit-pass capstone; every BC's existing `service.py` + `router.py` is the basis for the admin router.

## Constitutional Audit Matrix

| Constitution rule | Verified by | Phase |
|---|---|---|
| Rule 29 — admin endpoint segregation | T120 OpenAPI tag verification | Phase 18 |
| Rule 30 — every admin endpoint declares a role gate | T118 static-analysis check | Phase 18 |
| Rule 31 — no logging of bootstrap secrets | T119 secret-leak static-analysis check | Phase 18 |
| Rule 32 — bootstrap idempotency | T006 + T074-T076 E2E tests | Phase 2 + 6 |
| Rule 33 — 2PA enforced server-side | T020 `validate_token()` re-validation + T098 negative tests | Phase 3 + 9 |
| Rule 34 — impersonation double-audits | T025 audit append change + T101 dual-principal assertion | Phase 3 + 10 |
| Rule 41 — Vault failure does not bypass auth | (delegated — UPD-036 does not change Vault) | n/a |
| FR-488 + FR-489 (a11y + i18n) | T113 i18n catalog + T117 J18 axe scan | Phase 16 + 17 |
| FR-526 — axe-core CI gate | T116 + T117 (extended J01 + J18) | Phase 17 |
| FR-565 — `/api/v1/admin/*` segregated | T120 OpenAPI tag verification | Phase 18 |
| FR-573 — admin session security | T018 read-only middleware + T064/T105 toggle requires MFA step-up | Phase 3 + 12 |
| FR-583 — structured error responses | T017 RBAC dependency + every admin endpoint | Phase 3 |
| FR-585 — tenant mode switch | T032 + T033 + bootstrap exemption | Phase 3 |
| Wave 11 capstone | All tasks tagged W11A / W11B / W11C / W11D | All |
