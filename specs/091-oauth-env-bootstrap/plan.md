# Implementation Plan: UPD-041 — OAuth Provider Environment-Variable Bootstrap and Extended Super Admin UI

**Branch**: `091-oauth-env-bootstrap` | **Date**: 2026-04-27 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

UPD-041 is the smallest feature in the v1.3.0 audit-pass cohort by surface area but the most architecturally dependent — it CANNOT begin until UPD-040 (Wave 15) lands because the bootstrap module's only secret-storage path is `await secret_provider.put(...)` per Rule 43 (OAuth client secrets live in Vault, never in the database). The feature delivers the implementation of the already-canonical FR-639 through FR-648 (Section 114 of `docs/functional-requirements-revised-v6.md:3400-3509` — VERIFIED on disk per spec correction §6) across three parallelizable tracks:

- **Track A — Backend bootstrap + 5 admin endpoints** (~3 dev-days): NEW `apps/control-plane/src/platform/auth/services/oauth_bootstrap.py` invoked from the existing FastAPI lifespan hook at `main.py:_lifespan` lines 465-527 (immediately AFTER the existing `bootstrap_superadmin_from_env` call at lines 517-527 — verified per research R1); NEW `OAuthBootstrapSettings` Pydantic config block under `PlatformSettings`; Alembic migration `069_oauth_provider_env_bootstrap.py` adding 4 columns to `oauth_providers` + 1 NEW `oauth_provider_rate_limits` table per spec correction §5 + §12 (next sequence per research R7 — current highest is 068); 5 new admin endpoints registered on the existing `oauth_router` APIRouter at `auth/router_oauth.py` (verified — 4 admin endpoints exist at lines 173-274; new ones use the same `_require_platform_admin(current_user)` gate at lines 29-35 per Rule 30). Audit emission follows the dual `repository.create_audit_entry(...)` + `publish_auth_event(...)` pattern verified at `oauth_service.py:177-199`.

- **Track B — Admin UI extensions** (~3 dev-days): EXTENDS the existing `apps/web/components/features/auth/OAuthProviderAdminPanel.tsx` (382 lines on disk per research R3 — verified card-per-provider layout via `ProviderConfigCard` at lines 116-348, NO test-connectivity button, NO source badge, NO status panel, NO history tab) with 8 new sub-components per FR-643: source badge, status panel (4-stat strip), rotate-secret modal (write-only input per Rule 44), test-connectivity button (NEW per spec correction §2 — backend already exists at `router_oauth.py:220-248` returning the verified `OAuthConnectivityTestResponse(reachable, auth_url_returned, diagnostic)` per research R11), reseed-from-env action, role-mappings managed table, history tab with diff visualization, rate-limits tab. ALL strings i18n-keyed for the 6 supported locales per UPD-039 / FR-620.

- **Track C — Migration CLI + E2E + journey tests** (~2 dev-days): NEW `platform-cli admin oauth export|import` Typer sub-app at `apps/ops-cli/src/platform_cli/commands/admin/oauth.py` per spec correction §11; NEW E2E suite at `tests/e2e/suites/oauth_bootstrap/` (8 tests per spec User Story 1-5); EXTEND `tests/e2e/journeys/test_j01_admin_bootstrap.py` (verified — 318 lines, sequential `journey_step()` pattern per research R9) with new env-var-bootstrap steps; CREATE `tests/e2e/journeys/test_j19_new_user_signup.py` per spec correction §9 (J19 does NOT exist on disk — only J01-04, J10 verified). Matrix-CI inheritance from UPD-040's `secret_mode: [mock, kubernetes, vault]` job.

The three tracks converge at Phase 7 for SC verification + auto-doc verification. **Effort estimate: 8-10 dev-days** (the brownfield's "4.5 days (4 points)" understates by ~50%; the corrected estimate accounts for the 4-column Alembic migration with backward-compatible defaults, the 8 new UI sub-components with i18n + Playwright coverage, the 5 new Pydantic schemas, the 7 new audit-event types, the rate-limits middleware integration, the 8 E2E tests + 1 new journey test, and the migration runbook authoring per UPD-039 integration). Wall-clock with 3 devs in parallel: **~5-6 days**.

## Constitutional Anchors

This plan is bounded by the following Constitution articles + FRs. Each implementation step below cites the article it serves.

| Anchor | Citation | Implementation tie |
|---|---|---|
| **UPD-041 declared** | Constitution audit-pass roster (Wave 16) | The whole feature |
| **Rule 10 — Every credential goes through vault** | `.specify/memory/constitution.md:123-126` | Track A's bootstrap module writes via `SecretProvider.put`; never to a DB column |
| **Rule 30 — Every admin endpoint role-gated** | `.specify/memory/constitution.md:198-202` | Track A's 5 new endpoints all call `_require_platform_admin(current_user)` per the existing inline pattern at `router_oauth.py:29-35` |
| **Rule 31 — Super-admin bootstrap never logs secrets** | `.specify/memory/constitution.md:203-207` | Track A's structured-log discipline (deny-list `client_secret`, `secret_id` field names per UPD-040 task T044); Track A's audit `changed_fields` payload omits secret values entirely |
| **Rule 39 — Every secret resolves via SecretProvider** | `.specify/memory/constitution.md:235-239` (NEW per UPD-040) | Track A's bootstrap reads `PLATFORM_OAUTH_*_CLIENT_SECRET` env via Pydantic settings (NOT direct `os.getenv`); writes via `SecretProvider.put` per design D1 |
| **Rule 42 — OAuth env-var bootstrap is idempotent** | `.specify/memory/constitution.md:249-251` | Track A's idempotency check (`existing AND not force_update → skip`); FORCE_UPDATE emits critical audit entry per FR-640 |
| **Rule 43 — OAuth client secrets live in Vault, never in the database** | `.specify/memory/constitution.md:252-254` | Track A's bootstrap fails fast if Vault unreachable per spec edge case; the `oauth_providers.client_secret_ref` column stores a Vault PATH, never a value |
| **Rule 44 — Rotation responses never return the new secret** | `.specify/memory/constitution.md:255-257` | Track A's `POST /rotate-secret` returns 204 No Content; Track B's modal write-only input never displays the current secret per FR-643 |
| **FR-639 — Env-var seeding** | FR doc lines 3402-3424 (verified per research §11) | Track A — bootstrap module entire scope |
| **FR-640 — Idempotency** | FR doc lines 3426-3441 | Track A — `force_update` flag + audit-on-override |
| **FR-641 — Validation before persist** | FR doc lines 3443-3458 | Track A — Pydantic validators in `OAuthBootstrapSettings` |
| **FR-642 — Helm values for OAuth bootstrap** | FR doc lines 3460-3470 | Track A — `deploy/helm/platform/values.yaml` `oauth.{google,github}.*` block |
| **FR-643 — Extended super admin page** | FR doc lines 3472-3485 | Track B — entire scope |
| **FR-644 — Configuration history** | FR doc lines 3487-3491 | Track A `GET /history` endpoint + Track B history tab |
| **FR-645 — Export/import** | FR doc lines 3493-3497 | Track C — `platform-cli admin oauth` sub-app |
| **FR-646 — Per-provider rate limits** | FR doc lines 3499-3502 | Track A's NEW `oauth_provider_rate_limits` table + Track B's rate-limits tab |
| **FR-647 — CI validation** | FR doc lines 3504-3506 | Track C — extends UPD-039's `scripts/generate-env-docs.py` deny-list |
| **FR-648 — E2E coverage** | FR doc lines 3508-3509 | Track C — extends J01 + creates J19 + 8 suites tests |

**Verdict: gate passes. No declared variances.** UPD-041 satisfies all eight constitutional rules (10, 30, 31, 39, 42, 43, 44 + brownfield discipline) governing OAuth bootstrap + secret rotation.

## Technical Context

| Item | Value |
|---|---|
| **Languages** | Python 3.12 (control plane — backend bootstrap module + 5 admin endpoints + Alembic migration); TypeScript 5.x (Next.js — `OAuthProviderAdminPanel.tsx` extensions); YAML (Helm values + i18n message catalogs); No Go changes (the OAuth bootstrap is Python-only; satellites are uninvolved). |
| **Primary Dependencies (existing — reused)** | `pydantic-settings 2.x` (`BaseSettings` per `common/config.py:117-170` `AuthSettings` precedent — verified 26 OAuth-related fields); `SQLAlchemy 2.x async` (the `oauth_providers` table at `auth/models.py:223-243` — verified 12 columns); `alembic 1.13+` (next sequence is 069 per research R7); `aiokafka 0.11+` (audit-event emission via `publish_auth_event(...)` per research R6); `react 18+` + `next 14` + `shadcn/ui` (existing `OAuthProviderAdminPanel.tsx` at 382 lines per research R3); `Typer 0.12+` (existing `platform-cli admin` sub-app — research R7 confirms `apps/ops-cli/src/platform_cli/commands/admin.py`). |
| **Primary Dependencies (NEW in 091)** | NO new runtime dependencies. The bootstrap relies on UPD-040's `hvac>=2.3.0` (already added in Wave 15) for Vault writes via `SecretProvider`. Track C's CLI sub-app reuses UPD-040's `platform-cli vault` Typer infrastructure. |
| **Storage** | PostgreSQL — Alembic migration `069_oauth_provider_env_bootstrap.py` adds 4 columns to `oauth_providers` (`source` ENUM("env_var", "manual", "imported") default "manual"; `last_edited_by` UUID FK to users.id nullable; `last_edited_at` timestamptz nullable; `last_successful_auth_at` timestamptz nullable); existing 12 columns preserved unchanged. NEW table `oauth_provider_rate_limits` per FR-646 + spec correction §12: `provider_id` FK + `per_ip_max`, `per_ip_window`, `per_user_max`, `per_user_window`, `global_max`, `global_window` integers. Vault — NEW canonical paths `secret/data/musematic/{env}/oauth/google/client-secret` and `secret/data/musematic/{env}/oauth/github/client-secret` (per UPD-040's path scheme; populated by the bootstrap module). Redis — reuses UPD-040's per-pod cache + UPD-040's flush-cache primitive for rotation flow. |
| **Testing** | `pytest 8.x` + `pytest-asyncio` (control plane unit tests for bootstrap module + 5 admin endpoints — 30+ test cases); Playwright (Next.js panel E2E for the 8 new UI sub-components — 12+ scenarios); axe-core CI gate for AA accessibility per UPD-083 / FR-488 inheritance; pytest E2E suite at `tests/e2e/suites/oauth_bootstrap/` — 8 test files; J01 extension (the 318-line existing file gains ~50 lines of bootstrap-flow steps); J19 creation (new file modeled on J01's `journey_step()` pattern per research R9). Matrix-CI from UPD-040: `secret_mode: [mock, kubernetes, vault]` × `oauth_bootstrap` suite. |
| **Target Platform** | Linux x86_64 Kubernetes 1.28+ (control plane + Vault from UPD-040); Next.js 14 server + browser (admin UI). |
| **Project Type** | Cross-stack feature: (a) Python control plane (`apps/control-plane/` — bootstrap + endpoints + migration); (b) Next.js frontend (`apps/web/` — admin panel extensions); (c) operator CLI (`apps/ops-cli/` — export/import); (d) E2E test scaffolding (`tests/e2e/`); (e) Helm chart values (`deploy/helm/platform/`). NO Go satellite changes. |
| **Performance Goals** | Bootstrap module completes in ≤ 5 seconds wall-clock from pod startup per SC-001 (network round-trips: 1 SQL query for existing-row check, 1 Vault `put` per provider, 1 audit-emission per provider — 6-10 Vault/SQL operations total for 2 providers). Rotation action returns 204 in ≤ 2 seconds (1 Vault `put` + 1 cache flush + 1 audit emission). Admin panel extensions: per-page load ≤ 1.5 seconds p95 (the existing panel loads in ≤ 800 ms; new sub-components add ~700 ms in cold-cache). |
| **Constraints** | Rule 31 + Rule 44 — no plaintext secret in any log / response / audit metadata (CI-enforced via UPD-040's `scripts/check-secret-access.py` extended with `oauth_*` patterns); Rule 43 — bootstrap fails fast if Vault unreachable (no DB-stored-secret fallback); Rule 30 — every new admin endpoint depends on `_require_platform_admin`; Rule 42 — bootstrap is idempotent (verified by SC-002); FR-647 — CI staleness check on `PLATFORM_OAUTH_*` env vars (verified by SC-013 — extends UPD-039's `scripts/generate-env-docs.py`). |
| **Scale / Scope** | Track A: 1 NEW Python module (bootstrap, ~250 lines) + 1 NEW Pydantic config block (~80 lines) + 1 Alembic migration (~80 lines including downgrade) + 5 NEW admin endpoints (~300 lines including Pydantic schemas) + 7 NEW audit-event types + ~40 unit tests. Track B: 8 NEW UI sub-components in `OAuthProviderAdminPanel.tsx` (~600 lines net addition; existing 382 → ~1000) + 6 i18n catalogs × ~30 strings each = ~180 string entries + ~12 Playwright scenarios. Track C: 1 NEW Typer sub-app (~400 lines) + 8 E2E test files (~80 lines each = ~640 lines) + 1 J19 journey file (~250 lines modeled on J01) + ~50 lines J01 extension. Helm values: 1 NEW `oauth.*` block (~30 lines) + 1 control-plane Deployment env-var injection (~20 lines). **Total: ~3500 lines of new Python + TypeScript + YAML + 6 locales × 30 strings = 180 i18n entries; ~30 NEW files + ~10 MODIFIED files.** |

## Constitution Check

> **GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.**

| Check | Verdict | Rationale |
|---|---|---|
| Brownfield rule — modifications respect existing repo discipline | ✅ Pass | UPD-041 (a) EXTENDS the existing 4-endpoint OAuth admin router at `router_oauth.py:173-274` by adding 5 new endpoints — the existing 4 are preserved unchanged; (b) EXTENDS the existing `OAuthProviderAdminPanel.tsx` tab component (NOT a new route per spec correction §1); (c) ADDS 4 columns to `oauth_providers` via reversible Alembic migration with sane defaults (`source=manual` for existing rows); (d) preserves the existing 7 OAuth audit-event names (`auth.oauth.provider_configured`, etc.) and adds 7 new ones following the same `auth.oauth.{action}` convention. |
| Rule 10 — every credential goes through vault | ✅ Pass | Track A's bootstrap reads `PLATFORM_OAUTH_*_CLIENT_SECRET` from env (or `_FILE`) and writes to Vault via UPD-040's `SecretProvider.put`; the OAuth flow's secret-resolution path uses UPD-040's consolidated `SecretProvider.get` via the rewired `oauth_service._resolve_secret` (UPD-040 task T011 — already shipped at Wave 15). |
| Rule 30 — every admin endpoint role-gated | ✅ Pass | All 5 new admin endpoints call `_require_platform_admin(current_user)` per the existing pattern at `router_oauth.py:29-35` (verified). UPD-040 task T090 (Track E) added the static-analysis check at `scripts/check-admin-role-gates.py` — UPD-041's new endpoints will be auto-verified by that check. |
| Rule 31 — super-admin bootstrap never logs secrets | ✅ Pass | Track A's structured logger uses the deny-list from UPD-040 task T044 (extended with `client_secret`, `oauth_secret`); Track A's audit `changed_fields` excludes secret values per the existing pattern at `oauth_service.py:177-189` (verified — `changed_fields` lists field NAMES, not values). |
| Rule 39 — every secret resolves via SecretProvider | ✅ Pass | Track A's bootstrap module reads non-secret env vars (CLIENT_ID, REDIRECT_URI, etc.) via Pydantic settings; the CLIENT_SECRET value is read either from the Pydantic field (which UPD-040's CI deny-list at `scripts/check-secret-access.py` allows for `SecretProvider` implementations — the bootstrap module gets the same allowlist) OR from a `_FILE` path via `Path(...).read_text()` (filesystem read, not env-var read — exempt from the Rule 39 deny-list). The CLIENT_SECRET is then immediately written to Vault via `await secret_provider.put(...)`; no in-memory persistence beyond the synchronous bootstrap call. |
| Rule 42 — OAuth env-var bootstrap is idempotent | ✅ Pass | Track A's bootstrap module checks `existing = await oauth_repository.get_by_type(provider_type)`; if existing AND not `force_update`, skips the upsert; if `force_update=true`, overwrites with a critical-severity audit entry per FR-640. Test SC-002 verifies the idempotency contract under both flag values. |
| Rule 43 — OAuth client secrets live in Vault, never in the database | ✅ Pass | The `oauth_providers.client_secret_ref` column stores a Vault PATH (e.g., `secret/data/musematic/staging/oauth/google/client-secret`), NEVER a secret value. The bootstrap fails fast if Vault is unreachable (spec edge case + SC-017). |
| Rule 44 — rotation responses never return the new secret | ✅ Pass | Track A's `POST /rotate-secret` endpoint returns `204 No Content`; the response body is empty (verified by Track A's Pydantic schema `OAuthSecretRotateRequest` having NO response model). Track B's modal closes on 204 receipt. |

**Verdict: gate passes. No declared variances. UPD-041 satisfies all eight constitutional rules governing OAuth bootstrap + secret rotation.**

## Project Structure

### Documentation (this feature)

```text
specs/091-oauth-env-bootstrap/
├── plan.md                # this file
├── spec.md
├── planning-input.md
└── tasks.md               # produced by /speckit.tasks (next phase)
```

### Source Code (repository root) — files this feature creates or modifies

```text
# === Track A — Backend bootstrap + admin endpoints ===
apps/control-plane/src/platform/auth/services/oauth_bootstrap.py     # NEW — bootstrap module per FR-639 + Rule 42
apps/control-plane/src/platform/auth/services/__init__.py            # MODIFY — re-export bootstrap function
apps/control-plane/src/platform/common/config.py                     # MODIFY — adds NEW `OAuthBootstrapSettings` + `OAuthGoogleBootstrap` + `OAuthGithubBootstrap` blocks under PlatformSettings (env_prefix `OAUTH_GOOGLE_` / `OAUTH_GITHUB_` resolved as `PLATFORM_OAUTH_*` per spec correction §4)
apps/control-plane/src/platform/main.py                              # MODIFY — invoke bootstrap from `_lifespan` lines 465-527 AFTER existing `bootstrap_superadmin_from_env` at lines 517-527 per research R1
apps/control-plane/src/platform/auth/router_oauth.py                 # MODIFY — adds 5 new admin endpoints AFTER the existing 4 at lines 173-274; same `_require_platform_admin(current_user)` gate at line 29-35; same `tags=["admin"]` registration
apps/control-plane/src/platform/auth/schemas.py                      # MODIFY — adds 5 new schemas: `OAuthSecretRotateRequest`, `OAuthConfigReseedRequest`, `OAuthRateLimitConfig`, `OAuthHistoryEntryResponse`, `OAuthHistoryListResponse` (modeled on the existing 8 OAuth schemas at lines 208-303)
apps/control-plane/src/platform/auth/models.py                       # MODIFY — adds 4 columns to `OAuthProvider` (line 223-243): `source`, `last_edited_by`, `last_edited_at`, `last_successful_auth_at`; adds NEW `OAuthProviderRateLimit` model with FK to OAuthProvider
apps/control-plane/src/platform/auth/services/oauth_service.py       # MODIFY — adds `rotate_secret()`, `reseed_from_env()`, `get_history()`, `get_rate_limits()`, `update_rate_limits()` methods; the existing `_resolve_secret` (lines 732-747) is ALREADY rewired by UPD-040 task T011 to delegate to `SecretProvider.get` — UPD-041 inherits this
apps/control-plane/src/platform/auth/services/oauth_repository.py    # MODIFY (verify file exists during T010) — adds `get_history()` query, `get_by_type_for_update()` row-locking query for race-safe bootstrap, `count_active_links()` query for status panel
apps/control-plane/migrations/versions/069_oauth_provider_env_bootstrap.py  # NEW — Alembic migration adding 4 columns + 1 NEW table per spec correction §5 + §12
apps/control-plane/tests/auth/test_oauth_bootstrap.py                # NEW — pytest tests for bootstrap module (~30 cases)
apps/control-plane/tests/auth/test_oauth_admin_endpoints.py          # NEW — pytest tests for 5 new admin endpoints (~25 cases)
scripts/check-secret-access.py                                       # MODIFY (extends UPD-040's deny-list per FR-647) — adds `OAUTH_SECRET_*` and `PLATFORM_OAUTH_*_CLIENT_SECRET` patterns

# === Track B — Admin UI extensions ===
apps/web/components/features/auth/OAuthProviderAdminPanel.tsx        # MODIFY — extends 382-line existing panel with 8 new sub-components (verified per research R3)
apps/web/components/features/auth/OAuthProviderSourceBadge.tsx       # NEW — `source: env_var|manual|imported` badge (~50 lines)
apps/web/components/features/auth/OAuthProviderStatusPanel.tsx       # NEW — 4-stat strip (last_successful_auth, 24h/7d/30d counts, linked users count) (~120 lines)
apps/web/components/features/auth/OAuthProviderRotateSecretDialog.tsx  # NEW — write-only secret modal per Rule 44 (~150 lines)
apps/web/components/features/auth/OAuthProviderTestConnectivityButton.tsx  # NEW — button + diagnostic display (~100 lines; renders the existing OAuthConnectivityTestResponse from research R11)
apps/web/components/features/auth/OAuthProviderReseedDialog.tsx      # NEW — confirmation + diff display (~120 lines)
apps/web/components/features/auth/OAuthProviderRoleMappingsTable.tsx  # NEW — managed table for group_role_mapping (~250 lines)
apps/web/components/features/auth/OAuthProviderHistoryTab.tsx        # NEW — paginated change history with diff view (~200 lines)
apps/web/components/features/auth/OAuthProviderRateLimitsTab.tsx     # NEW — per-IP / per-user / global limits form (~150 lines)
apps/web/lib/api/oauth-admin.ts                                       # MODIFY — adds 5 new fetch wrappers for new endpoints
apps/web/lib/schemas/oauth.ts                                         # MODIFY — adds 5 new Zod schemas mirroring backend Pydantic
apps/web/messages/en.json                                             # MODIFY — adds ~30 new i18n keys under `admin.oauth.*` namespace
apps/web/messages/{de,es,fr,it,zh-CN,ja}.json                         # MODIFY — translated catalogs (vendor-handled per UPD-039)
apps/web/tests/e2e/admin-oauth-bootstrap.spec.ts                      # NEW — Playwright tests for the 8 new sub-components (~12 scenarios)

# === Track C — Migration CLI + E2E + journey tests ===
apps/ops-cli/src/platform_cli/commands/admin/oauth.py                 # NEW — Typer sub-app with `export` + `import` subcommands per FR-645
apps/ops-cli/src/platform_cli/commands/admin/__init__.py              # MODIFY — register new `oauth` sub-app
apps/ops-cli/src/platform_cli/commands/admin.py                       # MODIFY — add `app.add_typer(oauth_app, name="oauth")` per the existing pattern
apps/ops-cli/tests/commands/admin/test_oauth.py                       # NEW — pytest tests for export/import (~15 cases)

tests/e2e/suites/oauth_bootstrap/__init__.py                          # NEW
tests/e2e/suites/oauth_bootstrap/conftest.py                          # NEW — shared fixtures (env-var-bootstrap setup, kind cluster Vault populate, OAuth provider mocks)
tests/e2e/suites/oauth_bootstrap/test_env_bootstrap_google.py         # NEW
tests/e2e/suites/oauth_bootstrap/test_env_bootstrap_github.py         # NEW
tests/e2e/suites/oauth_bootstrap/test_bootstrap_idempotency.py        # NEW — Rule 42 verification
tests/e2e/suites/oauth_bootstrap/test_force_update.py                 # NEW — FORCE_UPDATE=true overwrite + critical audit
tests/e2e/suites/oauth_bootstrap/test_rotation.py                     # NEW — rotate-secret writes new Vault version + flush + 204 + Rule 44
tests/e2e/suites/oauth_bootstrap/test_reseed.py                       # NEW — reseed-from-env action
tests/e2e/suites/oauth_bootstrap/test_validation_failures.py          # NEW — missing CLIENT_ID, invalid JSON, non-HTTPS redirect
tests/e2e/suites/oauth_bootstrap/test_role_mappings.py                # NEW — group/team role mapping table

tests/e2e/journeys/test_j01_admin_bootstrap.py                        # MODIFY — add new env-var-bootstrap steps (~50 lines net)
tests/e2e/journeys/test_j19_new_user_signup.py                        # NEW — modeled on J01 per research R9 (~250 lines)

# === Helm chart additions ===
deploy/helm/platform/values.yaml                                      # MODIFY — adds new `oauth.{google,github}.*` block per FR-642 + spec User Story 5 (modeled on existing top-level blocks per research R8)
deploy/helm/platform/templates/deployment-control-plane.yaml          # MODIFY — adds `PLATFORM_OAUTH_*` env-var injection from `oauth.*` values; mounts client-secret files if `clientSecretRef` set
deploy/helm/platform/templates/configmap-oauth.yaml                   # NEW (optional — only if non-secret OAuth bootstrap config is many fields) — projects non-sensitive bootstrap config

# === Documentation (UPD-039 integration if landed) ===
docs/operator-guide/runbooks/oauth-bootstrap.md                       # NEW — operator runbook for env-var bootstrap (deliverable here if UPD-039 landed; otherwise UPD-039 owns)
docs/operator-guide/runbooks/oauth-secret-rotation.md                 # NEW — rotation runbook
docs/admin-guide/oauth-providers.md                                   # MODIFY — extends with rotation + reseed + role-mappings + history sections
```

**Structure decision**: UPD-041 follows the brownfield repo discipline established by UPD-036 (admin workbench) + UPD-037 (signup OAuth UI) + UPD-040 (Vault). The bootstrap module lives in `auth/services/` co-located with the existing `oauth_service.py`. The 5 new admin endpoints register on the same `oauth_router` APIRouter, NOT a new router. The 8 new UI sub-components live alongside `OAuthProviderAdminPanel.tsx` in `components/features/auth/`. The Alembic migration follows the next sequence (069). The E2E suite slots into the existing `tests/e2e/suites/` pattern from UPD-040.

## Phase 0 — Research

> Research notes captured during plan authoring. Each item resolves a specific design question.

- **R1 — Bootstrap insertion point in `main.py` lifespan [RESEARCH-COMPLETE]**: `apps/control-plane/src/platform/main.py:_lifespan` (verified at lines 465-527) runs the existing `bootstrap_superadmin_from_env(session_factory, settings, method="env_var")` at lines 517-527, BEFORE rubric/clickhouse setup at line 529. **Resolution**: UPD-041's `bootstrap_oauth_providers_from_env(...)` is invoked IMMEDIATELY AFTER the superadmin bootstrap (between lines 527-529), wrapped in the same try/except pattern that sets `app.state.degraded = True` on non-config failures and propagates `BootstrapConfigError` for misconfiguration. Conditional gate: only invoke if `os.getenv("PLATFORM_OAUTH_GOOGLE_ENABLED") == "true" OR os.getenv("PLATFORM_OAUTH_GITHUB_ENABLED") == "true"` to avoid unnecessary Vault round-trips when OAuth is not configured.

- **R2 — Admin endpoint URL convention: dual-prefix [RESEARCH-COMPLETE]**: The existing test-connectivity endpoint at `router_oauth.py:220-225` registers under TWO paths (`/api/v1/admin/oauth-providers/{provider}/test-connectivity` AND `/api/v1/admin/oauth/providers/{provider}/test-connectivity`) for backward compatibility. **Resolution**: The 5 new endpoints follow the SAME dual-prefix pattern; the canonical (preferred) path is `/api/v1/admin/oauth-providers/{provider}/{action}` (matches the spec); the legacy alias `/api/v1/admin/oauth/providers/...` is included with `include_in_schema=False` to avoid OpenAPI duplication. UPD-039's API Reference will only document the canonical path.

- **R3 — `OAuthProviderAdminPanel.tsx` extension strategy [RESEARCH-COMPLETE]**: 382 lines on disk; `ProviderConfigCard` at lines 116-348 is the per-provider card. **Resolution**: Track B EXTENDS `ProviderConfigCard` with a tabs structure (shadcn `Tabs`) above the existing form: tab "Configuration" (existing form, unchanged); tab "Status" (new `OAuthProviderStatusPanel`); tab "Role Mappings" (new `OAuthProviderRoleMappingsTable`); tab "History" (new `OAuthProviderHistoryTab`); tab "Rate Limits" (new `OAuthProviderRateLimitsTab`). The source badge + rotate-secret + test-connectivity + reseed buttons are rendered in the card header (above the tabs). This minimizes risk of regressing the existing form while delivering the FR-643 surface.

- **R4 — Pydantic schema additions [RESEARCH-COMPLETE]**: Existing 8 OAuth schemas at `auth/schemas.py:208-303` (verified per research R4). **Resolution**: 5 NEW schemas added to the same file: `OAuthSecretRotateRequest(new_secret: SecretStr)` (uses Pydantic's `SecretStr` to prevent accidental logging — the `__repr__` returns `**********`); `OAuthConfigReseedRequest(force_update: bool = False)`; `OAuthRateLimitConfig(per_ip_max, per_ip_window, per_user_max, per_user_window, global_max, global_window)`; `OAuthHistoryEntryResponse(timestamp, admin_id, action, before, after)`; `OAuthHistoryListResponse(entries, next_cursor)`. NO response model for rotate-secret (returns 204).

- **R5 — `_require_platform_admin` is INLINE not shared [RESEARCH-COMPLETE]**: Verified at `router_oauth.py:29-35` — the function is INLINE in the router file, NOT a shared dependency from `auth/dependencies.py`. **Resolution**: Track A's 5 new endpoints call the SAME inline function (importing or duplicating is unnecessary since they live in the same file). UPD-040 task T090's static-analysis check at `scripts/check-admin-role-gates.py` searches for `Depends(require_admin)` OR `Depends(require_superadmin)` OR direct `_require_platform_admin(current_user)` calls — all 3 patterns satisfy Rule 30. Track A's endpoints use the inline call; the static check passes.

- **R6 — Dual audit emission pattern [RESEARCH-COMPLETE]**: Verified at `oauth_service.py:177-199` — every OAuth audit event emits via TWO paths: (1) `await self.repository.create_audit_entry(...)` writes a row to the audit_chain DB table; (2) `await publish_auth_event(...)` publishes a Kafka event on the `auth.events` topic. **Resolution**: Track A's 7 new audit-event types (`auth.oauth.provider_bootstrapped`, `auth.oauth.secret_rotated`, `auth.oauth.config_reseeded`, `auth.oauth.role_mapping_updated`, `auth.oauth.rate_limit_updated`, `auth.oauth.config_imported`, `auth.oauth.config_exported`) follow the SAME dual-emission pattern. NEW Pydantic event payloads are added under `apps/control-plane/src/platform/auth/events/oauth_events.py` (or wherever the existing `OAuthProviderConfiguredPayload` lives — verified during T010 of tasks). Each payload OMITS secret values entirely (only metadata: provider_type, admin_id, action_outcome, etc.).

- **R7 — Alembic migration sequence [RESEARCH-COMPLETE]**: `apps/control-plane/migrations/versions/` contains 065-068 (verified — last is `068_pending_profile_completion.py` from UPD-037). **Resolution**: UPD-041's migration is `069_oauth_provider_env_bootstrap.py`. Conflict risk with UPD-040: UPD-040 ships in Wave 15 BEFORE UPD-041's Wave 16; if UPD-040 owns migration 069 (likely — based on UPD-040's own Alembic additions for the `oauth_provider_rate_limits` table OR the `runtime_warm_pool_targets` table from feature 055), the actual sequence in UPD-041 may shift to 070 or 071. T012 of tasks confirms the live sequence at the time of authoring.

- **R8 — Helm values block precedent [RESEARCH-COMPLETE]**: `deploy/helm/platform/values.yaml` has multiple top-level blocks (`superadmin:` lines 9-21, `postgresql:` lines 80-96, `vault:` lines NEW per UPD-040). **Resolution**: New `oauth:` block follows the same pattern with `# @section -- OAuth Bootstrap` heading and `# -- Configures ...` helm-docs comments per UPD-039 / FR-611 auto-doc integration. Sub-blocks `oauth.google.*` and `oauth.github.*` mirror the brownfield's example. Each value gets a helm-docs `# --` annotation so UPD-039's `helm-docs --check` CI gate passes.

- **R9 — J01 + J19 journey-test pattern [RESEARCH-COMPLETE]**: `tests/e2e/journeys/test_j01_admin_bootstrap.py` is 318 lines with 20 sequential `journey_step()` blocks (verified per research R9). Steps 4-7 ALREADY cover OAuth provider configuration (admin views inventory, configures Google, configures GitHub, verifies public list). **Resolution**: J01's existing OAuth steps are RECONCILED with the new env-var-bootstrap flow — adds 3 new steps BEFORE step 4: "Verify env-var-bootstrapped Google + GitHub providers exist on first admin login", "Verify source badge reads `env_var`", "Verify Vault path is populated". J19 (new file) is 250 lines modeled on J01's 318-line structure, starting from a kind cluster pre-configured with `PLATFORM_OAUTH_GOOGLE_*` env vars; tests the new-user-signup flow including OAuth-provisioning + group-role-mapping application.

- **R10 — Rule 39 wording [RESEARCH-COMPLETE]**: `.specify/memory/constitution.md:235-239` (verbatim quoted in plan-grounding research): "Every secret resolves via SecretProvider. Code MUST NOT call os.getenv / os.Getenv directly for names matching secret patterns (`*_SECRET`, `*_PASSWORD`, `*_API_KEY`, `*_TOKEN`) outside SecretProvider implementation files. A CI static-analysis check enforces this." **Resolution**: The bootstrap module's Pydantic settings (`OAuthGoogleBootstrap.client_secret: SecretStr`, `client_secret_file: str | None`) are NOT direct `os.getenv` calls — they are Pydantic settings reads that the CI deny-list at `scripts/check-secret-access.py` already allows (per UPD-040 task T023's pattern walker which scans for AST `os.getenv("...")` calls with literal string args matching secret patterns). The `_FILE` path read uses `Path.read_text()` which is filesystem I/O (also exempt from the deny-list). Rule 39 is satisfied.

- **R11 — `OAuthConnectivityTestResponse` UI rendering [RESEARCH-COMPLETE]**: Verified at `auth/schemas.py:280-283` and `router_oauth.py:230-248`. The response is `{reachable: bool, auth_url_returned: bool, diagnostic: str}`. **Resolution**: Track B's NEW `OAuthProviderTestConnectivityButton.tsx` renders: a green checkmark icon when `reachable=true AND auth_url_returned=true`; a yellow warning icon when `reachable=true AND auth_url_returned=false` (provider reachable but config issue); a red X icon when `reachable=false`; the `diagnostic` string in a tooltip + a Toast notification on action completion. Loading spinner during the request.

- **R12 — `OAuthLink` count query [RESEARCH-COMPLETE]**: `auth/models.py:246-280` defines `OAuthLink` with FK to `OAuthProvider.id` (verified per research R12). **Resolution**: The status-panel "active linked users count" is `SELECT COUNT(DISTINCT user_id) FROM oauth_links WHERE provider_id = :id` — implemented as a new repository method `count_active_links(provider_id) -> int` on `OAuthRepository`. The query is cached per-pod for 60 seconds (matching the panel's refresh cadence) to avoid hot-path repeated DB hits.

## Phase 1 — Design Decisions

> Implementation tasks (in tasks.md) MUST honour these decisions or escalate via spec amendment.

### D1 — `OAuthBootstrapSettings` config block uses Pydantic `SecretStr` for secrets

`OAuthGoogleBootstrap.client_secret: SecretStr | None = None` AND `client_secret_file: str | None = None`. Pydantic's `SecretStr.__repr__` returns `**********`, preventing accidental logging via `repr(settings)`. Mutual-exclusivity validator: at most one of `client_secret` or `client_secret_file` may be set.

### D2 — Bootstrap module is async + idempotent + atomic

`bootstrap_oauth_providers_from_env` is one `async def` that wraps the upsert + Vault write + audit emission in a SINGLE database transaction (`async with session.begin()`). On any failure (Vault unreachable, validation error, audit emission failure), the transaction rolls back and the bootstrap raises `BootstrapConfigError` — the platform pod exits non-zero per spec edge case + Rule 43.

### D3 — Per-provider rate limits live in a NEW table, not a column

Per spec correction §12, the implementation choice (column vs table) is deferred to the plan phase. **Decision**: NEW table `oauth_provider_rate_limits` with `provider_id` FK + 6 integer columns. Reason: a future feature may add per-provider rate-limit RULES (e.g., per-IP-AND-per-user combinations); a separate table is more extensible than a single JSONB column. Migration 069 creates this table.

### D4 — Source enum: 3 values

`source: Mapped[Literal["env_var", "manual", "imported"]]`. Default `manual` for existing rows (the Alembic migration's `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT 'manual'` ensures backward compatibility). The bootstrap module sets `env_var` on upsert; the existing UPD-036 admin-edit flow sets `manual`; UPD-041's `platform-cli admin oauth import` sets `imported`.

### D5 — Audit `changed_fields` payload omits secret values entirely

The existing pattern at `oauth_service.py:177-189` emits `changed_fields` as a list of field NAMES that changed (not before/after VALUES). UPD-041's bootstrap follows this pattern: on first bootstrap, `changed_fields=["client_id", "redirect_uri", "allowed_domains", ...]`; on FORCE_UPDATE, the same list. The actual VALUES are stored ONLY in the database (the `oauth_providers` row itself); the audit ENTRY has only the metadata.

### D6 — Rotation cache flush is per-path, not full-cache

UPD-040's `SecretProvider.flush_cache(path: str | None = None)` (verified in UPD-040 task T042) supports both per-path AND full-cache flush. UPD-041's rotate-secret action calls `flush_cache(path="secret/data/musematic/{env}/oauth/{provider}/client-secret")` — flushes ONLY the rotated path, not other unrelated cached secrets. Tighter scope reduces the cache-warm-up overhead post-rotation.

### D7 — `force_update` overwrites BUT preserves the row's `client_secret_ref`

When `FORCE_UPDATE=true`, the bootstrap UPDATES non-secret columns (allowed_domains, redirect_uri, etc.) AND writes a new Vault KV v2 version. The `client_secret_ref` column points at the SAME Vault path; only the version inside Vault is bumped. This means existing audit-chain entries that reference `client_secret_ref="secret/data/musematic/staging/oauth/google/client-secret"` remain valid post-FORCE_UPDATE.

### D8 — Migration manifest is one-way (matches UPD-040's pattern)

`platform-cli admin oauth export` produces a YAML; `import` reads + applies. NO reverse-export. Operators wanting to roll back use the existing UPD-036 admin UI to manually edit providers. Mirrors UPD-040 design D8.

### D9 — `J19 New User Signup` is created in this feature

Per spec correction §9. Modeled on `test_j01_admin_bootstrap.py` (318 lines, 20 sequential `journey_step()` blocks per research R9). New file is ~250 lines; covers signup → Google OAuth → group-role-mapping application → first-login dashboard verification. Promoted to a shared journey-suite asset for future signup-touching features.

### D10 — UPD-039 documentation integration is BEST-EFFORT

If UPD-039 has landed by UPD-041's polish phase, the runbooks live under `docs/operator-guide/runbooks/`. If UPD-039 is delayed, the runbooks live in `specs/091-oauth-env-bootstrap/contracts/` and are merged into UPD-039 later. Mirrors UPD-040 design D10.

## Phase 2 — Track A Build Order (Backend bootstrap + admin endpoints)

**Days 1-3 (1 dev). Depends on UPD-040 (Wave 15) being on `main`.**

1. **Day 1 morning** — Pre-flight check: confirm UPD-040 is merged on `main` (`git log --oneline | grep "UPD-040"`); confirm `apps/control-plane/src/platform/common/secret_provider.py` exists with the consolidated Protocol; confirm `oauth_service._resolve_secret` (lines 732-747) has been rewired per UPD-040 task T011. If UPD-040 is not yet merged, BLOCK UPD-041 implementation per spec correction §7.
2. **Day 1 morning** — Author Alembic migration `069_oauth_provider_env_bootstrap.py` per design D3 + D4: 4 ALTER TABLE statements adding columns to `oauth_providers` (with `NOT NULL DEFAULT 'manual'` for `source` to ensure backward compatibility); CREATE TABLE for `oauth_provider_rate_limits`. Reversible downgrade.
3. **Day 1 afternoon** — Author `OAuthBootstrapSettings`, `OAuthGoogleBootstrap`, `OAuthGithubBootstrap` Pydantic blocks in `common/config.py` per design D1; add Pydantic validators for the FR-641 rules (HTTPS in production, mutual exclusivity of secret vs secret_file, JSON parseability for role mappings).
4. **Day 1 afternoon** — Update `auth/models.py` with the 4 new columns on `OAuthProvider` + the new `OAuthProviderRateLimit` model.
5. **Day 2 morning** — Author `auth/services/oauth_bootstrap.py` per design D2: single async function `bootstrap_oauth_providers_from_env(session_factory, settings, secret_provider, audit_service)`. Atomic transaction (upsert + Vault put + audit) per design D2. Idempotency check per Rule 42. FORCE_UPDATE override emits critical-severity audit entry per FR-640.
6. **Day 2 afternoon** — Wire bootstrap into `main.py:_lifespan` per research R1 — invoke AFTER the existing superadmin bootstrap at lines 517-527, conditional on `PLATFORM_OAUTH_*_ENABLED` env var presence.
7. **Day 2 afternoon** — Author 5 new admin endpoints in `auth/router_oauth.py` per research R2 (dual-prefix registration): `POST /rotate-secret`, `POST /reseed-from-env`, `GET /history`, `GET /rate-limits`, `PUT /rate-limits`. Each calls `_require_platform_admin(current_user)` per Rule 30. Pydantic request/response schemas added to `auth/schemas.py` per design D5 (`OAuthSecretRotateRequest` uses `SecretStr` for the new_secret field).
8. **Day 3 morning** — Implement service-layer methods on `OAuthService`: `rotate_secret`, `reseed_from_env`, `get_history`, `get_rate_limits`, `update_rate_limits`. Each emits the appropriate audit entry per the dual-emission pattern at research R6. Per design D6, `rotate_secret` calls `secret_provider.flush_cache(path=...)` after the Vault write.
9. **Day 3 afternoon** — Author `apps/control-plane/tests/auth/test_oauth_bootstrap.py` (~30 cases): valid bootstrap (Google), valid bootstrap (GitHub), missing CLIENT_ID, both CLIENT_SECRET and CLIENT_SECRET_FILE set, invalid JSON in GROUP_ROLE_MAPPINGS, unknown role in mapping, non-HTTPS redirect URI in production, idempotent skip, FORCE_UPDATE overwrite, Vault unreachable, race condition (2 simultaneous bootstrap calls).
10. **Day 3 afternoon** — Author `apps/control-plane/tests/auth/test_oauth_admin_endpoints.py` (~25 cases): rotate-secret (204 response, no secret in body, audit entry, cache flush), reseed (re-reads env vars, applies, returns diff), history (paginated, includes diffs), rate-limits get/put.

Day-3 acceptance: `pytest apps/control-plane/tests/auth/` passes (30+25 = 55+ new test cases); the bootstrap module is callable from `main.py:_lifespan` without runtime errors; the 5 new admin endpoints respond correctly to authenticated super-admin requests.

## Phase 3 — Track B Build Order (Admin UI extensions)

**Days 1-3 (1 dev). Can start day 1 in parallel with Track A — depends on Track A's Pydantic schemas (Day 2 afternoon) for the API contract.**

11. **Day 1 morning** — Author `OAuthProviderSourceBadge.tsx` (~50 lines) per FR-643: 3-color shadcn `Badge` rendering `env_var` (blue), `manual` (gray), `imported` (purple). Includes accessibility labels for screen readers.
12. **Day 1 morning** — Author `OAuthProviderTestConnectivityButton.tsx` (~100 lines) per spec correction §2 + research R11. Calls the existing backend endpoint at `router_oauth.py:220-248`; renders `OAuthConnectivityTestResponse` shape (reachable, auth_url_returned, diagnostic) with appropriate icons + Toast on completion.
13. **Day 1 afternoon** — Author `OAuthProviderRotateSecretDialog.tsx` (~150 lines) per Rule 44 + spec User Story 3. Write-only `PasswordInput` component (NEVER pre-filled with current value); confirmation step; submits to `POST /rotate-secret` and expects 204; closes on success with Toast "Secret rotated successfully".
14. **Day 1 afternoon** — Author `OAuthProviderReseedDialog.tsx` (~120 lines) per FR-643. Confirmation copy explains "this may overwrite manual changes". On Confirm, calls `POST /reseed-from-env`; renders the diff response.
15. **Day 2 morning** — Refactor `OAuthProviderAdminPanel.tsx`'s `ProviderConfigCard` per Phase 0 R3: introduce shadcn `Tabs` with 5 tabs (Configuration, Status, Role Mappings, History, Rate Limits). The existing form moves into the Configuration tab unchanged.
16. **Day 2 morning** — Author `OAuthProviderStatusPanel.tsx` (~120 lines) per FR-643. 4-stat `Card` strip: last successful auth (from new `last_successful_auth_at` column), 24h auth count, 7d auth count, 30d auth count, active linked users count. Queries to dedicated endpoints OR a single status endpoint (decision deferred to Track A — see T021 in tasks).
17. **Day 2 afternoon** — Author `OAuthProviderRoleMappingsTable.tsx` (~250 lines) per User Story 4. Managed table with shadcn `Table` + per-row edit/delete `Button`s + add-row `Form`. Validation: group format regex (Google: email; GitHub: `org/team`); role select dropdown populated from a `/api/v1/admin/roles` endpoint (verify exists during T030; if missing, hardcode the canonical 6 roles from the constitution).
18. **Day 3 morning** — Author `OAuthProviderHistoryTab.tsx` (~200 lines) per FR-644. Paginated table with timestamp, admin principal, change summary; expandable rows render before/after diff using a JSON-diff visualization (e.g., `react-diff-viewer-continued` if already in dependencies — verify during T031; otherwise use `<pre>` + manual diff highlighting).
19. **Day 3 morning** — Author `OAuthProviderRateLimitsTab.tsx` (~150 lines) per FR-646 + spec correction §12. Form with 6 numeric inputs (per_ip_max, per_ip_window, per_user_max, per_user_window, global_max, global_window); save calls `PUT /rate-limits`.
20. **Day 3 afternoon** — i18n integration: extract all new strings to `apps/web/messages/en.json` under `admin.oauth.*` namespace (~30 keys); commit with TODO markers for the 5 other locales (vendor-translated per UPD-039 / FR-620). Run axe-core scan locally; verify zero AA violations.

Day-3 acceptance: visiting `/admin/settings?tab=oauth` shows the extended panel with all 5 sub-tabs; each new sub-component renders correctly against the live backend; `pnpm test` passes; axe-core scan clean.

## Phase 4 — Track C Build Order (CLI + E2E + journey)

**Days 4-6 (1 dev). Depends on Track A (admin endpoints functional) + Track B (UI button references).**

21. **Day 4 morning** — Author `apps/ops-cli/src/platform_cli/commands/admin/oauth.py` Typer sub-app per FR-645: `export(env, output)` subcommand reads providers from the database via the admin REST API + emits YAML; `import(input, dry_run, apply)` reads YAML + validates Vault paths exist via `secret_provider.list_versions()` per Rule 43 + design D8 + spec User Story 5. Both subcommands depend on the existing `platform-cli admin` Typer app's auth + HTTP client utilities.
22. **Day 4 afternoon** — Register `oauth_app` in `commands/admin/__init__.py` per the existing `platform-cli admin` sub-app pattern (research R7).
23. **Day 4 afternoon** — Author `apps/ops-cli/tests/commands/admin/test_oauth.py` (~15 cases): export produces valid YAML, export omits secret values, export is idempotent (2 consecutive exports identical), import dry-run validates Vault paths, import fails on missing path, import applies + emits audit, round-trip (export from staging + import to production with mock Vault).
24. **Day 5 morning** — Author E2E suite at `tests/e2e/suites/oauth_bootstrap/` (8 test files per spec User Story 1-5 + spec edge cases): each test file has 2-5 test functions; total ~640 lines. Conftest sets up a kind cluster with Vault populated + env vars set; runs the platform pod; asserts behaviour.
25. **Day 5 afternoon** — Extend `tests/e2e/journeys/test_j01_admin_bootstrap.py` per spec correction §9: add 3 new `journey_step()` blocks BEFORE the existing step 4 ("Verify env-var-bootstrapped Google + GitHub providers exist on first admin login", "Verify source badge reads `env_var`", "Verify Vault path is populated"). Total addition: ~50 lines.
26. **Day 6 morning** — Create `tests/e2e/journeys/test_j19_new_user_signup.py` per spec correction §9 + design D9. Modeled on J01's structure (research R9). 20 sequential `journey_step()` blocks. Total: ~250 lines. Covers: signup-page render → Google OAuth flow → group-role-mapping applied → first-login dashboard render → user can perform first action.
27. **Day 6 afternoon** — Wire UPD-041's E2E suite into UPD-040's matrix-CI: add `tests/e2e/suites/oauth_bootstrap/` to the existing matrix-CI job's test path; verify the suite runs in all 3 modes (`mock`, `kubernetes`, `vault`) — `mock` mode tests assert that bootstrap is SKIPPED when Vault is unreachable (mock mode has no Vault); `kubernetes` mode tests assert bootstrap writes to K8s Secrets (transitional path); `vault` mode tests assert bootstrap writes to real Vault.

Day-6 acceptance: `pytest tests/e2e/suites/oauth_bootstrap/` passes on a kind cluster with UPD-040's `vault.mode=dev` + `PLATFORM_OAUTH_GOOGLE_ENABLED=true`; J01 + J19 journey tests pass on the matrix CI; the operator-CLI export+import round-trip succeeds.

## Phase 5 — Helm chart + secret-leak CI extension

**Days 5-6 (overlapping with Track C).**

28. **Day 5 morning** — Author `oauth.{google,github}.*` block in `deploy/helm/platform/values.yaml` per FR-642 + research R8. Each value annotated with `# --` comment for UPD-039 / FR-611 helm-docs auto-generation.
29. **Day 5 morning** — Modify `deploy/helm/platform/templates/deployment-control-plane.yaml`: inject `PLATFORM_OAUTH_*` env vars from the `oauth.*` values block; mount `clientSecretRef` Kubernetes Secret as a file at `/etc/secrets/{provider}-client-secret` if set; the bootstrap reads via `_FILE` path per User Story 1 setup.
30. **Day 5 afternoon** — Extend UPD-040's `scripts/check-secret-access.py` with the 2 new secret patterns (`OAUTH_SECRET_*` legacy fallback NOW REMOVED per spec correction §7; `PLATFORM_OAUTH_*_CLIENT_SECRET` is allowed only in `oauth_bootstrap.py` and `oauth_service.py`). Verify the existing Track A code passes the check.
31. **Day 6 morning** — Verify UPD-039's `scripts/generate-env-docs.py` (if landed) auto-generates the `PLATFORM_OAUTH_*` env-var entries with the `sensitive` classification per FR-700 (UPD-040 inheritance). Per FR-647 — CI fails any PR adding a new OAuth env var without regenerating the docs reference.

Day-6 acceptance: `helm install platform deploy/helm/platform/ --set oauth.google.enabled=true --set oauth.google.clientId=... --set oauth.google.clientSecretRef.name=...` brings up the platform with the bootstrap running on first pod-start; the auto-doc env-var reference includes the new vars.

## Phase 6 — SC verification + documentation polish

**Days 7-9 (1 dev — overlaps Phase 4-5).**

32. **Day 7** — Run the full SC verification sweep per the spec's 20 SCs. For each SC, document the actual measurement (e.g., SC-001's "5 seconds from pod startup" — measured wall-clock time on a synthetic kind cluster). Capture the verification record at `specs/091-oauth-env-bootstrap/contracts/sc-verification.md`.
33. **Day 8** — Author operator runbooks: `docs/operator-guide/runbooks/oauth-bootstrap.md` (env-var bootstrap walkthrough); `docs/operator-guide/runbooks/oauth-secret-rotation.md` (rotation flow). Per design D10 — if UPD-039 has not landed, these live in `specs/091-oauth-env-bootstrap/contracts/` and merge into UPD-039 later.
34. **Day 8 afternoon** — Modify `docs/admin-guide/oauth-providers.md` per UPD-039 admin guide: add sections for rotation, reseed, role mappings, history, rate limits.
35. **Day 9** — Final review pass; address PR feedback; verify `pytest apps/control-plane/tests/auth/`, `pytest apps/ops-cli/tests/`, `pytest tests/e2e/suites/oauth_bootstrap/`, and the J01 + J19 journey tests all pass; verify zero plaintext-secret regex hits in 24-hour kind-cluster log capture per User Story 1 acceptance scenario 5; merge.

## Effort & Wave

**Total estimated effort: 8-10 dev-days** (5-6 wall-clock days with 3 devs in parallel: 1 on Track A, 1 on Track B, 1 on Track C+Helm; Phase 6 is split across all 3 devs).

The brownfield's "4.5 days (4 points)" understates by ~50% because it does not account for: (a) the 4-column Alembic migration with backward-compatible defaults + the new rate-limits table (~0.5 day); (b) the 8 new UI sub-components with i18n integration across 6 locales + Playwright coverage (~1.5 days beyond the bare 1.5-day brownfield estimate); (c) the 5 new Pydantic schemas + 7 new audit-event payloads (~0.5 day); (d) the J19 journey CREATION (NOT extension — brownfield mistake per spec correction §9) at ~1 day for a 250-line file modeled on J01's 318-line structure; (e) the operator runbook authoring (~0.5 day). The corrected estimate aligns with the v1.3.0 cohort's pattern of brownfield-understated estimates (per features 085-090's plan corrections).

**Wave: Wave 16 — last in the v1.3.0 audit-pass cohort.** Position in execution order:
- Wave 11 — UPD-036 Administrator Workbench (delivers `/admin/settings?tab=oauth` tab — UPD-041 dependency)
- Wave 12 — UPD-037 Public Signup Flow (delivers signup OAuth UI + test-connectivity backend — UPD-041 dependency)
- Wave 13 — UPD-038 Multilingual README
- Wave 14 — UPD-039 Documentation Site (delivers env-var auto-doc + helm-docs auto-gen — UPD-041 integration point)
- Wave 15 — UPD-040 HashiCorp Vault Integration (delivers `SecretProvider` + Vault client + matrix CI — UPD-041 hard dependency)
- **Wave 16 — UPD-041 OAuth Env-Var Bootstrap + Admin UI** (this feature)

**Cross-feature dependency map**:
- UPD-041 HARD-DEPENDS on UPD-040 (cannot start without `SecretProvider`).
- UPD-041 INTEGRATES with UPD-036 (extends `OAuthProviderAdminPanel.tsx` tab).
- UPD-041 INTEGRATES with UPD-037 (reuses `OAuthProviderButtons.tsx` + the dedicated callback page; uses the existing test-connectivity backend endpoint).
- UPD-041 INTEGRATES with UPD-039 (env-var + helm-docs + runbook auto-flow).
- UPD-041 INHERITS UPD-040's matrix CI pattern.
- UPD-041 INHERITS UPD-085's E2E test harness.

## Risk Assessment

**Low-medium risk overall.** UPD-041 is well-scoped + builds on proven backends, BUT the hard dependency on UPD-040 introduces schedule risk.

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **R1: UPD-040 delayed past UPD-041 start** | Medium | High (UPD-041 is fully blocked) | UPD-041 BLOCKS until UPD-040 ships; no transitional path per Rule 43 + spec correction §7. The Wave 15→16 sequencing is constitutional, not negotiable. |
| **R2: Env-var validation gaps cause crash on startup** | Low | High (operational outage) | Comprehensive Pydantic validators per FR-641 + 30+ unit tests covering each edge case from spec; bootstrap fails fast with clear error messages. |
| **R3: Idempotency edge cases (partial failure)** | Low | Medium (inconsistent state) | Atomic transaction per design D2: upsert + Vault put + audit emit in a single `async with session.begin()`; rollback on any failure. |
| **R4: Admin UI regressions in the existing form** | Medium | Medium (UPD-036 contract violated) | Track B's tabs structure (research R3 + design D5) wraps the EXISTING form unchanged in a "Configuration" tab; UPD-036's existing tests must pass; SC-020 verifies. |
| **R5: Secret leak via API response** | Low | High (compliance issue) | Pydantic `SecretStr` for `OAuthSecretRotateRequest.new_secret` (design D1); rotate-secret endpoint returns `204 No Content` (no response body); CI deny-list at `scripts/check-secret-access.py` extended in T030. |
| **R6: J19 journey test underscoped** | Medium | Low (E2E coverage gap) | Modeled on J01's 318-line structure (research R9); 20 sequential journey_step() blocks with explicit assertions; reused in future signup-touching features. |
| **R7: i18n catalog drift** | Medium | Low (untranslated strings) | Per UPD-039 / FR-620 — vendor-translated catalogs; UPD-088's parity check (already shipped) catches drift; the 7-day grace window applies. |
| **R8: Rate-limits table is over-engineered** | Low | Low (YAGNI risk) | Per design D3 — separate table is more extensible than a column for future per-rule complexity; 6 columns is small; no perf concern. |

## Plan-correction notes (vs. brownfield input)

1. **Effort estimate corrected from 4.5 days to 8-10 dev-days.** Brownfield understates by ~50% (consistent with features 085-090's pattern).
2. **Wave placement: Wave 16 (LAST in v1.3.0 cohort).** Brownfield correctly identifies Wave 16; this plan reaffirms.
3. **Hard dependency on UPD-040 (Wave 15).** Brownfield says "Running without UPD-040 falls back to `PLATFORM_VAULT_MODE=kubernetes` which still works but sacrifices rotation". CORRECTED per Rule 43 + spec correction §7: UPD-041 is BLOCKED until UPD-040 ships; there is no transitional path that writes secrets to a non-Vault location. The `kubernetes` mode in UPD-040 ITSELF satisfies UPD-041's requirements (writes K8s Secrets at canonical paths via `KubernetesSecretProvider`); this is NOT the same as bypassing UPD-040.
4. **Admin UI route is `/admin/settings?tab=oauth`, NOT `/admin/oauth-providers`.** Per spec correction §1 + research R3.
5. **Test-connectivity UI button is NEW in this feature** per spec correction §2; the brownfield's Track A includes it but does not flag the UI gap.
6. **5 NEW admin endpoints (NOT 4).** The brownfield lists 5 actions (rotate / test-connectivity / reseed / history / rate-limits-get-put); test-connectivity backend ALREADY EXISTS per spec correction §2; the 5 NEW endpoints are: rotate-secret, reseed-from-env, history, rate-limits-get, rate-limits-put.
7. **4 NEW database columns + 1 NEW table.** Per spec correction §5 + design D3 + D4.
8. **Audit event names follow `auth.oauth.{action}` convention** (NOT `oauth.provider.{action}`) per spec correction §8 + research R6.
9. **J19 must be CREATED, not extended** per spec correction §9 + research R9.
10. **Constitutional Rules 39, 42, 43, 44 are first-class anchors** (NOT just Rule 10 as the brownfield mentions).
11. **Configuration export/import is OAuth-PROVIDER-CONFIG-ONLY** per spec correction §11.
12. **Per-provider rate limits coexist with global** per spec correction §12.
13. **Bootstrap insertion point is AFTER `bootstrap_superadmin_from_env`** (not just "after Vault authentication" as the brownfield says) per research R1.
14. **Helm secret-mounting paths follow UPD-040's discipline** — `clientSecretRef` is a Kubernetes Secret reference; `clientSecretVaultPath` references an already-populated Vault path. The bootstrap chooses the right path per planning-input's precedence list.

## Complexity Tracking

| Area | Complexity | Why |
|---|---|---|
| `OAuthBootstrapSettings` config block | Low | Mirrors existing `AuthSettings` pattern; Pydantic validators are mechanical. |
| Bootstrap module | Medium | Atomic transaction + idempotency + FORCE_UPDATE override + Vault integration; ~30 unit tests. |
| 5 new admin endpoints | Medium | 5 Pydantic schemas + 5 service methods + 5 audit-event types; dual-prefix registration. |
| Alembic migration | Low | 4 columns + 1 table; backward-compatible defaults. |
| 8 new UI sub-components | High | 600 lines net + i18n + Playwright coverage; the role-mappings managed table is the trickiest. |
| Operator CLI export/import | Medium | YAML serialization + Vault path validation + diff preview; 15 tests. |
| 8 E2E test files + J01 extension + J19 creation | Medium | ~640 lines + ~50 lines + ~250 lines = ~940 lines total. |
| Helm values + Deployment template | Low | New top-level block + env-var injection + optional file mount. |
| UPD-039 documentation integration | Low | Best-effort runbooks + admin-guide section additions. |

**Net complexity: low-medium.** The hard dependency on UPD-040 is the highest-risk piece; once UPD-040 ships, UPD-041 is mechanical.
