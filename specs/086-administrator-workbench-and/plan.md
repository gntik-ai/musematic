# Implementation Plan: UPD-036 — Administrator Workbench and Super Admin Bootstrap

**Branch**: `086-administrator-workbench-and` | **Date**: 2026-04-27 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

UPD-036 is the **first feature of platform v1.3.0** (Constitution lines 6, 40, 110, 476) and the largest feature in the UPD-036–UPD-045 cohort by surface area (57 admin pages + matching API surface across 13 bounded contexts + a new headless-bootstrap path + 4 cross-cutting admin primitives). It is delivered in three parallelizable tracks that converge for end-to-end validation:

- **Track A — Headless super-admin bootstrap and CLI break-glass** (smallest, unblocks GitOps deployments): `bootstrap_superadmin_from_env()` startup hook in a new `apps/control-plane/src/platform/admin/` composition layer (this is **NOT** a bounded context — it is a thin composition + cross-cutting layer per the brownfield design); Helm values block (`superadmin:`, `platformInstanceName:`, `tenantMode:`) added to the existing `deploy/helm/platform/values.yaml`; a new `templates/platform-bootstrap-job.yaml` with `post-install` Helm hook (the chart currently has zero pre-install / post-install hooks per the inventory); and a new `platform-cli superadmin` top-level Typer sub-app (NOT under the existing `admin` sub-app at `commands/admin.py:25-180` — the existing `admin` sub-app stays for tenant-scoped user-management commands; `superadmin` is a sibling per the established `app.add_typer(name=…)` pattern at `apps/ops-cli/src/platform_cli/main.py:71-76`).
- **Track B — Admin REST API surface** (medium, can land before UI): the composition layer at `apps/control-plane/src/platform/admin/` mounts a top-level admin router at `/api/v1/admin/*` and registers per-BC `admin_router.py` modules added to each of 13 BCs (auth, accounts, workspaces, policies, connectors, privacy_compliance, security_compliance, cost_governance, multi_region_ops, model_catalog, notifications, incident_response, audit). Cross-cutting primitives shipped here: `require_admin` / `require_superadmin` FastAPI dependencies (extending the existing `_require_platform_admin()` pattern at `auth/router.py:54-58`), `AdminReadOnlyMiddleware` (registered ABOVE the existing `AuthMiddleware` at `apps/control-plane/src/platform/common/auth_middleware.py`), `TwoPersonAuthService` + router, `ImpersonationService` + router, `ChangePreview` primitives, `ActivityFeed` audit-aggregation read model, `installer_state.py` reading from the audit chain.
- **Track C — Next.js admin workbench UI** (largest, most parallelizable): a NEW top-level route group `apps/web/app/(admin)/` (sibling to existing `(auth)` and `(main)`) with 57 enumerated pages organised into 10 functional sections (FR-548 through FR-557); 14 shared components under `apps/web/components/features/admin/` (siblings to the existing `AdminSettingsPanel` from feature 027); the existing `apps/web/app/(main)/admin/` directory from feature 027 is **removed** (clean cut for v1.3.0 — the absorbed settings content moves to `(admin)/settings/page.tsx`, the existing `AdminSettingsPanel` at `apps/web/components/features/admin/AdminSettingsPanel.tsx` is repointed but stays); WebSocket subscriptions for real-time updates extend the existing `ws_hub/subscription.py:11-50` `ChannelType` enum with admin-scoped channels.

All three tracks converge in Phase 10 for E2E coverage: the J01 Platform Administrator journey (already extended in feature 085 / UPD-035) is extended further to walk every admin section; a NEW J18 Super Admin Platform-Lifecycle journey exercises the headless bootstrap, first-install checklist, tenant creation, 2PA, impersonation, read-only mode, configuration export/import, break-glass simulation, and audit chain integrity verification.

## Constitutional Anchors

This plan is bounded by the following Constitution articles. Each implementation step below cites the article it serves.

| Anchor | Citation | Implementation tie |
|---|---|---|
| **UPD-036 declared** | Constitution lines 6, 40, 110, 476 (audit-pass roster + v1.3.0 first feature) | The whole feature |
| **Rule 29 — Admin endpoint segregation** | Constitution lines 193-197 | All admin endpoints under `/api/v1/admin/*`, separate OpenAPI tag, separate rate-limit group (T013) |
| **Rule 30 — Every admin endpoint declares a role gate** | Constitution lines 198-202 | Every method in every `admin_router.py` MUST depend on `require_admin` or `require_superadmin`; CI static-analysis check fails the build if any method is missing the gate (T088) |
| **Rule 31 — No logging of bootstrap secrets** | Constitution lines 203-207 | `bootstrap.py` (T002) routes all secret-bearing branches through a no-log decorator; structlog redaction patterns from feature 084 catch any accidental leak (T009) |
| **Rule 32 — Bootstrap idempotency** | Constitution lines 208-212 | `bootstrap_superadmin_from_env()` is idempotent (T003); `--force-reset-superadmin` is gated by `ALLOW_SUPERADMIN_RESET=true` in production (T005) |
| **Rule 33 — 2PA enforced server-side** | Constitution lines 213-216 | `TwoPersonAuthService.validate_token()` re-validates at apply-time (T015); the client UI is informed of the requirement but never gates alone |
| **Rule 34 — Impersonation double-audits** | Constitution lines 217-221 | `ImpersonationService` injects both principals into the request context; every audit-emit during the impersonation session writes both `impersonation_user_id` and `effective_user_id` (T020) |
| **FR-004 / FR-004a / FR-004b** | FR document lines 93-116 | Track A entire surface |
| **FR-012 — RBAC roles incl. `superadmin`** | FR document lines 169-182 | The `RoleType.SUPERADMIN` enum value at `auth/schemas.py:21-33` is the canonical role; UPD-036 enforces it at admin-API + admin-UI layer-0 boundaries |
| **FR-488 (WCAG AA), FR-489 (i18n), FR-490 (theming)** | feature 083 / UPD-030 contracts | Workbench inherits axe-core CI gate (T087), next-intl translation drift check (T078), theming via the established next-themes wiring at `apps/web/app/layout.tsx:17` |
| **FR-526 — axe-core CI gate** | feature 085 / UPD-035 contract (T062) | J18 + extended J01 journeys add the workbench's pages to the existing axe-core scan |
| **FR-561 (2PA)** | FR doc lines 2049-2050 | T013-T016 codify the contract |
| **FR-562 (impersonation)** | FR doc lines 2052-2053 | T017-T020 codify the contract |
| **FR-563 (read-only mode)** | FR doc lines 2055-2056 | T011-T012 codify the contract |
| **FR-579 (break-glass)** | FR doc lines 2146-2147 | T010 (CLI) + T011 (emergency-key check) codify the contract |

## Technical Context

| Item | Value |
|---|---|
| **Languages** | Python 3.12+ (control plane + CLI), TypeScript 5.x strict (frontend), YAML (Helm + GitHub Actions). No Go in this feature. |
| **Primary Dependencies (existing — reused)** | Python: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async (`audit_chain_entries`, `user_roles`, `users`, `sessions` tables — already in features 014/074), Alembic 1.13+, aiokafka 0.11+ (audit + auth events), structlog (feature 084's logging contract — UPD-036 inherits), PyJWT 2.x RS256 (auth/dependencies pattern at `common/dependencies.py:38-66`). Typer 0.12+ (CLI extension at `commands/admin.py:25-180` and `main.py:71-76`). Frontend: Next.js 14+ App Router, React 18+, shadcn/ui (ALL primitives reused), Tailwind 3.4+, TanStack Query v5, Zustand 5.x (existing `store/auth-store.ts:17-74`), React Hook Form 7.x + Zod 3.x, next-intl (feature 083's wiring), next-themes 0.4.4 (already at `apps/web/app/layout.tsx:17`), `cmdk` 1.0.0 (existing command palette at `components/layout/command-palette/CommandPaletteProvider.tsx`). |
| **Primary Dependencies (NEW in 086)** | None. Every dependency required by the workbench (TanStack Query, RHF+Zod, shadcn/ui, Recharts, etc.) is already installed per feature 015 + 083 + 085 inventories. |
| **Storage** | PostgreSQL — 2 NEW tables via Alembic migration `065_admin_workbench.py`: `two_person_auth_requests` (FR-561 — request_id, action, payload, initiator_id, created_at, expires_at, approved_by_id, approved_at, rejected_by_id, rejected_at, rejection_reason, consumed) and `impersonation_sessions` (FR-562 — session_id, impersonating_user_id, effective_user_id, justification, started_at, expires_at, ended_at, end_reason). Plus 1 column added to existing `users` table (`first_install_checklist_state` JSONB) for the FR-568 checklist persistence. No new Redis keys (2PA uses PostgreSQL with a 60-second polling scanner; impersonation uses PostgreSQL session-row TTL). One new Kafka topic — `admin.events` for events that have no current Kafka home (e.g., `admin.bootstrap.completed`, `admin.tenant_mode.changed`); existing `auth.events` topic is reused for events that overlap with auth scope. See correction §6. |
| **Testing** | pytest 8.x + pytest-asyncio for control-plane and per-BC `admin_router.py` tests; Vitest + React Testing Library for component tests; Playwright for J18 E2E (extends feature 085's harness at `tests/e2e/journeys/`); axe-playwright-python for J18 + extended J01 accessibility scans; Helm unittest for the new `platform-bootstrap-job.yaml` template. |
| **Target Platform** | The bootstrap path runs on every supported deployment topology (kind for E2E, k3s, managed Kubernetes — GKE/EKS/AKS); the workbench UI runs in any modern browser at desktop viewport (FR-582 — tablet ≥ 768 px is read-mostly). |
| **Project Type** | Composition + UI feature. No new BC. UPD-036 owns the `apps/control-plane/src/platform/admin/` thin composition + cross-cutting layer + the `(admin)` Next.js route group + the `superadmin` CLI sub-app + the bootstrap Helm Job. |
| **Performance Goals** | Headless bootstrap completes in ≤ 5 min (SC-001). Admin landing-page real-time counters update within 2s of underlying event (SC-018). Workbench routes render their primary table within 800 ms p95 against seeded test data (per feature 015's existing data-table SLO). 2PA scanner cycle ≤ 60 s (request expiry granularity). |
| **Constraints** | Constitution rules 29-34 enumerated in the anchors table; FR-573 stricter admin session security (idle timeout default 30 min, configurable down to 5 min; MFA step-up for destructive actions; IP+UA session binding); FR-583 structured error responses (machine code, human message, suggested action, correlation ID — plumbed through every admin endpoint); FR-575 deep-linking and breadcrumbs MUST work for every admin URL. |
| **Scale / Scope** | Track A: 1 startup hook + 1 Helm Job + 4 Helm values keys + 2 CLI commands. Track B: 1 composition module + 9 cross-cutting modules (rbac.py, two_person_auth_service.py, two_person_auth_router.py, impersonation_service.py, impersonation_router.py, read_only_middleware.py, change_preview.py, activity_feed.py, installer_state.py, bootstrap.py, feature_flags_service.py, settings_router.py, tenant_mode_service.py) + 13 per-BC `admin_router.py` files + 2 PostgreSQL tables + 1 Alembic migration. Track C: 1 new route group + 1 layout + 57 page files + 14 shared components + admin search palette + first-install checklist + tour + 6-locale i18n strings. |

## Constitution Check

> **GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.**

| Check | Verdict | Rationale |
|---|---|---|
| Brownfield rule — modifications respect existing BC boundaries | ✅ Pass | UPD-036 adds `admin_router.py` per BC (additive — does not modify the BC's `service.py` or `router.py`) and creates a thin composition layer at `apps/control-plane/src/platform/admin/` (NOT a new BC — declared explicitly per the brownfield input). |
| Rule 29 — admin endpoint segregation | ✅ Pass | All admin endpoints under `/api/v1/admin/*` (T013); OpenAPI tag `admin` segregates them; rate-limit group `admin` is registered separately (T013) per FR-566. |
| Rule 30 — every admin endpoint declares a role gate | ✅ Pass (CI-enforced) | T088 ships the static-analysis check — a CI job fails the build if any method in any `admin_router.py` is missing `Depends(require_admin)` or `Depends(require_superadmin)`. |
| Rule 31 — no logging of bootstrap secrets | ✅ Pass | T002 implements `bootstrap.py` with explicit no-log of every secret-bearing variable; T009's CI check verifies via structlog redaction patterns from feature 084 + a static-analysis pass over `bootstrap.py` searching for any `.password` / `.secret` reference inside a `logger.*` call. |
| Rule 32 — bootstrap idempotency | ✅ Pass | T003's idempotency check is the canonical contract; T005 implements the `--force-reset-superadmin` + `ALLOW_SUPERADMIN_RESET=true` gate. |
| Rule 33 — 2PA enforced server-side | ✅ Pass | `TwoPersonAuthService.validate_token()` (T015) is called fresh at apply-time on every protected endpoint; the client UI is informational-only. |
| Rule 34 — impersonation double-audits | ✅ Pass | `ImpersonationService` (T017) injects both principals into request context; `AuditChainService.append()` calls (T019) include both fields whenever an impersonation session is active. |
| Rule 41 — Vault failure does not bypass auth | ✅ N/A | UPD-036 does not change the Vault contract (the constitutional Vault paths from features 077/078/080 are unaffected). |
| FR-488 + FR-489 (a11y + i18n) | ✅ Pass (delegated) | Workbench inherits feature 083's next-intl + axe-core gate; UPD-036 adds the strings to the catalog (T078) and adds workbench pages to the J15/J18 axe scan (T087). |
| FR-526 — axe-core CI gate | ✅ Pass | J18 + extended J01 journeys (T081-T082) include axe-core scans on every visited admin page; the gate from feature 085 / UPD-035 is reused. |
| FR-565 — `/api/v1/admin/*` segregated in OpenAPI | ✅ Pass | T013 sets the OpenAPI `tags=["admin"]` on every admin route; T088's static-analysis check verifies no admin route is missing the tag. |
| FR-573 — admin session security stricter than user sessions | ✅ Pass | T010 implements admin-specific session config (idle timeout 30 min default, MFA step-up gate, IP+UA binding) leveraging the existing session table from feature 014. |

**Verdict: gate passes. No declared variances. Constitution rules 29-34 are this feature's canonical contract — every relevant task cites the rule it serves.**

## Project Structure

### Documentation (this feature)

```text
specs/086-administrator-workbench-and/
├── plan.md                # this file
├── spec.md
├── planning-input.md
└── tasks.md               # produced by /speckit.tasks (next phase)
```

### Source Code (repository root) — files this feature creates or modifies

```text
apps/control-plane/src/platform/
├── admin/                                       # NEW composition layer (NOT a BC)
│   ├── __init__.py                              # NEW
│   ├── router.py                                # NEW (top-level admin router mounting per-BC admin routers)
│   ├── rbac.py                                  # NEW (require_admin + require_superadmin dependencies — extending the existing `_require_platform_admin` pattern at `auth/router.py:54-58`)
│   ├── two_person_auth_service.py               # NEW (FR-561 — name corrected from brownfield's `2pa_service.py` per spec correction §4)
│   ├── two_person_auth_router.py                # NEW
│   ├── two_person_auth_models.py                # NEW (SQLAlchemy `TwoPersonAuthRequest`)
│   ├── impersonation_service.py                 # NEW (FR-562)
│   ├── impersonation_router.py                  # NEW
│   ├── impersonation_models.py                  # NEW (SQLAlchemy `ImpersonationSession`)
│   ├── read_only_middleware.py                  # NEW (FR-563 — `AdminReadOnlyMiddleware`)
│   ├── change_preview.py                        # NEW (FR-560 shared dry-run primitives)
│   ├── activity_feed.py                         # NEW (FR-567 — read-side aggregation over `audit_chain_entries`)
│   ├── installer_state.py                       # NEW (FR-556 — reads `platform.superadmin.bootstrapped` audit entries)
│   ├── bootstrap.py                             # NEW (FR-004 — `bootstrap_superadmin_from_env()` startup hook + CLI entrypoint)
│   ├── feature_flags_service.py                 # NEW (FR-578 — global / tenant / workspace / per-user flag granularity over the existing platform-settings store)
│   ├── settings_router.py                       # NEW (FR-550 — platform settings GET/PUT with diff audit)
│   └── tenant_mode_service.py                   # NEW (FR-585 — single ↔ multi switch with 2PA gate + downgrade-blocking check)
│
├── auth/
│   ├── admin_router.py                          # NEW (FR-548 — users, roles, groups, sessions, oauth-providers, ibor, api-keys)
│   └── service.py                               # MODIFY (add `force_password_change` flag handling for FR-573 first-login flow if not already present from feature 014)
├── accounts/
│   └── admin_router.py                          # NEW (`/api/v1/admin/api-keys`)
├── workspaces/
│   └── admin_router.py                          # NEW (`/api/v1/admin/workspaces`, `tenants`, `namespaces`, `quotas`)
├── policies/
│   └── admin_router.py                          # NEW
├── connectors/
│   └── admin_router.py                          # NEW
├── privacy_compliance/
│   └── admin_router.py                          # NEW (DSR queue / DLP rules / PIA review / consent records)
├── security_compliance/
│   └── admin_router.py                          # NEW (SBOM / scans / pentests / rotations / JIT / audit chain query)
├── cost_governance/
│   └── admin_router.py                          # NEW (budgets / chargeback / anomalies / forecasts / rates)
├── multi_region_ops/
│   └── admin_router.py                          # NEW (regions / replication / maintenance / failover — failover wraps in 2PA per FR-561)
├── model_catalog/
│   └── admin_router.py                          # NEW (catalog CRUD / cards / fallback policies)
├── notifications/
│   └── admin_router.py                          # NEW (channels / webhooks / templates / integrations)
├── incident_response/
│   └── admin_router.py                          # NEW (incidents / runbooks / post-mortems)
├── audit/
│   └── admin_router.py                          # NEW (audit query and signed export)
│
├── ws_hub/
│   └── subscription.py                          # MODIFY (extend `ChannelType` enum at lines 11-50 with admin-scoped channels: ADMIN_HEALTH, ADMIN_INCIDENTS, ADMIN_QUEUES, ADMIN_WARM_POOL, ADMIN_MAINTENANCE, ADMIN_REGIONS; extend CHANNEL_TOPIC_MAP)
│
├── common/
│   ├── auth_middleware.py                       # MODIFY (no behaviour change; added test for AdminReadOnlyMiddleware ordering)
│   └── app_factory.py                           # MODIFY (register `AdminReadOnlyMiddleware` ABOVE `AuthMiddleware` per the brownfield design's middleware stack)
│
└── main.py                                      # MODIFY (call `bootstrap_superadmin_from_env()` from FastAPI lifespan; register the admin top-level router; register all 13 per-BC admin routers per the existing pattern at lines 1569-1615)

apps/control-plane/migrations/
└── versions/
    └── 065_admin_workbench.py                   # NEW (Alembic — `two_person_auth_requests` + `impersonation_sessions` tables + `users.first_install_checklist_state` column)

apps/ops-cli/src/platform_cli/
├── main.py                                      # MODIFY (add `app.add_typer(superadmin_app, name="superadmin")` after the existing `admin_app` registration at line 75)
└── commands/
    └── superadmin.py                            # NEW (FR-579 break-glass `recover` + FR-004b `reset --force` commands)

deploy/helm/platform/
├── values.yaml                                  # MODIFY (add `superadmin:` block, `platformInstanceName`, `tenantMode` per the brownfield input)
└── templates/
    └── platform-bootstrap-job.yaml              # NEW (`post-install` Helm hook — runs `bootstrap_superadmin_from_env()` after migrations)

apps/web/app/
├── (admin)/                                     # NEW route group (sibling to `(auth)` and `(main)`)
│   ├── layout.tsx                               # NEW (server-side role gate — return 403 page on deep link, NOT client-side redirect; layout shell with header + sidebar)
│   ├── page.tsx                                 # NEW (FR-547 landing dashboard with real-time counters + activity feed + first-install checklist render conditional)
│   ├── 403/page.tsx                             # NEW (the 403 page rendered when a non-admin / non-super-admin hits an admin route)
│   ├── users/{page.tsx, [id]/page.tsx}          # NEW (2 files)
│   ├── roles/{page.tsx, [id]/page.tsx}          # NEW (2 files)
│   ├── groups/page.tsx                          # NEW
│   ├── sessions/page.tsx                        # NEW
│   ├── oauth-providers/page.tsx                 # NEW
│   ├── ibor/{page.tsx, [connector_id]/page.tsx} # NEW (2 files)
│   ├── api-keys/page.tsx                        # NEW
│   ├── tenants/{page.tsx, [id]/page.tsx}        # NEW (super-admin-only — guarded at server)
│   ├── workspaces/{page.tsx, [id]/page.tsx, [id]/quotas/page.tsx}   # NEW (3 files)
│   ├── namespaces/page.tsx                      # NEW
│   ├── settings/page.tsx                        # NEW (absorbs the feature 027 settings — repoints `<AdminSettingsPanel>`)
│   ├── feature-flags/page.tsx                   # NEW
│   ├── model-catalog/{page.tsx, [id]/page.tsx}  # NEW (2 files)
│   ├── policies/page.tsx                        # NEW
│   ├── connectors/page.tsx                      # NEW
│   ├── audit-chain/page.tsx                     # NEW
│   ├── security/{sbom, pentests, rotations, jit}/page.tsx           # NEW (4 files)
│   ├── privacy/{dsr, dlp, pia, consent}/page.tsx                    # NEW (4 files)
│   ├── compliance/page.tsx                      # NEW
│   ├── health/page.tsx                          # NEW
│   ├── incidents/{page.tsx, [id]/page.tsx}      # NEW (2 files)
│   ├── runbooks/{page.tsx, [id]/page.tsx}       # NEW (2 files)
│   ├── maintenance/page.tsx                     # NEW
│   ├── regions/page.tsx                         # NEW (super-admin-only)
│   ├── queues/page.tsx                          # NEW
│   ├── warm-pool/page.tsx                       # NEW
│   ├── executions/page.tsx                      # NEW
│   ├── costs/{overview, budgets, chargeback, anomalies, forecasts, rates}/page.tsx   # NEW (6 files)
│   ├── observability/{dashboards, alerts, log-retention, registry}/page.tsx          # NEW (4 files)
│   ├── integrations/{webhooks, incidents, notifications, a2a, mcp}/page.tsx         # NEW (5 files)
│   ├── lifecycle/{version, migrations, backup, installer}/page.tsx                  # NEW (4 files — super-admin-only)
│   └── audit/{page.tsx, admin-activity/page.tsx}                    # NEW (2 files)
│
├── (main)/admin/                                # REMOVE (clean cut for v1.3.0)
│   ├── layout.tsx                               # DELETE
│   └── settings/page.tsx                        # DELETE (content migrated to (admin)/settings/page.tsx)
│
└── api/admin/                                   # NEW Next.js API routes for the auth-proxy that the embedded Grafana iframe uses
    └── grafana-proxy/[...path]/route.ts         # NEW (FR-580 auth-proxy)

apps/web/components/features/admin/
├── AdminLayout.tsx                              # NEW (top bar + sidebar + breadcrumb)
├── AdminPage.tsx                                # NEW (page shell)
├── AdminTable.tsx                               # NEW (FR-576 standard data-table — pagination, sort, filter, search, CSV, saved views)
├── BulkActionBar.tsx                            # NEW (FR-559)
├── ChangePreview.tsx                            # NEW (FR-560)
├── TwoPersonAuthDialog.tsx                      # NEW (FR-561)
├── ImpersonationBanner.tsx                      # NEW (FR-562)
├── ReadOnlyIndicator.tsx                        # NEW (FR-563)
├── EmbeddedGrafanaPanel.tsx                     # NEW (FR-580 — iframe + auth-proxy)
├── ConfirmationDialog.tsx                       # NEW (FR-577 — tiered: simple / typed / 2PA)
├── AdminHelp.tsx                                # NEW (FR-569)
├── AdminCommandPalette.tsx                      # NEW (FR-558 — extends existing `cmdk`-based palette at `components/layout/command-palette/CommandPaletteProvider.tsx:18`)
├── FirstInstallChecklist.tsx                    # NEW (FR-568)
├── AdminTour.tsx                                # NEW (FR-568 — guided tour for regular admin first login)
├── AdminSettingsPanel.tsx                       # KEEP (from feature 027 — repointed by the new `(admin)/settings/page.tsx`)
├── shared/                                      # KEEP (from feature 027 — `SettingsFormActions.tsx`, `StaleDataAlert.tsx`)
├── tabs/                                        # KEEP
├── connectors/                                  # KEEP
└── users/                                       # KEEP (the existing user-management sub-components — repointed)

apps/web/lib/
├── api.ts                                       # MODIFY (no behaviour change; verify no admin-route is bypassed by skipAuth)
├── stores/admin-store.ts                        # NEW (Zustand — read-only mode, active impersonation session, 2PA notifications counter — separate from `auth-store`)
└── hooks/use-admin-mutations.ts                 # NEW (TanStack Query mutation hooks for every admin write action)

tests/e2e/journeys/
├── test_j01_admin_bootstrap.py                  # MODIFY (extend per FR-581 — visit every admin section once, perform 1 representative action per section)
└── test_j18_super_admin_lifecycle.py            # NEW (the new J18 super-admin journey per FR-581)

tests/e2e/suites/admin/                          # NEW directory
├── __init__.py                                  # NEW
├── test_role_gates.py                           # NEW (asserts every admin endpoint enforces `require_admin` or `require_superadmin`; the static-analysis result from T088 is the input here)
├── test_two_person_auth.py                      # NEW
├── test_impersonation.py                        # NEW
├── test_read_only_mode.py                       # NEW
├── test_bootstrap_env_vars.py                   # NEW
└── test_config_export_import.py                 # NEW

.github/workflows/
└── ci.yml                                       # MODIFY (add the T088 admin-route-audit static-analysis step to the existing `lint-python` job)
```

**Structure Decision**: UPD-036 follows the existing repo conventions: per-BC admin routers added as `admin_router.py` siblings to each BC's existing `router.py` (matching the brownfield input's design); a thin composition layer at `apps/control-plane/src/platform/admin/` (declared NOT to be a new BC); a new top-level Next.js route group `(admin)` (matching the existing `(auth)` and `(main)` pattern); and a new `superadmin` Typer sub-app (matching the existing `app.add_typer()` pattern at `apps/ops-cli/src/platform_cli/main.py:71-76`). No new BC. No new database (only 2 new tables + 1 column added to an existing table). One new Kafka topic (`admin.events`) per correction §6.

## Brownfield-Input Reconciliations

These are corrections from spec to plan. Each is an artifact-level discrepancy between the brownfield input and the on-disk codebase.

1. **Role names.** The brownfield input writes `admin` and `superadmin` casually; the canonical role enum at `apps/control-plane/src/platform/auth/schemas.py:21-33` has `RoleType.SUPERADMIN` and `RoleType.PLATFORM_ADMIN` (NOT `RoleType.ADMIN`). The existing `_require_platform_admin()` at `auth/router.py:54-58` accepts the JWT-claim string `"platform_admin"` OR `"superadmin"`. **Resolution:** UPD-036's `require_admin` (T012) accepts users whose JWT claims include `"platform_admin"` OR `"superadmin"`; `require_superadmin` accepts only `"superadmin"`. The plan and tasks consistently use the canonical enum names; the brownfield-input "admin" wording is treated as shorthand for "platform_admin OR superadmin" per the existing convention.

2. **`(main)/admin/` clean-cut.** The brownfield input nominates `apps/web/app/(admin)/` as a new route group; the on-disk codebase has `apps/web/app/(main)/admin/` from feature 027 with: `layout.tsx` (16-line client-side guard checking roles via `useAuthStore`) and `settings/page.tsx` (18-line wrapper around `<AdminSettingsPanel>`). **Resolution:** UPD-036 creates a new top-level `(admin)` route group, MOVES the `<AdminSettingsPanel>` reference into `(admin)/settings/page.tsx`, and DELETES `(main)/admin/` entirely (no backwards-compat redirect — clean cut, v1.3.0). The existing `apps/web/components/features/admin/AdminSettingsPanel.tsx` and its `shared/` / `tabs/` / `users/` / `connectors/` sub-components are KEPT (repointed by the new settings page).

3. **2PA module filenames.** Brownfield input has `2pa_service.py` and `2pa_router.py` — Python module names cannot start with a digit. **Resolution:** Canonical filenames are `two_person_auth_service.py`, `two_person_auth_router.py`, `two_person_auth_models.py` (already corrected in the spec).

4. **Bootstrap startup hook timing.** Brownfield input says `bootstrap_superadmin_from_env()` "runs once on startup". **Resolution:** It runs inside FastAPI's `lifespan` async context manager (the established pattern in `main.py`), gated on `os.getenv("PLATFORM_SUPERADMIN_USERNAME")` being non-empty. Without the env var, the function is a no-op — preserving the existing CLI-bootstrap path. With the env var, the function runs ONCE per pod startup; the idempotency check (T003) ensures multi-pod / restart scenarios do not duplicate-create. The same `bootstrap.py` module exposes a CLI entrypoint via `python -m platform.admin.bootstrap` so the Helm Job can invoke it without spinning up the full FastAPI app.

5. **Helm Job + hooks.** Brownfield input does NOT specify Helm hook semantics; the on-disk chart at `deploy/helm/platform/templates/` has zero existing pre-install / post-install hooks (verified by inventory). **Resolution:** UPD-036 adds the bootstrap as the FIRST Helm hook in this chart — `templates/platform-bootstrap-job.yaml` with `helm.sh/hook: post-install,post-upgrade` and `helm.sh/hook-weight: "10"`. The Job runs the control-plane image with command `python -m platform.admin.bootstrap`. The Job has `helm.sh/hook-delete-policy: before-hook-creation,hook-succeeded` so re-runs do not accumulate stale Job objects. (Note: this is `post-install` — NOT `pre-install` — because the database migrations Job must complete first; running bootstrap before migrations would fail because the `users` table does not yet exist.)

6. **No `admin.events` Kafka topic exists.** Brownfield input does not specify; inventory confirms the constitutional Kafka topic registry has no `admin.events` topic. **Resolution:** UPD-036 emits admin-action events to (a) `AuditChainService.append()` for the canonical audit chain (PostgreSQL append-only) — this is the source of truth; AND (b) the existing `auth.events` Kafka topic for events that overlap with auth scope (e.g., `admin.user.suspended` is auth-scope-relevant). For events that have no current Kafka home (e.g., `admin.bootstrap.completed`, `admin.tenant_mode.changed`, `admin.2pa.requested`, `admin.impersonation.started`), UPD-036 introduces a new `admin.events` topic — added to the constitutional Kafka registry as part of the constitution-update side-effect of this feature. The spec's "no new Kafka topics" claim from the brownfield input is corrected: ONE new topic is added.

7. **Existing `admin` CLI sub-app at `commands/admin.py:25-180`.** Brownfield input writes `platform-cli superadmin recover` as if `superadmin` is a new top-level sub-app. The inventory confirms there is already a top-level `admin` sub-app (created by feature 045 / 048 — handles tenant-scoped `admin list`, `admin create`, `admin status`, `admin stop`). **Resolution:** UPD-036 adds `superadmin` as a NEW SIBLING top-level sub-app, NOT under `admin`. The registration at `apps/ops-cli/src/platform_cli/main.py:75` becomes:
```python
app.add_typer(admin_app, name="admin")          # existing
app.add_typer(observability_app, name="observability")  # existing (feature 085)
app.add_typer(superadmin_app, name="superadmin")  # NEW
```
This preserves the conceptual separation: `admin` = tenant-scoped operator commands; `superadmin` = platform-wide critical operations (break-glass + force-reset only).

8. **Role gate at the layout layer.** Brownfield input shows the route-group's `layout.tsx` performing a role gate; on-disk the existing `(main)/admin/layout.tsx:13-16` does this **client-side** via `useAuthStore`. **Resolution:** UPD-036's new `(admin)/layout.tsx` performs a **server-side** role gate (Next.js Server Component reading the JWT from the auth cookie / header) — required because the spec User Story 3 acceptance scenario 2 requires deep-link to a super-admin-only page to render a 403 page (NOT a client-side redirect, which is a different UX). The server-side check is the authoritative gate; the API-layer `require_admin` / `require_superadmin` dependencies are the second gate (defence in depth — Constitution Rule 30).

9. **57 pages, not "40+".** Spec correction §2 enumerates 57 pages. Plan adopts 57 as the canonical count. Tasks (T065-T074) split the page work across 10 sections matching FR-548 through FR-557.

10. **`AdminSettingsPanel` is KEPT.** Brownfield input's UI Implementation section lists 11 NEW shared admin components and writes that the workbench replaces feature 027 — implying `AdminSettingsPanel` is replaced. **Resolution:** the existing `AdminSettingsPanel` and its sub-components are KEPT (the contents continue to render via the new `(admin)/settings/page.tsx`); they are simply repointed. The 14 NEW shared components from the brownfield input + the design map are SIBLINGS to `AdminSettingsPanel`, NOT replacements.

11. **`first_install_checklist_state` column.** Brownfield input does not specify checklist persistence; spec User Story 2 requires it. **Resolution:** UPD-036 adds a `first_install_checklist_state` JSONB column on the existing `users` table (Alembic 065) — this is the smallest-surface change for per-super-admin checklist state. The column defaults to `null`; when the bootstrap super admin first logs in, the front-end populates it via `PATCH /api/v1/admin/users/me/checklist-state`.

12. **Admin-scoped WebSocket channels.** Brownfield input does not enumerate the admin channels; FR-564 enumerates the pages requiring real-time updates (dashboard landing, Incidents, Queue Health, Warm Pool, Maintenance, Multi-Region). **Resolution:** UPD-036 extends `ws_hub/subscription.py:11-50` `ChannelType` enum with: `ADMIN_HEALTH`, `ADMIN_INCIDENTS`, `ADMIN_QUEUES`, `ADMIN_WARM_POOL`, `ADMIN_MAINTENANCE`, `ADMIN_REGIONS`. The CHANNEL_TOPIC_MAP is extended with the corresponding Kafka topics (each admin channel maps to existing topics — e.g., `ADMIN_INCIDENTS` → `incident.triggered`, `incident.resolved`; the admin channel is just a scoped-fan-out view, NOT a new topic). All admin channels are added to a new set `ADMIN_SCOPED_CHANNELS` (mirroring `WORKSPACE_SCOPED_CHANNELS` at line 39-49); subscription requires the connecting user to have `platform_admin` or `superadmin` role (verified at WebSocket upgrade per the existing JWT-auth-on-upgrade contract from feature 019).

## Phase 0 — Research and Design Decisions

### R1. Server-side role gate vs. client-side role gate

Two competing patterns:
1. **Client-side**: `(main)/admin/layout.tsx:13-16` reads `useAuthStore` and redirects on miss (Next.js client-component pattern).
2. **Server-side**: `(admin)/layout.tsx` is a Next.js Server Component that reads the JWT from the auth cookie / header in `cookies()` / `headers()` and either renders the 403 page server-side or proceeds.

**Decision**: Server-side. The spec User Story 3 acceptance scenario 2 explicitly requires a 403 page (NOT a redirect) on deep link. The server-side approach is also the authoritative gate per Constitution Rule 30 (defence in depth combined with the API-layer `require_admin`/`require_superadmin` dependencies). The client-side `useAuthStore` is still used for navigation rendering (the sidebar hides super-admin-only sections for regular admins per FR-577 phrasing).

### R2. 2PA storage: PostgreSQL vs Redis

Two options for `TwoPersonAuthRequest` lifecycle:
1. **Redis with TTL**: `2pa:{request_id}` key with 15-minute TTL; auto-expiry on Redis side; pub/sub for cross-pod notifications.
2. **PostgreSQL with scanner**: `two_person_auth_requests` table; rows have `expires_at`; a 60-second background scanner marks expired requests; cross-pod notifications via Kafka.

**Decision**: PostgreSQL. Reasons: (a) audit chain tightly couples 2PA decisions to the `audit_chain_entries` table — same transaction boundary; (b) 60-second expiry granularity is acceptable per FR-561's "configurable window (default 15 minutes)" — ±60 s precision is fine; (c) PostgreSQL gives query-able history (rejected requests, audit trail of who rejected what); Redis would lose this. The scanner is implemented as an APScheduler background task (the established pattern in features 077/079/080).

### R3. Impersonation session storage: reuse `sessions` table or new table

Two options:
1. **Reuse the existing `sessions` table** (referenced at `auth/router.py:95`): add `impersonation_user_id` and `effective_user_id` columns; impersonation = a special session row.
2. **New `impersonation_sessions` table**: dedicated table with the dual-principal fields + justification + expiry.

**Decision**: New table. Reasons: (a) the existing `sessions` table is owned by feature 014 (Auth) and a column addition would expand its surface in a way feature 014's owners might not want; (b) the dual-principal pattern is unique to impersonation — bolt-on columns on a single-principal table are a smell; (c) the FR-562 contract names a distinct entity ("impersonation session"); (d) the new table is small (~10 columns); Alembic migration 065 is small. The session token issued for impersonation is a JWT with claim `impersonation_session_id` — the `get_current_user` dependency resolves the dual principals from this claim (T018).

### R4. Bootstrap idempotency check: PostgreSQL row vs audit chain query

Two options:
1. **Query `users` table**: `SELECT * FROM users WHERE username=$1 OR email=$2`; if row exists, skip.
2. **Query audit chain**: `SELECT * FROM audit_chain_entries WHERE event_type='platform.superadmin.bootstrapped' ORDER BY sequence_number DESC LIMIT 1`; if entry exists, skip.

**Decision**: Both — combined. Reasons: (a) the `users` table query is the authoritative existence check (the source of truth); (b) the audit chain query is the audit-trail check that records the bootstrap method (`env_var` vs `cli`). T003 implements the combined check: if user exists AND audit entry exists with `method=env_var` → no-op (the canonical idempotent re-run); if user exists but NO audit entry → write the audit entry (recovery path for an existing user that was created via CLI before audit-chain integration); if user does NOT exist → create user AND audit entry.

### R5. `--force-reset-superadmin` audit chain entry severity

The constitution at line 209 says "shall require confirmation and shall emit a critical audit chain entry". **Decision**: T005 emits the audit entry with `severity="critical"` and `event_type="platform.superadmin.force_reset"`; the audit-chain integrity verifier (feature 074 / UPD-024) treats `severity="critical"` entries as MUST-be-verifiable on every chain integrity check, NOT just on demand. This raises the bar — a `--force-reset-superadmin` in production is the most-audited operation in the platform.

### R6. Bootstrap secret handling — Helm Job command line vs env vars vs Secret mount

Three options:
1. **Command line args**: `python -m platform.admin.bootstrap --password "..."` — visible in `kubectl describe pod`.
2. **Env vars**: `PLATFORM_SUPERADMIN_PASSWORD=...` — visible in `kubectl describe pod` only if NOT marked `valueFrom.secretKeyRef`.
3. **Secret mount**: `PLATFORM_SUPERADMIN_PASSWORD_FILE=/run/secrets/superadmin-password` reading from a Kubernetes Secret mounted as a file; Secret content is never serialised in the pod spec.

**Decision**: #3 is the recommended path; #2 is supported with the Secret reference (`valueFrom.secretKeyRef`). Helm values `superadmin.passwordSecretRef` (per the brownfield input) is the documented production pattern. The `bootstrap.py` implementation reads `PLATFORM_SUPERADMIN_PASSWORD_FILE` first, then `PLATFORM_SUPERADMIN_PASSWORD` env var, then falls back to generated password. Constitution Rule 31 (no logging of bootstrap secrets) means: the password is read into a stack variable, used to compute the Argon2 hash, and the variable is overwritten with `\0`-bytes before the function returns (defence-in-depth — Python's GC may still hold a reference, but the immediate clearance reduces the attack window).

### R7. CLI break-glass emergency-key path

FR-579 requires "physical cluster access and a second-factor present on the cluster (e.g., a sealed emergency key)". Two implementation options:
1. **Filesystem path**: emergency key file at a documented cluster-host path (e.g., `/etc/musematic/emergency-key.bin`) — the CLI checks file existence + content hash.
2. **Kubernetes Secret**: Secret `platform-emergency-key` in `kube-system` namespace; the CLI's pod must have a ServiceAccount with permission to read it.

**Decision**: Filesystem path. Reasons: (a) FR-579 explicitly says "physical cluster access" — a filesystem path on a control-plane node is the canonical "physical cluster access" gate; a Kubernetes Secret can be exfiltrated by anyone with cluster API access (which is not "physical"); (b) the filesystem path is auditable at the host layer (auditd / file-integrity monitoring); (c) the operator workflow is: SRE custodian holds the sealed file; in emergency, they SSH to a control-plane node, place the file at the documented path, run `platform-cli superadmin recover`, then remove the file. T011 implements the file existence + SHA-256 content hash check.

### R8. Activity feed performance (FR-567)

The activity feed page renders the recent admin activity sorted by timestamp. Two query patterns:
1. **Direct query against `audit_chain_entries`**: `SELECT * FROM audit_chain_entries WHERE actor_role IN ('platform_admin','superadmin') ORDER BY created_at DESC LIMIT 50`.
2. **Materialised projection**: a `admin_activity_feed` projection table updated by a background worker consuming the audit-chain.

**Decision**: #1 with an index on `(actor_role, created_at DESC)`. Reasons: (a) the audit chain is append-only — the index is monotonically growing but never re-sorted; (b) the workbench's typical query is "last 50 in the last 24 hours" — bounded by both COUNT and TIME; (c) materialisation adds latency to audit emission and complexity for partial-recovery scenarios. The Alembic migration 065 adds the index. If the query degrades at scale (1M+ admin events / day), revisit with a projection (open question — see Q3).

### R9. Configuration export / import bundle format

FR-572 requires a "signed YAML bundle". Two options:
1. **Single YAML file** with all categories + a sidecar `.sig` file.
2. **Tarball** containing `config.yaml` + `manifest.json` (per-category file hashes) + `signature.bin`.

**Decision**: Option 2 — tarball. Reasons: (a) per-category hashing in `manifest.json` enables partial-verification (e.g., import only the policies + roles, not the connectors); (b) the manifest is signed once, the per-file hashes are verified individually — same pattern as feature 074's audit-evidence bundle; (c) the tarball format is well-known to operators and well-supported by tooling. T044 (config-import) verifies the signature against the source platform's public key (retrieved via `GET /api/v1/audit/public-key` from feature 074); T045 (config-export) writes the bundle.

### R10. Tenant-mode switch — single-to-multi vs multi-to-single

FR-585 requires the switch is gated by 2PA and downgrades from multi → single are blocked when > 1 tenant exists. **Decision**: T046 implements `tenant_mode_service.py` with two methods: `upgrade_to_multi()` (no entity-count check; opens the Tenants page and tenant-scoping UI) and `downgrade_to_single()` (rejects with the list of tenant IDs that must be removed first). Both methods require a 2PA token; the 2PA initiator is the super admin attempting the switch; the approver is any other super admin. The bootstrap exemption (only one super admin exists at first install) is handled in T046's pre-check.

## Phase 1 — Design

### Track A — Headless Bootstrap Architecture

```
Helm install:
  helm install platform ./deploy/helm/platform/ -f values-tenant.yaml
        │
        ├── 1. PostgreSQL migrations Job (existing — runs Alembic 065 adding the 2 new tables + 1 column)
        │
        └── 2. Helm post-install hook: platform-bootstrap-job.yaml (NEW)
                  │
                  └── runs: python -m platform.admin.bootstrap
                              │
                              ├── 1. Parse env vars (PLATFORM_SUPERADMIN_USERNAME, EMAIL, PASSWORD, PASSWORD_FILE, MFA_ENROLLMENT, FORCE_PASSWORD_CHANGE, INSTANCE_NAME, TENANT_MODE)
                              ├── 2. Validate (presence, exclusivity, RFC 5322 email format)
                              ├── 3. Idempotency check (users table + audit chain query)
                              ├── 4. If --force-reset-superadmin: gate by ALLOW_SUPERADMIN_RESET=true in production
                              ├── 5. Resolve password (PASSWORD_FILE > PASSWORD > generated 32-char urlsafe)
                              ├── 6. Argon2id-hash the password (existing argon2-cffi 23+ dep from feature 014)
                              ├── 7. Insert user into auth.users + auth.user_credentials + auth.user_roles (role=SUPERADMIN)
                              ├── 8. Set platform_settings.instance_name + platform_settings.tenant_mode
                              ├── 9. AuditChainService.append(event_type="platform.superadmin.bootstrapped", method="env_var", non_secret_payload)
                              ├── 10. If MFA_ENROLLMENT=required_before_first_login: generate TOTP secret, write to stdout exactly once with QR-code + manual key, mark user.mfa_pending=true
                              └── 11. Exit 0
```

**Key design point**: the bootstrap is idempotent at every step; any single step's failure leaves the database in a consistent state (transactional boundary around steps 7-9; steps 1-6 are read-only validation; steps 10-11 are post-commit logging that does not affect the user record's correctness if they fail — only the operator notification).

### Track B — Admin Composition Layer

```
                    ┌─────────────────────────────────────────────────────┐
                    │            FastAPI app (existing)                    │
                    │                                                      │
   request flow:    │  ┌────────────────────────────────────────────┐    │
   client ────────► │  │ Middleware stack (apps/control-plane/      │    │
                    │  │ src/platform/common/app_factory.py)         │    │
                    │  │                                             │    │
                    │  │   1. CorrelationLoggingMiddleware           │    │
                    │  │   2. ApiVersioningMiddleware                │    │
                    │  │   3. RateLimitMiddleware                    │    │
                    │  │   4. AdminReadOnlyMiddleware ◄───── NEW    │    │
                    │  │      (returns 403 on non-GET to            │    │
                    │  │       /api/v1/admin/* when read-only)       │    │
                    │  │   5. AuthMiddleware                          │    │
                    │  │      (existing — common/auth_middleware.py) │    │
                    │  └────────────────────────────────────────────┘    │
                    │                                                      │
                    │  ┌────────────────────────────────────────────┐    │
                    │  │ Top-level admin router                       │    │
                    │  │ (apps/control-plane/src/platform/admin/      │    │
                    │  │  router.py — NEW)                            │    │
                    │  │                                              │    │
                    │  │   prefix=/api/v1/admin                       │    │
                    │  │   tags=["admin"]                             │    │
                    │  │   dependencies=[Depends(rate_limit_admin)]   │    │
                    │  │                                              │    │
                    │  │   includes:                                  │    │
                    │  │   • settings_router (NEW)                    │    │
                    │  │   • two_person_auth_router (NEW)             │    │
                    │  │   • impersonation_router (NEW)               │    │
                    │  │   • activity_feed_router (NEW)               │    │
                    │  │   • installer_state_router (NEW)             │    │
                    │  │   • feature_flags_router (NEW)               │    │
                    │  │   • tenant_mode_router (NEW)                 │    │
                    │  │   • health_router (NEW — aggregated)         │    │
                    │  │   • lifecycle_router (NEW — super-admin only)│    │
                    │  │                                              │    │
                    │  │   AND mounts every per-BC admin_router:      │    │
                    │  │   • auth/admin_router.py        (NEW)         │    │
                    │  │   • accounts/admin_router.py    (NEW)         │    │
                    │  │   • workspaces/admin_router.py  (NEW)         │    │
                    │  │   • policies/admin_router.py    (NEW)         │    │
                    │  │   • connectors/admin_router.py  (NEW)         │    │
                    │  │   • privacy_compliance/admin_router.py (NEW)  │    │
                    │  │   • security_compliance/admin_router.py (NEW) │    │
                    │  │   • cost_governance/admin_router.py (NEW)     │    │
                    │  │   • multi_region_ops/admin_router.py (NEW)    │    │
                    │  │   • model_catalog/admin_router.py (NEW)       │    │
                    │  │   • notifications/admin_router.py (NEW)       │    │
                    │  │   • incident_response/admin_router.py (NEW)   │    │
                    │  │   • audit/admin_router.py       (NEW)         │    │
                    │  └────────────────────────────────────────────┘    │
                    │                                                      │
                    │  Every admin endpoint declares:                     │
                    │     Depends(require_admin)  OR                      │
                    │     Depends(require_superadmin)                     │
                    │  (Constitution Rule 30 — CI-enforced via T088)      │
                    └─────────────────────────────────────────────────────┘
```

**Key design point**: the composition layer at `apps/control-plane/src/platform/admin/` is **NOT a bounded context** — it has no `models.py`, no `service.py`, no per-BC business logic. It is a thin router-mounting + cross-cutting-primitives layer. The cross-cutting modules (2PA, impersonation, change preview) DO have their own service.py + models because they have their own state — this is the only exception.

### Track B — `require_admin` / `require_superadmin` Dependencies (canonical signatures)

```python
# apps/control-plane/src/platform/admin/rbac.py — NEW

from fastapi import Depends, HTTPException, status
from platform.common.dependencies import get_current_user

def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Gate: user has the platform_admin OR superadmin role.

    Mirrors the existing `_require_platform_admin` pattern at auth/router.py:54-58
    but exposes it as a reusable FastAPI dependency.
    """
    roles = {r["role"] for r in current_user.get("roles", [])}
    if not (roles & {"platform_admin", "superadmin"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "admin_role_required",
                "message": "This endpoint requires the platform_admin or superadmin role.",
                "suggested_action": "Sign in as an administrator.",
                "correlation_id": current_user.get("correlation_id"),
            },
        )
    return current_user

def require_superadmin(current_user: dict = Depends(get_current_user)) -> dict:
    """Gate: user has the superadmin role specifically."""
    roles = {r["role"] for r in current_user.get("roles", [])}
    if "superadmin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "superadmin_role_required",
                "message": "This endpoint requires the superadmin role.",
                "suggested_action": "Contact your platform administrator.",
                "correlation_id": current_user.get("correlation_id"),
            },
        )
    return current_user
```

### Track B — `AdminReadOnlyMiddleware` (canonical signature)

```python
# apps/control-plane/src/platform/admin/read_only_middleware.py — NEW

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class AdminReadOnlyMiddleware(BaseHTTPMiddleware):
    """
    Returns HTTP 403 on any non-GET request to /api/v1/admin/* when the session
    has admin_read_only_mode=true. Registered ABOVE AuthMiddleware in the stack
    (per common/app_factory.py) so the rejection short-circuits before the
    per-endpoint logic.
    """
    async def dispatch(self, request, call_next):
        if (
            request.url.path.startswith("/api/v1/admin/")
            and request.method != "GET"
            and request.scope.get("admin_read_only_mode")  # populated by AuthMiddleware from the session marker
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "error_code": "admin_read_only_mode",
                    "message": "This session is in read-only mode. Toggle it off to perform write actions.",
                    "suggested_action": "Toggle the read-only switch in the workbench header off (requires MFA step-up if enabled).",
                    "correlation_id": request.scope.get("correlation_id"),
                },
            )
        return await call_next(request)
```

The `admin_read_only_mode` flag is populated by the existing `AuthMiddleware` from the session record's `admin_read_only_mode` boolean — but the rejection happens BEFORE `AuthMiddleware` would otherwise process the rest of the request, so the rejection is fast.

### Track C — `(admin)` Route Group Layout (canonical sketch)

```typescript
// apps/web/app/(admin)/layout.tsx — NEW (Server Component)

import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { decodeJwtClaims } from "@/lib/jwt";  // existing helper
import { Forbidden403 } from "./403/page";
import { AdminLayout } from "@/components/features/admin/AdminLayout";

export default async function AdminRouteGroupLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get("access_token")?.value;

  if (!accessToken) {
    redirect("/login?redirectTo=/admin");
  }

  const claims = decodeJwtClaims(accessToken);
  const roles = new Set(claims.roles?.map((r: any) => r.role) ?? []);

  if (!roles.has("platform_admin") && !roles.has("superadmin")) {
    return <Forbidden403 />;  // SERVER-SIDE 403 page (NOT a redirect)
  }

  return (
    <AdminLayout
      isSuperAdmin={roles.has("superadmin")}
      instanceName={process.env.NEXT_PUBLIC_PLATFORM_INSTANCE_NAME ?? "Musematic Platform"}
    >
      {children}
    </AdminLayout>
  );
}
```

**Key design points**:
- The role gate is server-side (Server Component reading `cookies()`).
- A non-admin gets a 403 page, NOT a redirect — supporting deep-link UX per User Story 3.
- The `isSuperAdmin` boolean is forwarded to `<AdminLayout>` which conditionally renders the super-admin-only navigation sections.
- The platform instance name is read from a public env var so the workbench can render the customised header per FR-546.
- Per-page super-admin-only gates (e.g., `/admin/tenants/page.tsx`) ALSO check the role server-side — defence in depth for deep-linked super-admin-only pages.

### Track C — Shared Admin Components Map

| Component | File | Purpose | FR |
|---|---|---|---|
| `<AdminLayout>` | `components/features/admin/AdminLayout.tsx` | Top bar (instance name, identity badge, read-only toggle, 2PA bell, help, theme switch) + collapsible sidebar with grouped nav (10 sections) | FR-546, FR-571 |
| `<AdminPage>` | `AdminPage.tsx` | Page shell — breadcrumbs + title + help panel + action bar + data area | FR-575, FR-569 |
| `<AdminTable>` | `AdminTable.tsx` | Data-table — server-side pagination (50 default, max 500) + sort + column filter + free-text search + CSV export + saved views | FR-576 |
| `<BulkActionBar>` | `BulkActionBar.tsx` | Multi-select bar with available bulk actions | FR-559 |
| `<ChangePreview>` | `ChangePreview.tsx` | Renders dry-run diff (affected entities, cascade implications, irreversibility, duration) | FR-560 |
| `<TwoPersonAuthDialog>` | `TwoPersonAuthDialog.tsx` | 2PA initiation + approval UI | FR-561 |
| `<ImpersonationBanner>` | `ImpersonationBanner.tsx` | Persistent header banner during impersonation | FR-562 |
| `<ReadOnlyIndicator>` | `ReadOnlyIndicator.tsx` | Header badge during read-only mode + toggle handler | FR-563 |
| `<EmbeddedGrafanaPanel>` | `EmbeddedGrafanaPanel.tsx` | Auth-proxied iframe with `frame-ancestors 'self'` CSP | FR-580 |
| `<ConfirmationDialog>` | `ConfirmationDialog.tsx` | Tiered confirmation: simple click / typed phrase / 2PA | FR-577 |
| `<AdminHelp>` | `AdminHelp.tsx` | Collapsible inline help per page | FR-569 |
| `<AdminCommandPalette>` | `AdminCommandPalette.tsx` | Cmd/Ctrl+K palette scoped to admin (extends existing `cmdk`-based palette) | FR-558 |
| `<FirstInstallChecklist>` | `FirstInstallChecklist.tsx` | 7-item checklist for the bootstrap super admin's first login | FR-568 |
| `<AdminTour>` | `AdminTour.tsx` | Guided tour for new regular admins on first login | FR-568 |

## Phase 2 — Implementation Order

| Phase | Goal | Tasks (T-numbers indicative; final list in tasks.md) | Wave | Parallelizable |
|---|---|---|---|---|
| **0. Setup** | Alembic migration 065, dependency audit, OpenAPI tag | T001-T004 | W11A.1 | yes |
| **1. Track A — Bootstrap** | `bootstrap.py` + idempotency + Helm Job + Helm values + CLI `superadmin` sub-app + emergency-key check | T005-T011 | W11A.2 | sequential |
| **2. Track B — Composition** | `admin/` composition + `require_admin` + `require_superadmin` + `AdminReadOnlyMiddleware` + 2PA + impersonation + change preview + activity feed + installer-state | T012-T024 | W11B.1 | mostly yes |
| **3. Track B — Per-BC admin routers** | 13 `admin_router.py` files | T025-T037 | W11B.2 | yes — 13 independent BCs |
| **4. Track B — Cross-BC admin routes** | `health` aggregator + `lifecycle/*` + `feature-flags` + `tenant_mode` switch + signed config export/import | T038-T046 | W11B.3 | mostly yes |
| **5. Track C — Shared components** | 14 shared components per the design map | T047-T060 | W11C.1 | mostly yes |
| **6. Track C — Layout + landing** | `(admin)/layout.tsx` server-side gate + 403 page + `(admin)/page.tsx` landing dashboard + `<FirstInstallChecklist>` + `<AdminTour>` | T061-T064 | W11C.2 | yes (parallel sub-tasks) |
| **7. Track C — Pages** | 57 admin pages — split into 10 sub-tasks per FR-548 to FR-557 | T065-T074 | W11C.3 | yes — 10 independent sections |
| **8. Track C — UX polish** | Universal search palette + admin store + admin mutations hooks + i18n catalog | T075-T078 | W11C.4 | mostly yes |
| **9. WebSocket admin channels** | Extend `ChannelType` + CHANNEL_TOPIC_MAP; admin channels for real-time counters per FR-564 | T079-T080 | W11B.4 | sequential |
| **10. E2E coverage** | Extend J01 + author J18 + `tests/e2e/suites/admin/` with 6 BC-suite tests + axe-core scan extension | T081-T087 | W11D.1 | mostly yes |
| **11. CI gates** | Static-analysis check for Constitution Rule 30 + admin-route audit + secret-leak lint + Helm unittest for the bootstrap Job | T088-T091 | W11D.2 | yes |
| **12. Polish + docs** | Operator README + CLAUDE.md update + chart README addendum + cross-feature coordination notes | T092-T098 | W11D.3 | yes |

### Wave layout

UPD-036 lands in **Wave 11** (post-audit-pass capstone — UPD-035 is Wave 12 of v1.2.0; UPD-036 starts v1.3.0 at Wave 11 of the global cadence — note the wave numbering resets per major version per the constitutional cadence at line 476).

- **Wave 11A — Bootstrap (Track A)**: T001-T011; ~1.5 dev-days; dependencies on the existing auth BC + Helm chart.
- **Wave 11B — Admin REST API (Track B)**: T012-T046; ~5 dev-days; 13 per-BC routers are parallelizable across devs.
- **Wave 11C — Workbench UI (Track C)**: T047-T078; ~7 dev-days; 10 page sections are parallelizable across devs.
- **Wave 11D — Validation + polish**: T081-T098; ~2 dev-days; sequential after Tracks A/B/C.

**Total: ~14 dev-days.** With three devs in parallel (one per track), wall-clock is **~6-7 days**, plus the audit-pass-completion gate.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Surface-area drift** — 57 pages is easy to underestimate | High | High — the workbench's value depends on every page actually shipping | T065-T074 split the page work across 10 sections (one task per section); T088 verifies every documented page has a corresponding test in J18 / extended J01 / `tests/e2e/suites/admin/`; no page is "done" without a test |
| **RBAC bug — missing role gate on one endpoint** | Medium | Critical — could expose super-admin functionality to a regular admin | T088 ships the static-analysis CI check enforcing Constitution Rule 30; per-endpoint negative tests (T085) verify the gate works at runtime |
| **2PA replay / race conditions** | Medium | High — could allow approval-spoofing or stale-approval attacks | T015 implements single-use bound-to-action tokens (DB-side `consumed=true` on approval, transactional read-modify-write); T086's negative tests cover replay; threat model document (T093) reviewed by a separate engineer before merge per the brownfield input's security note |
| **Impersonation abuse** — admins use it for routine work | Medium | Medium — degrades audit value; potential compliance issue | T020 emits dual-principal audit entries on every impersonated action; T067's `/admin/audit/admin-activity` page surfaces impersonation frequency by admin (per-day count); rate limit on impersonation starts (≤ 10 per admin per day, configurable) per the brownfield input's security note |
| **Installer regression** — changes to FR-004 break existing CLI bootstrap | Medium | High — breaks all manual / dev installs | T010 keeps the CLI bootstrap fully functional; the env-var bootstrap is strictly additive (no env vars → no behaviour change); T087's regression test verifies the CLI flow still works post-merge |
| **i18n coverage gaps** — late translations delay shipping | Medium | Medium — workbench is non-functional in non-English locales | T078 extracts admin strings into the catalog EARLY (right after T060 ships components); coordination with translation vendor begins at the start of Track C; ship-with-English-only gate via `FEATURE_ADMIN_I18N_FALLBACK=true` if needed (the brownfield input's mitigation) |
| **Bootstrap secret leak** — password appears in a log line | Low | Critical — total bootstrap-credential compromise | T002 routes secret-bearing branches through a no-log decorator + structlog redaction patterns from feature 084; T009's CI lint pass searches `bootstrap.py` for any `.password` / `.secret` reference inside a `logger.*` call; threat-model review (T093) by a separate engineer |
| **Helm Job ordering — Job runs before migrations** | Medium | High — bootstrap fails because tables don't exist | T007's Job has `helm.sh/hook: post-install,post-upgrade` AND `helm.sh/hook-weight: "10"` — the existing migrations Job has a lower weight (or is in `pre-install`); T091's helm-unittest verifies the ordering |
| **Server-side role gate mismatch with API gates** — UI shows pages but API rejects | Low | Low — UX confusion | T061's server-side gate AND T012's API-side gate use the SAME role-name strings (`platform_admin`, `superadmin`); both are derived from the same `RoleType` enum at `auth/schemas.py:21-33`; T085's E2E test verifies parity (every page that the UI renders, the API permits — and vice versa) |
| **Embedded Grafana panel CSP failure** — iframes refuse to load | Medium | Low (graceful degrade) | T055 ships the `<EmbeddedGrafanaPanel>` with a server-rendered `<a>` fallback; on CSP failure, the panel renders a clear "Grafana panel unavailable — open in new tab" link |
| **Cross-feature coordination — feature 027 settings** | High (already true) | Medium | T068 explicitly `git mv`s the existing `(main)/admin/settings/page.tsx` content into `(admin)/settings/page.tsx`; the `<AdminSettingsPanel>` is REPOINTED, not rebuilt; the old route is deleted in the same PR |
| **Tenant-mode switch deadlock** — single→multi requires 2PA but no second super admin exists yet | Low | Medium | T046's `upgrade_to_multi()` is allowed without 2PA when there is exactly ONE super admin in the platform (an explicit bootstrap exemption per FR-585's "switching modes after installation requires a super admin decision, 2PA approval"); the second-super-admin requirement re-engages once a second super admin exists |

## Open Questions

These do NOT block the plan but should be tracked:

- **Q1**: Should the `AdminReadOnlyMiddleware` flag be per-session or per-tab? **Working assumption**: per-session (consistent with FR-563 phrasing). Per-tab adds complexity but improves UX (open a read-only tab without affecting the rest); defer.
- **Q2**: Should the activity feed be paginated server-side or virtualised client-side? **Working assumption**: server-side pagination (matches the FR-576 standard data-table pattern); client-side virtualisation (e.g., `react-virtuoso`) is a follow-up perf improvement if the page hits limits.
- **Q3**: Should the activity feed materialise a projection if the audit chain hits 1M+ admin events / day? **Working assumption**: defer — the index on `(actor_role, created_at DESC)` from R8 is sufficient at the documented scale; revisit if the page p95 exceeds 800 ms.
- **Q4**: Should the `superadmin` CLI sub-app be hidden from `--help` output unless `PLATFORM_ENV != production`? **Working assumption**: NO — visibility is good (operators learn the path); the safety is in the `--force-reset-superadmin` + `ALLOW_SUPERADMIN_RESET=true` gate, NOT in hiding.
- **Q5**: Should the `(admin)` route group be a separate Next.js application (deployed independently)? **Working assumption**: NO — single Next.js app simplifies deployment; the route group is the established Next.js pattern for separating shells without separating apps.
- **Q6**: Should impersonation start be a 2PA-gated action by default? **Working assumption**: NO for impersonating a non-super-admin (justification + audit + notification + banner is sufficient per FR-562); YES for impersonating another super admin (the spec User Story 5 acceptance scenario 5 already specifies this).
- **Q7**: Should `/admin/lifecycle/migrations` allow LAUNCHING a migration? **Working assumption**: YES with 2PA — migrations are reversible-with-careful-handling but the criticality justifies 2PA. The brownfield input lists "Database Migrations" as a page; the spec captures this in FR-556.

## Cross-Feature Coordination

| Feature | What we need from them | Owner action | Blocking? |
|---|---|---|---|
| **014 (Auth)** | `RoleType.SUPERADMIN` + `_require_platform_admin` pattern + `users` / `user_roles` / `sessions` tables | Already on disk | No |
| **027 (Admin Settings Panel)** | `<AdminSettingsPanel>` component + sub-components | Already on disk; T068 absorbs into new (admin)/settings/ | No (clean cut) |
| **045 (Installer-operations CLI)** | Typer sub-app registration pattern at `main.py:71-76` | Already on disk; T011 follows the pattern | No |
| **046 (CI/CD pipeline)** | `lint-python` job for static-analysis additions (T088, T089) | T088 patches the workflow additively | No |
| **074-085 (audit-pass BCs)** | Each BC's `service.py` + `router.py` for the admin-router to delegate to | Already on disk | No (UPD-036 is the post-audit-pass capstone) |
| **083 (Accessibility & i18n)** | next-intl wiring + axe-core CI gate + 6-locale catalog | Already on disk; T078 adds admin strings to the catalog | No |
| **084 (Log aggregation)** | structlog config + Loki labels + `assert_log_contains` helper | Already on disk; T085 reuses the helper | No |
| **085 (Extended E2E)** | J01 journey + `tests/e2e/journeys/` harness + `(admin)/` axe-core scan integration | T081 extends J01; T082 authors J18 | Yes (J01 already extended; UPD-036 extends FURTHER) |

## Phase Gate

**Plan ready for `/speckit.tasks` when**:
- ✅ Constitutional anchors enumerated and gate verdicts recorded
- ✅ Brownfield-input reconciliations enumerated (12 items)
- ✅ Research decisions R1-R10 documented
- ✅ Wave placement (W11A/B/C/D) confirmed
- ✅ Cross-feature coordination matrix populated
- ✅ Risk register populated with mitigations
- ✅ Open questions enumerated (none blocking)

The plan is ready. The next phase (`/speckit.tasks`) breaks the 12-phase implementation order above into ordered, dependency-annotated tasks (T001-T098, indicative).

## Complexity Tracking

> **Filled when Constitution Check has violations that must be justified.**

| Variance | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| New `admin.events` Kafka topic (correction §6) | Some admin actions (bootstrap, tenant-mode switch, break-glass) have no current Kafka home; the existing `auth.events` topic is auth-scoped | Routing all admin events through `auth.events` would broaden the topic's scope and break consumer subscriptions; the new topic is small and bounded |
| Admin composition layer is NOT a BC | The brownfield design explicitly declares this; per-BC business logic stays with the owning BC | Making `admin/` a BC would duplicate every BC's models in the admin namespace and create cross-BC coupling that the constitutional BC discipline forbids |
| Two new tables (`two_person_auth_requests`, `impersonation_sessions`) without reusing `sessions` | Dual-principal pattern is unique to impersonation; 2PA's request-with-approval workflow is unique to 2PA | Bolting columns onto `sessions` would expand its surface in a way feature 014's owners did not anticipate; the new tables are small and bounded |
| Server-side role gate at `(admin)/layout.tsx` instead of client-side (deviation from feature 027's pattern) | Spec User Story 3 acceptance scenario 2 requires a 403 page on deep link, NOT a redirect | Client-side gates produce redirects, not 403 pages — that breaks the deep-link contract |
| `superadmin` CLI as a NEW top-level sub-app, not under `admin` | Conceptual separation: `admin` = tenant-scoped operator commands; `superadmin` = critical platform operations | Nesting under `admin` would imply tenant-scoped operations, which break-glass is NOT |
