# Tasks: UPD-041 — OAuth Provider Environment-Variable Bootstrap and Extended Super Admin UI

**Feature**: 091-oauth-env-bootstrap
**Branch**: `091-oauth-env-bootstrap`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

User stories (from spec.md):
- **US1 (P1)** — GitOps deployment with pre-configured OAuth via `PLATFORM_OAUTH_GOOGLE_*` / `PLATFORM_OAUTH_GITHUB_*` env vars; secrets land in Vault at canonical paths; login + signup pages render OAuth buttons within 5 seconds of pod startup.
- **US2 (P1)** — Idempotent reinstall preserves manual adjustments per Rule 42; `FORCE_UPDATE=true` overwrites with critical audit entry.
- **US3 (P1)** — Super admin rotates client secret via Vault KV v2 versioning per Rule 44; modal write-only input; 204 response NEVER returns the new secret.
- **US4 (P2)** — Group/team role mappings managed table; new mappings apply to future logins only.
- **US5 (P2)** — `platform-cli admin oauth export|import` for GitOps promotion (dev → staging → production); SHA-256-only manifest; Vault path validation before apply.

Independent-test discipline: every US MUST be verifiable in isolation. US1 = bootstrap + login button visibility on a fresh kind cluster. US2 = manual edit + helm upgrade verification + FORCE_UPDATE override audit. US3 = rotate-secret + KV v2 v2 write + 204 response + cache flush. US4 = role-mapping table + first-time-OAuth user provisioned with mapped role. US5 = staging export → production import with Vault path validation.

**Wave-16 sub-division** (per plan.md "Effort & Wave"):
- W16.0 — Setup: T001-T004
- W16A — Track A Backend bootstrap + admin endpoints (depends on UPD-040 / Wave 15): T005-T036
- W16B — Track B Admin UI extensions (depends on Track A schemas): T037-T065
- W16C — Track C CLI + E2E + journey tests: T066-T085
- W16D — Helm chart + secret-leak CI: T086-T091
- W16E — SC verification + documentation polish: T092-T105

---

## Phase 1: Setup

- [x] T001 [W16.0] Verify the on-disk repo state per plan.md "Phase 0 — Research" + spec.md scope-discipline section: confirm UPD-040 (Wave 15) is on `main` (`git log --oneline | grep "UPD-040"`); confirm `apps/control-plane/src/platform/common/secret_provider.py` exists with the consolidated `SecretProvider` Protocol + `VaultSecretProvider` + `KubernetesSecretProvider` + `MockSecretProvider`; confirm `apps/control-plane/src/platform/auth/services/oauth_service.py:732-747` has been rewired by UPD-040 task T011 to delegate to `SecretProvider.get`; confirm `apps/control-plane/src/platform/auth/router_oauth.py:173-274` has the 4 existing admin endpoints; confirm `apps/web/components/features/auth/OAuthProviderAdminPanel.tsx` is 382 lines with no test-connectivity button. Document the inventory in `specs/091-oauth-env-bootstrap/contracts/repo-inventory.md` (NEW file). If UPD-040 is NOT merged, BLOCK UPD-041 implementation per spec correction §7.
- [x] T002 [P] [W16.0] Verify the migration sequence per plan.md research R7: open `apps/control-plane/migrations/versions/` and confirm the highest existing migration number; if UPD-040's migrations have shifted the count past 068 to 069+, document the actual next sequence in `specs/091-oauth-env-bootstrap/contracts/migration-sequence.md` (NEW file). UPD-041's migration uses the verified next sequence number (default `069`; may be `070`+ if UPD-040 owns intervening migrations).
- [x] T003 [P] [W16.0] Verify the constitutional anchors per plan.md Constitutional Anchors table: open `.specify/memory/constitution.md` and confirm Rule 10 (lines 123-126) + Rule 30 (lines 198-202) + Rule 31 (lines 203-207) + Rule 39 (lines 235-239) + Rule 42 (lines 249-251) + Rule 43 (lines 252-254) + Rule 44 (lines 255-257). If any rule has been renumbered or rewritten, escalate via spec amendment before authoring code. Document confirmation (or required amendment) in `specs/091-oauth-env-bootstrap/contracts/constitution-confirmation.md` (NEW file).
- [x] T004 [P] [W16.0] Cross-feature coordination check per plan.md "Cross-feature dependency map": confirm UPD-036 (Administrator Workbench — feature 086) has shipped `OAuthProviderAdminPanel.tsx` AND `AdminSettingsPanel.tsx` tab registration at lines 33-36; confirm UPD-037 (Public Signup — feature 087) has shipped `OAuthProviderButtons.tsx` + the dedicated callback page + the test-connectivity backend at `router_oauth.py:220-248`; confirm UPD-039 (Documentation — feature 089) status — if landed, the FR-647 CI gate uses `scripts/generate-env-docs.py`; if not landed, document the deferred CI integration in `specs/091-oauth-env-bootstrap/contracts/cross-feature-deps.md` (NEW file).

---

## Phase 2: Track A — Backend Bootstrap + Admin Endpoints

**Story goal**: NEW `oauth_bootstrap.py` invoked from `main.py:_lifespan` AFTER `bootstrap_superadmin_from_env`; 4 new columns + 1 new table via Alembic 069; 5 new admin endpoints with dual-prefix registration; 7 new audit-event types following `auth.oauth.{action}` convention. Honors Rule 10 + Rule 30 + Rule 31 + Rule 39 + Rule 42 + Rule 43 + Rule 44.

### Alembic migration

- [x] T005 [W16A] [US1, US4] Create `apps/control-plane/migrations/versions/069_oauth_provider_env_bootstrap.py` (or the verified next-sequence number from T002) per plan.md design D3 + D4: 4 ALTER TABLE statements adding columns to `oauth_providers` — `source: ENUM("env_var", "manual", "imported") NOT NULL DEFAULT 'manual'` (backward-compatible default), `last_edited_by: UUID FK to users.id NULLABLE`, `last_edited_at: timestamptz NULLABLE`, `last_successful_auth_at: timestamptz NULLABLE`. CREATE TABLE `oauth_provider_rate_limits` per spec correction §12: `provider_id UUID FK to oauth_providers.id ON DELETE CASCADE`, 6 integer columns (`per_ip_max`, `per_ip_window`, `per_user_max`, `per_user_window`, `global_max`, `global_window`). Reversible downgrade.
- [x] T006 [W16A] Run `alembic upgrade head` locally against a test DB; verify the migration applies cleanly + verify `alembic downgrade -1` removes the 4 columns + 1 table without data loss in the existing 12 columns of `oauth_providers` per SC-019.

### `OAuthProvider` SQLAlchemy model + repository

- [x] T007 [W16A] [US1, US4] Modify `apps/control-plane/src/platform/auth/models.py:223-243` per plan.md "Source Code" section: add 4 new mapped columns on `OAuthProvider` (`source: Mapped[Literal["env_var", "manual", "imported"]] = mapped_column(default="manual")`, `last_edited_by: Mapped[UUID | None]`, `last_edited_at: Mapped[datetime | None]`, `last_successful_auth_at: Mapped[datetime | None]`). Preserve the existing 12 columns unchanged.
- [x] T008 [W16A] [US4] Add NEW `class OAuthProviderRateLimit(Base, UUIDMixin, TimestampMixin)` model to `apps/control-plane/src/platform/auth/models.py` per spec correction §12: `provider_id: Mapped[UUID] = mapped_column(ForeignKey("oauth_providers.id", ondelete="CASCADE"))`, 6 integer columns matching the migration. Add a `rate_limits: Mapped[OAuthProviderRateLimit | None] = relationship(...)` back-reference on `OAuthProvider`.
- [x] T009 [W16A] Modify `apps/control-plane/src/platform/auth/services/oauth_repository.py` (verified file path during T009 — likely `auth/services/oauth_service.py` repository inner class OR `auth/repositories/oauth_repository.py`): add `get_by_type_for_update(provider_type) -> OAuthProvider | None` (uses `SELECT ... FOR UPDATE SKIP LOCKED` for race-safe bootstrap per spec edge case "concurrent bootstrap from 2+ pods"); add `get_history(provider_id, limit, cursor) -> list[OAuthAuditEntry]` (paginated query against the existing `oauth_audit_entries` table per FR-644); add `count_active_links(provider_id) -> int` (per plan.md research R12: `SELECT COUNT(DISTINCT user_id) FROM oauth_links WHERE provider_id = ?`).

### Pydantic config block (`OAuthBootstrapSettings`)

- [x] T010 [W16A] [US1] Modify `apps/control-plane/src/platform/common/config.py` per plan.md design D1 + spec correction §4: add NEW classes `class OAuthGoogleBootstrap(BaseSettings)` with `model_config = SettingsConfigDict(env_prefix="OAUTH_GOOGLE_", extra="ignore")`. Fields: `enabled: bool = False`, `client_id: str = ""`, `client_secret: SecretStr | None = None` (uses Pydantic `SecretStr` per design D1 — `__repr__` returns `**********`), `client_secret_file: str | None = None`, `redirect_uri: str = ""`, `allowed_domains: list[str] = []`, `group_role_mappings: dict[str, str] = {}`, `require_mfa: bool = False`, `default_role: str = "member"`, `force_update: bool = False`. Validators: HTTPS in production (Pydantic `model_validator(mode="after")` per FR-641); mutual exclusivity of `client_secret` vs `client_secret_file`; client_id format check (Google: `.apps.googleusercontent.com`); JSON parseability for `group_role_mappings` (handled by Pydantic dict type).
- [x] T011 [W16A] [US1] Add `class OAuthGithubBootstrap(BaseSettings)` mirroring `OAuthGoogleBootstrap` per spec User Story 1 brownfield table: `env_prefix="OAUTH_GITHUB_"`, fields `enabled`, `client_id` (alphanumeric format check), `client_secret`, `client_secret_file`, `redirect_uri`, `allowed_orgs: list[str] = []`, `team_role_mappings: dict[str, str] = {}`, `require_mfa`, `default_role`, `force_update`.
- [x] T012 [W16A] [US1] Add `class OAuthBootstrapSettings(BaseSettings)` to `common/config.py` with `model_config = SettingsConfigDict(env_prefix="OAUTH_", extra="ignore")` (resolved as `PLATFORM_OAUTH_*` through the parent prefix); fields: `google: OAuthGoogleBootstrap = Field(default_factory=OAuthGoogleBootstrap)`, `github: OAuthGithubBootstrap = Field(default_factory=OAuthGithubBootstrap)`. Add `oauth_bootstrap: OAuthBootstrapSettings = Field(default_factory=OAuthBootstrapSettings)` field on `PlatformSettings`.
- [x] T013 [W16A] [US1] Author `apps/control-plane/tests/common/test_oauth_bootstrap_settings.py` (NEW pytest test file): ~12 cases — valid Google config, valid GitHub config, missing CLIENT_ID with ENABLED=true, both CLIENT_SECRET and CLIENT_SECRET_FILE set (raises mutual-exclusivity error), invalid JSON in role mappings (Pydantic raises ValidationError), unknown role in mapping (validator queries platform role catalog and rejects), non-HTTPS redirect URI in production (raises validation error), non-HTTPS allowed in dev with `ALLOW_INSECURE=true`, FORCE_UPDATE flag, default-empty config (no env vars set). `pytest -v` passes.

### Bootstrap module (`oauth_bootstrap.py`)

- [x] T014 [W16A] [US1] Create `apps/control-plane/src/platform/auth/services/oauth_bootstrap.py` (NEW per FR-639 + Rule 42 + plan.md design D2): single async function `async def bootstrap_oauth_providers_from_env(session_factory, settings, secret_provider, audit_service)`. Reads `settings.oauth_bootstrap.google` + `settings.oauth_bootstrap.github`; for each enabled provider: validates per FR-641 (raises `BootstrapConfigError` on validation failure), reads existing row via `oauth_repository.get_by_type_for_update(provider_type)` (race-safe lock), branches on `existing AND not force_update` (skip with structured-log entry per Rule 42), writes the secret to Vault via `await secret_provider.put(path=f"secret/data/musematic/{settings.environment}/oauth/{provider_type}/client-secret", values={"value": secret_str})`, upserts the provider row with `source="env_var"` + `last_edited_at=datetime.utcnow()` + `last_edited_by=None` (system-driven), emits audit entry per design D5.
- [x] T015 [W16A] [US1, US2] Implement secret resolution per planning-input precedence list + spec correction §7: helper function `_resolve_client_secret(provider_config: OAuthGoogleBootstrap | OAuthGithubBootstrap) -> str` returns the secret value from one of: (1) `provider_config.client_secret.get_secret_value()` if set; (2) `Path(provider_config.client_secret_file).read_text().strip()` if set; (3) raise `BootstrapConfigError("client_secret OR client_secret_file required")`. The `Path.read_text()` is filesystem I/O (exempt from Rule 39 `os.getenv` deny-list per plan.md research R10). The returned value is IMMEDIATELY written to Vault and never persisted in any other location.
- [x] T016 [W16A] [US2] Implement idempotency + FORCE_UPDATE per Rule 42 + FR-640: when `existing AND not force_update`, log `{event: "auth.oauth.bootstrap_skipped", provider: provider_type, reason: "existing_provider_no_force_update"}` and return; when `existing AND force_update`, emit a CRITICAL-severity audit entry `auth.oauth.config_reseeded` with metadata `{force_update: true, overrode_source: existing.source}` BEFORE the upsert; the upsert sets `source="env_var"` (overriding any prior `source="manual"`).
- [x] T017 [W16A] [US1] Implement atomic-transaction wrapper per design D2: `async with session_factory() as session: async with session.begin(): ...` — the upsert + Vault put + audit emission run inside a single transaction; on any exception, rollback + re-raise `BootstrapConfigError`. The platform pod exits non-zero when this raises (per `main.py:_lifespan` existing pattern at lines 517-527).
- [x] T018 [W16A] [US1] Implement existing-provider-from-other-source skip per spec edge case: if `existing.source not in ("manual", "env_var", None)` (e.g., `source="ibor"` from a future IBOR-sync feature), emit a warning `{event: "auth.oauth.bootstrap_skipped", provider: provider_type, reason: "existing_provider_external_source", source: existing.source}` and return without modifying the row.
- [x] T019 [W16A] [US1] Author `apps/control-plane/tests/auth/test_oauth_bootstrap.py` (NEW pytest test file): ~30 cases per plan.md Phase 2 day 3 afternoon: valid bootstrap (Google), valid bootstrap (GitHub), idempotent re-run (no audit emission), FORCE_UPDATE overwrite (critical audit emission), missing CLIENT_ID raises BootstrapConfigError, invalid JSON role mapping, unknown role, non-HTTPS in production, Vault unreachable (raises BootstrapConfigError, no DB write per Rule 43), partial failure (Vault put succeeds but audit emission fails — rollback verified), race condition (2 concurrent bootstrap calls — second sees first's row via row-lock and skips), existing provider with `source="ibor"` (skip with warning), `enabled=false` (no-op skip), both providers configured. `pytest -v` passes.

### Wire bootstrap into `main.py:_lifespan`

- [x] T020 [W16A] [US1] Modify `apps/control-plane/src/platform/main.py:_lifespan` per plan.md research R1: insert the bootstrap call IMMEDIATELY AFTER the existing `bootstrap_superadmin_from_env(...)` call at lines 517-527, BEFORE rubric/clickhouse setup at line 529. Wrap in the same try/except pattern: catch `BootstrapConfigError` → re-raise (pod exits non-zero per Rule 43); catch generic Exception → set `app.state.degraded = True` + log warning. Conditional gate: `if oauth_bootstrap_enabled(settings):` — only invoke when at least one of `settings.oauth_bootstrap.google.enabled` / `settings.oauth_bootstrap.github.enabled` is True.

### 5 new admin endpoints

- [x] T021 [W16A] [US3] Add `class OAuthSecretRotateRequest(BaseModel)` to `apps/control-plane/src/platform/auth/schemas.py` (extend lines 208-303): `new_secret: SecretStr` (per plan.md design D1 — `SecretStr` prevents accidental logging via repr). NO response model (the rotate endpoint returns 204 per Rule 44).
- [x] T022 [P] [W16A] [US2] Add `class OAuthConfigReseedRequest(BaseModel)` to schemas.py: `force_update: bool = False`. Response model `OAuthConfigReseedResponse(diff: dict[str, Any])` returning the list of changed fields (NOT values per design D5).
- [x] T023 [P] [W16A] [US4] Add `class OAuthRateLimitConfig(BaseModel)` to schemas.py: 6 integer fields matching `OAuthProviderRateLimit` model. Same model used for GET response + PUT request.
- [x] T024 [P] [W16A] [US4] Add `class OAuthHistoryEntryResponse(BaseModel)` + `OAuthHistoryListResponse(BaseModel)` to schemas.py: HistoryEntry has `timestamp: datetime`, `admin_id: UUID | None`, `action: str`, `before: dict[str, Any] | None`, `after: dict[str, Any] | None`. ListResponse has `entries: list[OAuthHistoryEntryResponse]`, `next_cursor: str | None`.
- [x] T025 [W16A] [US3] Add `POST /api/v1/admin/oauth-providers/{provider}/rotate-secret` endpoint to `apps/control-plane/src/platform/auth/router_oauth.py` per plan.md research R2 (dual-prefix registration with the legacy `/api/v1/admin/oauth/providers/...` path with `include_in_schema=False`): handler `async def rotate_oauth_secret(provider, body: OAuthSecretRotateRequest, current_user, oauth_service)`. Calls `_require_platform_admin(current_user)` per Rule 30. Calls `await oauth_service.rotate_secret(provider, body.new_secret.get_secret_value(), actor_id=current_user["sub"])`. Returns `Response(status_code=204)` per Rule 44 — the response body is empty.
- [x] T026 [P] [W16A] [US2] Add `POST /api/v1/admin/oauth-providers/{provider}/reseed-from-env` endpoint: handler `async def reseed_oauth_provider(provider, body: OAuthConfigReseedRequest, current_user, settings, secret_provider, oauth_service)`. Calls `_require_platform_admin(current_user)`. Re-invokes the bootstrap module's logic with `force_update=body.force_update`; returns the diff. If `PLATFORM_OAUTH_GOOGLE_ENABLED` is not set in the running pod, returns 400 with `"PLATFORM_OAUTH_GOOGLE_ENABLED is not set in the running pod; cannot reseed"` per spec edge case.
- [x] T027 [P] [W16A] [US4] Add `GET /api/v1/admin/oauth-providers/{provider}/history` endpoint per FR-644: handler `async def get_oauth_provider_history(provider, limit: int = 100, cursor: str | None = None, current_user, oauth_repository) -> OAuthHistoryListResponse`. Calls `_require_platform_admin(current_user)`. Queries via `await oauth_repository.get_history(provider_id, limit, cursor)`.
- [x] T028 [P] [W16A] [US4] Add `GET /api/v1/admin/oauth-providers/{provider}/rate-limits` endpoint per FR-646: handler returns `OAuthRateLimitConfig` from the new `oauth_provider_rate_limits` table; if no row exists, returns the default global config from `AuthSettings.oauth_rate_limit_*` (the existing fields from research §10).
- [x] T029 [P] [W16A] [US4] Add `PUT /api/v1/admin/oauth-providers/{provider}/rate-limits` endpoint per FR-646: handler accepts `OAuthRateLimitConfig` body; upserts into the `oauth_provider_rate_limits` table; emits `auth.oauth.rate_limit_updated` audit entry.

### Service-layer methods on `OAuthService`

- [x] T030 [W16A] [US3] Add `async def rotate_secret(provider_type, new_secret, actor_id) -> None` method to `apps/control-plane/src/platform/auth/services/oauth_service.py` per plan.md design D6 + Rule 44: (a) validate provider exists; (b) call `await self._secret_provider.put(path=provider.client_secret_ref, values={"value": new_secret})` (UPD-040's `VaultSecretProvider.put` creates a new KV v2 version); (c) call `await self._secret_provider.flush_cache(path=provider.client_secret_ref)` per design D6; (d) emit `auth.oauth.secret_rotated` audit entry via the dual-emission pattern from plan.md research R6 (`repository.create_audit_entry` + `publish_auth_event`); audit `changed_fields=["client_secret"]` (NOT the value); (e) NEVER returns the new secret per Rule 44.
- [x] T031 [W16A] [US2] Add `async def reseed_from_env(provider_type, force_update, actor_id, settings, secret_provider) -> dict[str, Any]` method: re-invokes the bootstrap logic with `force_update`; returns `{changed_fields: [...], audit_event_id: ...}` (NOT secret values). Emits `auth.oauth.config_reseeded` audit entry.
- [x] T032 [P] [W16A] [US4] Add `async def get_history(provider_type, limit, cursor) -> list[dict]` method: delegates to `oauth_repository.get_history()`.
- [x] T033 [P] [W16A] [US4] Add `async def get_rate_limits(provider_type) -> OAuthRateLimitConfig | None` and `async def update_rate_limits(provider_type, config, actor_id) -> None` methods. The update method emits `auth.oauth.rate_limit_updated` audit entry.

### 7 new audit-event payload classes

- [x] T034 [W16A] [US1, US2, US3, US4] Add 7 new Pydantic event payload classes to `apps/control-plane/src/platform/auth/events/oauth_events.py` (verify file path during T034 — likely co-located with the existing `OAuthProviderConfiguredPayload` referenced in research §6): `OAuthProviderBootstrappedPayload(actor_id, provider_type, source, force_update_used)`, `OAuthSecretRotatedPayload(actor_id, provider_type, old_version, new_version)`, `OAuthConfigReseededPayload(actor_id, provider_type, force_update, changed_fields)`, `OAuthRoleMappingUpdatedPayload(actor_id, provider_type, before_count, after_count)`, `OAuthRateLimitUpdatedPayload(actor_id, provider_type, before, after)`, `OAuthConfigImportedPayload(actor_id, provider_type, vault_path)`, `OAuthConfigExportedPayload(actor_id, provider_type, target_env)`. NONE of these payloads include secret values per Rule 31.

### Track A integration tests

- [x] T035 [W16A] [US1, US2, US3, US4] Author `apps/control-plane/tests/auth/test_oauth_admin_endpoints.py` (NEW pytest test file, ~25 cases per plan.md Phase 2 day 3): rotate-secret returns 204 with no body (Rule 44), audit entry emitted (no secret), cache flush triggered, reseed re-reads env vars + returns diff, reseed fails 400 when env vars not set, history returns paginated entries with diffs, rate-limits get returns global default if no per-provider row, rate-limits put upserts + emits audit, all 5 endpoints reject non-superadmin (403) per Rule 30. `pytest -v` passes.
- [x] T036 [W16A] Run `python scripts/check-secret-access.py` against the Track A code (will be extended in T087) to verify zero new direct `os.getenv("*_SECRET")` calls exist outside the `SecretProvider` implementation files. Pre-T087 violations are OK (covered by T087); Track A NEW code is the focus.

**Checkpoint (end of Phase 2)**: `pytest apps/control-plane/tests/auth/` passes (12 + 30 + 25 = 67+ new test cases); the 5 admin endpoints respond correctly to authenticated super-admin requests; `git grep "os.getenv" apps/control-plane/src/platform/auth/services/oauth_bootstrap.py` returns zero results (Rule 39 satisfied).

---

## Phase 3: Track B — Admin UI Extensions

**Story goal**: EXTENDS the existing 382-line `OAuthProviderAdminPanel.tsx` per plan.md research R3 + design (refactor `ProviderConfigCard` with shadcn `Tabs` wrapping the existing form unchanged). 8 new sub-components per FR-643. All strings i18n-keyed for 6 supported locales per UPD-039 / FR-620.

### Tabs structure refactor

- [x] T037 [W16B] [US1, US3, US4] Refactor `apps/web/components/features/auth/OAuthProviderAdminPanel.tsx`'s `ProviderConfigCard` (lines 116-348) per plan.md research R3 + Phase 3 day 2 morning: introduce shadcn `Tabs` component above the existing form. 5 tabs in this order: "Configuration" (existing form unchanged, moved into the tab content), "Status" (NEW — T040), "Role Mappings" (NEW — T044), "History" (NEW — T046), "Rate Limits" (NEW — T048). Tab routing via `?provider_tab=...` query param to preserve URL state across navigation.

### Source badge + status panel

- [x] T038 [W16B] [US1] Create `apps/web/components/features/auth/OAuthProviderSourceBadge.tsx` (NEW ~50 lines) per FR-643: shadcn `Badge` rendering the source value with 3 colors (`env_var` blue, `manual` gray, `imported` purple); tooltip explains each source's meaning. Accessibility label `aria-label="Configuration source: {source}"`.
39. [x] T039 [W16B] Render the source badge in the card header of `OAuthProviderAdminPanel.tsx`'s `ProviderConfigCard` per FR-643. Reads from the `OAuthProviderAdminResponse.source` field (added by Track A T007).
- [x] T040 [W16B] [US4] Create `apps/web/components/features/auth/OAuthProviderStatusPanel.tsx` (NEW ~120 lines) per FR-643. 4-stat shadcn `Card` strip: last successful auth timestamp (formatted via `date-fns`), 24h auth count, 7d auth count, 30d auth count, active linked users count. Uses TanStack Query to fetch `/api/v1/admin/oauth-providers/{provider}/status` (NEW endpoint — verify if Track A T021-T029 covers this; if not, add a 6th admin endpoint OR aggregate from existing audit + oauth_links queries via a service-layer method).
- [x] T041 [W16B] Register `OAuthProviderStatusPanel` in the "Status" tab of `ProviderConfigCard` from T037.

### Rotate-secret + test-connectivity + reseed buttons

- [x] T042 [W16B] [US3] Create `apps/web/components/features/auth/OAuthProviderRotateSecretDialog.tsx` (NEW ~150 lines) per Rule 44 + spec User Story 3. shadcn `Dialog` with: a write-only `PasswordInput` component (NEVER pre-filled with current value — the current secret is NEVER fetched from backend per Rule 44), a confirmation checkbox "I understand the new secret will be written to Vault", a `Button` to submit. On submit, calls `POST /api/v1/admin/oauth-providers/{provider}/rotate-secret` with the new secret in the request body; expects 204 No Content; closes dialog with Toast "Secret rotated successfully" — the new secret is NEVER displayed back to the user. Render the rotate-secret button in the card header.
- [x] T043 [W16B] [US3] Create `apps/web/components/features/auth/OAuthProviderTestConnectivityButton.tsx` (NEW ~100 lines) per spec correction §2 + plan.md research R11. Button renders inline in the card header. On click, calls the existing backend endpoint at `router_oauth.py:220-248` (`POST /api/v1/admin/oauth-providers/{provider}/test-connectivity`); renders the `OAuthConnectivityTestResponse` shape (reachable, auth_url_returned, diagnostic) per research R11: green checkmark icon when `reachable=true AND auth_url_returned=true`; yellow warning icon when `reachable=true AND auth_url_returned=false`; red X icon when `reachable=false`; `diagnostic` string in a tooltip + Toast notification. Loading spinner during the request.
- [x] T044 [W16B] [US2] Create `apps/web/components/features/auth/OAuthProviderReseedDialog.tsx` (NEW ~120 lines) per FR-643. shadcn `Dialog` with: a confirmation copy "This may overwrite manual changes. Continue?" + a checkbox to acknowledge override risk; a `force_update` toggle (default false). On confirm, calls `POST /api/v1/admin/oauth-providers/{provider}/reseed-from-env`; renders the diff response (changed_fields list); Toast notification on success.

### Role mappings managed table

- [x] T045 [W16B] [US4] Create `apps/web/components/features/auth/OAuthProviderRoleMappingsTable.tsx` (NEW ~250 lines) per spec User Story 4. Managed table with shadcn `Table` + per-row edit/delete `Button`s + add-row inline `Form`. Validation: group format regex (Google: email format `[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}`; GitHub: `[a-z0-9-]+/[a-z0-9-]+`); role select dropdown populated from a `/api/v1/admin/roles` endpoint (verify this exists during T045; if missing, hardcode the canonical 6 roles from the constitution: `user`, `admin`, `super_admin`, `security_officer`, `member`, `viewer`).
- [x] T046 [W16B] [US4] Wire the role-mappings table to the existing PUT endpoint at `/api/v1/admin/oauth/providers/{provider}` (research §6 verified `upsert_oauth_provider`); the table reads + writes the existing `OAuthProvider.group_role_mapping` JSONB column. On save, emits `auth.oauth.role_mapping_updated` audit entry server-side per Track A T034.
- [x] T047 [W16B] Register `OAuthProviderRoleMappingsTable` in the "Role Mappings" tab of `ProviderConfigCard` from T037.

### History tab

- [x] T048 [W16B] [US4] Create `apps/web/components/features/auth/OAuthProviderHistoryTab.tsx` (NEW ~200 lines) per FR-644. Paginated shadcn `Table` with columns: timestamp (formatted), admin principal (resolved from user_id via existing `/api/v1/users/{id}` endpoint), change summary (action name). Expandable rows render before/after diff using a JSON-diff visualization. Uses TanStack Query's `useInfiniteQuery` with the cursor-based pagination from the `OAuthHistoryListResponse.next_cursor` field.
- [x] T049 [W16B] Register `OAuthProviderHistoryTab` in the "History" tab of `ProviderConfigCard` from T037.

### Rate limits tab

- [x] T050 [W16B] [US4] Create `apps/web/components/features/auth/OAuthProviderRateLimitsTab.tsx` (NEW ~150 lines) per FR-646 + spec correction §12. shadcn `Form` with 6 `NumberInput` fields (per_ip_max, per_ip_window, per_user_max, per_user_window, global_max, global_window) + `Button` to save. Reads via `GET /api/v1/admin/oauth-providers/{provider}/rate-limits`; writes via `PUT`. Tooltip explanations for each field.
- [x] T051 [W16B] Register `OAuthProviderRateLimitsTab` in the "Rate Limits" tab of `ProviderConfigCard` from T037.

### Frontend API + schema integration

- [x] T052 [W16B] Modify `apps/web/lib/api/oauth-admin.ts` (or wherever the existing OAuth admin fetch wrappers live — verify file path during T052; likely `apps/web/lib/api/oauth.ts`): add 5 new fetch wrappers for the new admin endpoints (`rotateSecret`, `reseedFromEnv`, `getHistory`, `getRateLimits`, `putRateLimits`). Each wrapper uses the existing TanStack Query mutation/query factories.
- [x] T053 [W16B] Modify `apps/web/lib/schemas/oauth.ts` (or equivalent — verify during T053): add 5 new Zod schemas mirroring backend Pydantic schemas from Track A T021-T024. Re-export for use in the new UI components.

### i18n integration

- [x] T054 [W16B] [US1, US3, US4] Modify `apps/web/messages/en.json`: add ~30 new i18n keys under `admin.oauth.*` namespace covering all new sub-components (badges, tabs, button labels, dialog copy, error messages, tooltip explanations). Reference these in all new TSX components via `useTranslations("admin.oauth")` from `next-intl`.
- [x] T055 [P] [W16B] Modify `apps/web/messages/{de,es,fr,it,zh-CN,ja}.json`: copy English keys with TODO-translation markers per UPD-038's parity check; vendor translates per UPD-039 / FR-620. The 7-day grace window from UPD-038's `scripts/check-readme-parity.py` extension applies.
- [x] T056 [P] [W16B] Run `pnpm test:i18n-parity` (or the UPD-038 / UPD-088 parity check command) to verify all 6 locale catalogs have all new keys; flag missing keys.

### Playwright E2E + accessibility

- [x] T057 [W16B] [US1, US3, US4] Create `apps/web/tests/e2e/admin-oauth-bootstrap.spec.ts` (NEW Playwright test file): ~12 scenarios covering: (a) source badge renders correctly for env_var / manual / imported; (b) test-connectivity button calls backend + renders diagnostic; (c) rotate-secret dialog accepts new secret + closes on 204; (d) reseed dialog warns about manual-change-overwrite + applies; (e) role-mappings table validates group format + role existence; (f) history tab renders paginated entries; (g) rate-limits tab saves correctly; (h) tab routing via `?provider_tab=...` URL param preserves on refresh.
- [x] T058 [P] [W16B] Run axe-core scan on the extended panel locally (`pnpm dev` + browser scan); verify zero AA violations per UPD-083 / FR-488 inheritance. Fix any violations introduced by the new sub-components (likely candidates: badge contrast, dialog focus management, table keyboard navigation).
- [x] T059 [W16B] Run `pnpm test` + `pnpm typecheck` + `pnpm lint` to verify the panel extensions pass all CI gates.

### Backward-compat verification

- [x] T060 [W16B] [US1] Verify SC-020 — no regression in the existing UPD-036 admin OAuth tab: re-run UPD-036's existing test suite (the original `apps/web/tests/...` files for `OAuthProviderAdminPanel`); all passing tests must continue passing. The Configuration tab (the existing form unchanged) must look + behave identically per design D5.
- [x] T061 [P] [W16B] Verify the existing 4 OAuth admin endpoints (`GET /providers`, `PUT /providers/{provider}`, `POST /test-connectivity`, `GET /audit`) still respond correctly post-Track-A schema additions; no breaking changes to the request/response shapes.

### `OAuthProviderButtons.tsx` regression check (login + signup)

- [x] T062 [W16B] [US1] Verify SC-004 — the existing `OAuthProviderButtons.tsx` component (verified per spec.md scope discipline as feature 087's deliverable) renders OAuth buttons for the bootstrapped providers within 1 second of page load. The component reads from a public-facing `/api/v1/oauth/providers` endpoint (verified at `router_oauth.py` — `GET /api/v1/oauth/providers` returns the public `OAuthProviderPublicListResponse` from research §4). UPD-041 makes NO UI changes here — the bootstrap-driven `enabled=true` state of the provider rows is sufficient.
- [ ] T063 [P] [W16B] Run an end-to-end manual smoke test: with the bootstrap module having run (Track A landed) AND `PLATFORM_OAUTH_GOOGLE_ENABLED=true` set on a kind cluster pod, navigate to `/login` AND `/signup` in a browser; verify both buttons appear; click "Sign in with Google" + complete the OAuth round-trip; verify the user is provisioned with the `defaultRole`.

### Status panel endpoint consolidation (deferred decision from T040)

- [x] T064 [W16B] [US4] Decision point: T040 may need a NEW dedicated `GET /api/v1/admin/oauth-providers/{provider}/status` endpoint OR the status panel can compose from existing data (`OAuthProvider.last_successful_auth_at` from T007, audit-entry counts via existing `GET /api/v1/admin/oauth/audit`, `OAuthLink` count via a new repository method per plan.md research R12). **Resolution**: add a NEW 6th admin endpoint `GET /status` that aggregates all 4 stats in a single response — avoids 4 separate frontend requests + cleaner caching. Endpoint added in this task as a Track B-driven Track A backend addition.
- [x] T065 [W16B] [US4] Update `OAuthProviderStatusPanel.tsx` (T040) to call the new `GET /status` endpoint instead of 4 separate queries.

**Checkpoint (end of Phase 3)**: visiting `/admin/settings?tab=oauth` shows the extended panel with 5 tabs per provider; each tab renders correctly against the live backend; `pnpm test`, `pnpm typecheck`, axe-core scan, i18n parity check all pass; the existing UPD-036 test suite passes unchanged.

---

## Phase 4: Track C — Migration CLI + E2E + Journey Tests

**Story goal**: NEW `platform-cli admin oauth export|import` per FR-645; 8 E2E test files covering bootstrap / idempotency / FORCE_UPDATE / rotation / reseed / validation; J01 extension; J19 creation.

### `platform-cli admin oauth` Typer sub-app

- [x] T066 [W16C] [US5] Create `apps/ops-cli/src/platform_cli/commands/admin/oauth.py` (NEW Typer sub-app per FR-645 + plan.md design D8): `oauth_app = typer.Typer(help="Export and import OAuth provider configurations.", no_args_is_help=True)`. 2 subcommands: `export(env: str, output: Path)`, `import_(input: Path, dry_run: bool = True, apply: bool = False)`.
- [x] T067 [W16C] [US5] Implement `export` subcommand: reads providers from the database via the admin REST API (`GET /api/v1/admin/oauth/providers`); for each provider, builds a YAML entry with provider_type + display_name + enabled + client_id + redirect_uri + scopes + domain_restrictions/org_restrictions + group_role_mapping + default_role + require_mfa + source + `client_secret_vault_path` (NOT the secret value per Rule 43). Output written to `--output` path.
- [x] T068 [W16C] [US5] Implement `import` subcommand: reads YAML file; for each provider, calls `await secret_provider.list_versions(client_secret_vault_path)` to verify the path exists in the target Vault (per Rule 43 — fails fast if missing); produces a diff preview against the current state via the admin REST API; on `--apply`, upserts each provider via the existing `PUT /api/v1/admin/oauth/providers/{provider}` endpoint with `source="imported"` (NEW source value); emits `auth.oauth.config_imported` audit entry per Track A T034.
- [x] T069 [W16C] Modify `apps/ops-cli/src/platform_cli/commands/admin/__init__.py` (or `commands/admin.py` per plan.md "Source Code"): register the new `oauth_app` via `app.add_typer(oauth_app, name="oauth")` per the existing `platform-cli admin` Typer app's `add_typer` pattern.
- [x] T070 [W16C] Author `apps/ops-cli/tests/commands/admin/test_oauth.py` (NEW pytest test file): ~15 cases — export produces valid YAML, export omits secret values, export is idempotent (2 consecutive exports identical hash), export includes the `source` field, import dry-run validates Vault paths, import fails on missing path with clear error, import applies + emits audit, round-trip (export from staging + import to production with mock Vault), --apply without --dry-run-first refused with error.

### E2E test suite

- [x] T071 [W16C] [US1, US2, US3, US4, US5] Create `tests/e2e/suites/oauth_bootstrap/__init__.py` + `conftest.py` (NEW pytest fixtures): `kind_cluster_with_oauth_env_vars` (kind cluster with `PLATFORM_OAUTH_GOOGLE_*` set), `populated_vault` (Vault with synthetic OAuth secrets at canonical paths), `mock_oauth_provider_endpoints` (httpbin-style mock Google + GitHub OAuth servers for synthetic flows), `clean_oauth_state` (resets between tests).
- [x] T072 [P] [W16C] [US1] Create `tests/e2e/suites/oauth_bootstrap/test_env_bootstrap_google.py`: 3 test functions covering full Google bootstrap end-to-end on a kind cluster — `enabled=true` triggers bootstrap, provider row created with `source=env_var`, Vault path populated, login button visible.
- [x] T073 [P] [W16C] [US1] Create `tests/e2e/suites/oauth_bootstrap/test_env_bootstrap_github.py`: 3 test functions — same shape as Google, with team_role_mappings instead of group_role_mappings.
- [x] T074 [P] [W16C] [US2] Create `tests/e2e/suites/oauth_bootstrap/test_bootstrap_idempotency.py` per Rule 42 + FR-640: 4 test functions — re-run with unchanged values is no-op (no audit emission), manual edit + helm upgrade unchanged → manual edit preserved, FORCE_UPDATE=true overwrites with critical audit, FORCE_UPDATE on empty DB is identical to fresh bootstrap (audit entry is `provider_bootstrapped` not `config_reseeded`).
- [x] T075 [P] [W16C] [US3] Create `tests/e2e/suites/oauth_bootstrap/test_rotation.py` per Rule 44 + plan.md design D6: 4 test functions — rotation writes new Vault KV v2 version, cache flushed, response is 204 with no body, audit entry has no plaintext secret, in-flight OAuth flow continues with cached v1 then transitions to v2.
- [x] T076 [P] [W16C] [US2] Create `tests/e2e/suites/oauth_bootstrap/test_reseed.py`: 3 test functions — reseed re-reads env vars + applies, reseed without env vars set returns 400, reseed with `force_update=true` overrides manual changes.
- [x] T077 [P] [W16C] [US1] Create `tests/e2e/suites/oauth_bootstrap/test_validation_failures.py` per FR-641 + spec edge cases: 8 test functions — missing CLIENT_ID with ENABLED=true, both CLIENT_SECRET and CLIENT_SECRET_FILE set, invalid JSON in role mappings, unknown role, non-HTTPS redirect URI in production, Vault unreachable at bootstrap, ALLOWED_DOMAINS empty (warning only, not failure), Google provider with `source=ibor` (skip with warning).
- [x] T078 [P] [W16C] [US4] Create `tests/e2e/suites/oauth_bootstrap/test_role_mappings.py`: 4 test functions — add mapping via admin UI, group format validation rejects malformed entries, unknown role rejected, future first-time-OAuth user provisioned with mapped role, existing user role unchanged on mapping change.

### Journey tests

- [x] T079 [W16C] [US1] Modify `tests/e2e/journeys/test_j01_admin_bootstrap.py` (verified 318 lines per plan.md research R9): add 3 new `journey_step()` blocks BEFORE the existing step 4 ("Admin views OAuth provider inventory"). New steps: (1) "Verify env-var-bootstrapped Google + GitHub providers exist on first admin login" (queries `GET /api/v1/admin/oauth/providers` — expects 2 providers with `source=env_var`); (2) "Verify source badge reads `env_var`" (loads admin tab via Playwright + asserts badge text); (3) "Verify Vault paths populated" (queries Vault via `vault kv get` from a sidecar). Total addition: ~50 lines.
- [x] T080 [W16C] [US1, US4] Create `tests/e2e/journeys/test_j19_new_user_signup.py` (NEW per spec correction §9 + plan.md design D9). Modeled on `test_j01_admin_bootstrap.py`'s 318-line structure (sequential `journey_step()` blocks per research R9). 20 sequential journey steps covering: kind cluster pre-configured with `PLATFORM_OAUTH_GOOGLE_ENABLED=true`, Google OAuth provider mock set up with a test workspace group → admin role mapping, new user `alice@company.com` (member of mapped group) navigates to `/signup`, clicks "Sign in with Google", completes OAuth round-trip, lands on dashboard with `role=admin`, performs a first action, audit chain has `auth.oauth.user_provisioned` entry. Total: ~250 lines.

### Matrix CI integration

- [x] T081 [W16C] [US1, US2, US3, US4] Modify `.github/workflows/ci.yml` per plan.md Phase 4 day 6 afternoon: add `tests/e2e/suites/oauth_bootstrap/` to UPD-040's existing matrix-CI job's test path; the suite runs in all 3 modes (`mock`, `kubernetes`, `vault`). Mock mode tests assert that bootstrap is SKIPPED when Vault is unreachable (mock mode has no Vault — bootstrap fails fast per Rule 43; this is the EXPECTED behaviour in mock mode). Kubernetes mode tests assert bootstrap writes to K8s Secrets via UPD-040's `KubernetesSecretProvider`. Vault mode tests assert bootstrap writes to real Vault.
- [ ] T082 [W16C] [US1] Verify SC-015: J01 (extended) + J19 (created) journey tests pass on the matrix CI for all 3 modes. If any mode fails, debug + fix.

### Track C tests

- [x] T083 [W16C] Run `pytest apps/ops-cli/tests/commands/admin/test_oauth.py -v` → 15+ test cases pass.
- [ ] T084 [W16C] Run `pytest tests/e2e/suites/oauth_bootstrap/ -v` against a kind cluster with UPD-040's `vault.mode=dev` + bootstrap env vars → 8 test files pass.
- [ ] T085 [W16C] Run J01 + J19 against a real kind cluster with full bootstrap flow → both pass.

**Checkpoint (end of Phase 4)**: 8 E2E test files + J01 extension + J19 creation all pass; matrix CI green for all 3 secret modes; Track C is shippable.

---

## Phase 5: Helm Chart + Secret-Leak CI Extension

**Story goal**: New `oauth.{google,github}.*` Helm values block per FR-642; control-plane Deployment env-var injection; UPD-040's secret-leak CI extended for OAuth patterns; UPD-039's auto-doc env-var reference includes new vars.

### Helm chart additions

- [x] T086 [W16D] [US1] Modify `deploy/helm/platform/values.yaml` per FR-642 + plan.md research R8 + planning-input's example: add new top-level `oauth:` block with `google:` and `github:` sub-blocks. Each value annotated with `# --` comment per UPD-039 / FR-611 helm-docs auto-generation. Sub-fields: `enabled`, `clientId`, `clientSecretRef.name` + `.key`, `clientSecretVaultPath`, `redirectUri`, `allowedDomains` (Google) / `allowedOrgs` (GitHub), `groupRoleMappings` (Google) / `teamRoleMappings` (GitHub), `requireMfa`, `defaultRole`, `forceUpdate`.
- [x] T087 [W16D] [US1] Modify `deploy/helm/platform/templates/deployment-control-plane.yaml`: inject `PLATFORM_OAUTH_GOOGLE_*` and `PLATFORM_OAUTH_GITHUB_*` env vars from the `oauth.{google,github}.*` values block. If `oauth.google.clientSecretRef.name` is set, add a volumeMount for the K8s Secret as a file at `/etc/secrets/google-client-secret`; the bootstrap reads via `_FILE` path per User Story 1's planning-input precedence list. Same for GitHub.

### Secret-leak CI extension

- [x] T088 [W16D] [US1] Modify `scripts/check-secret-access.py` (UPD-040's deny-list per FR-687, extended in this task per FR-647): add 2 new patterns to the deny-list — `PLATFORM_OAUTH_*_CLIENT_SECRET` (allowed only inside `auth/services/oauth_bootstrap.py` and `auth/services/oauth_service.py`); `OAUTH_SECRET_*` (the legacy fallback — REMOVED in this feature per spec correction §7; if found in any code, fails the build). Add 4 test cases in `scripts/tests/test_check_secret_access.py` covering the new patterns.
- [x] T089 [W16D] Run `python scripts/check-secret-access.py` against the full repo post-Track-A; verify zero violations from new code; verify the legacy `OAUTH_SECRET_*` fallback at `oauth_service.py:741-746` (verified pre-UPD-040) is GONE per spec correction §7 (UPD-040 task T011 already removed it).

### UPD-039 auto-doc verification

- [x] T090 [W16D] [US1] If UPD-039 has landed, run `python scripts/generate-env-docs.py` to regenerate `docs/configuration/environment-variables.md`. Verify all `PLATFORM_OAUTH_GOOGLE_*` and `PLATFORM_OAUTH_GITHUB_*` env vars appear with the correct security classification: `*_CLIENT_SECRET` and `*_CLIENT_SECRET_FILE` are `sensitive`; the rest are `configuration`. CI fails any drift per FR-647.
- [x] T091 [W16D] If UPD-039 has landed, run `helm-docs --chart-search-root=deploy/helm/platform/` to regenerate the Helm values reference. Verify the new `oauth.*` block appears in `docs/configuration/helm-values.md` with all `# --` annotations parsed correctly.

**Checkpoint (end of Phase 5)**: `helm install platform deploy/helm/platform/ --set oauth.google.enabled=true --set oauth.google.clientId=... --set oauth.google.clientSecretRef.name=...` brings up the platform with the bootstrap running on first pod-start; the auto-doc env-var reference includes the new vars; the secret-leak CI passes.

---

## Phase 6: SC Verification + Documentation Polish

**Story goal**: All 20 spec SCs pass; UPD-039 docs integration; release notes; final review.

### SC sweep

- [ ] T092 [W16E] Run the full SC verification sweep per plan.md design Phase 6 day 7: SC-001 through SC-020. For each SC, document the actual measurement (e.g., SC-001's "5 seconds from pod startup" — measured wall-clock time on a synthetic kind cluster). Capture the verification record at `specs/091-oauth-env-bootstrap/contracts/sc-verification.md` (NEW file).
- [ ] T093 [P] [W16E] Run the canonical secret-leak regex set against `kubectl logs platform-control-plane-...` for 24 hours of synthetic load (bootstrap + rotation + reseed flows) per SC-014; verify zero matches per Rule 31 + Rule 44.

### Operator runbooks (UPD-039 integration)

- [x] T094 [W16E] [US1] Create `docs/operator-guide/runbooks/oauth-bootstrap.md` (NEW per plan.md design D10; deliverable here if UPD-039 has landed; otherwise UPD-039 owns and merges later). Sections: Symptom (operator wants GitOps OAuth bootstrap), Diagnosis (verify env vars set), Remediation (step-by-step Helm values flow), Verification (admin tab shows source=env_var badge), Rollback (mode-flag flip). Includes the canonical 4-path precedence list from spec User Story 1 setup.
- [x] T095 [P] [W16E] [US3] Create `docs/operator-guide/runbooks/oauth-secret-rotation.md`: rotation flow via the admin UI rotate-secret action OR the `platform-cli vault rotate-token` CLI fallback; references UPD-040's KV v2 versioning + dual-credential window.
- [x] T096 [P] [W16E] [US5] Create `docs/operator-guide/runbooks/oauth-config-promotion.md`: GitOps promotion (dev → staging → production) via `platform-cli admin oauth export|import`; Vault path validation step.

### Admin guide updates

- [x] T097 [P] [W16E] [US3, US4] Modify `docs/admin-guide/oauth-providers.md` (or wherever the existing UPD-039 admin-guide OAuth page lives — verify during T097): add sections for rotation flow, reseed action, role-mappings table, history tab, rate-limits tab. Reuse the existing screenshots from UPD-036 + add new ones for the 5 new sub-components. Reference Rule 44 + Rule 42.

### Developer guide pages

- [x] T098 [P] [W16E] Create `docs/developer-guide/oauth-bootstrap-internals.md` (deliverable here if UPD-039 has landed): how the bootstrap module integrates with `SecretProvider`, the dual audit-emission pattern, the 7 new event types, the 4 secret-mounting paths, the migration sequence (069), the canonical Vault path scheme.

### Release notes

- [x] T099 [W16E] Modify `docs/release-notes/v1.3.0/oauth-bootstrap.md` (or extend the existing v1.3.0 release notes file): document the new `PLATFORM_OAUTH_*` env vars, the deprecated legacy `OAUTH_SECRET_*` fallback REMOVAL (breaking change for any deployment that relied on it), the migration tool, the 4 new database columns, the 5 new admin endpoints, the 8 new UI sub-components.

### Final review pass

- [ ] T100 [W16E] Verify all 20 spec SCs pass (re-run sweep from T092); verify J01 + J19 + 8 E2E suites + 12 Playwright scenarios all pass on the matrix CI; verify zero secret-leak hits in 24-hour log capture; verify UPD-036's existing test suite passes unchanged (SC-020).
- [ ] T101 [W16E] Run `pytest apps/control-plane/tests/auth/`, `pytest apps/ops-cli/tests/commands/admin/`, `pytest tests/e2e/suites/oauth_bootstrap/`, `pytest tests/e2e/journeys/test_j01_admin_bootstrap.py`, `pytest tests/e2e/journeys/test_j19_new_user_signup.py`, `pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm test:i18n-parity` one final time → all pass.
- [x] T102 [W16E] Run `python scripts/check-secret-access.py` and `python scripts/check-admin-role-gates.py` (UPD-040's gate from T090) → both pass with zero violations.
- [ ] T103 [W16E] Run `helm template deploy/helm/platform/ --set oauth.google.enabled=true --set oauth.google.clientId=test...` → renders without errors; verify the rendered Deployment has the expected env-var injection + volume mounts.
- [x] T104 [W16E] If UPD-039 has landed, run `python scripts/check-doc-references.py` → no broken FR references; run `helm-docs --check` → no drift; run `python scripts/generate-env-docs.py --check` → no drift in env-var reference.
- [ ] T105 [W16E] Address PR review feedback; merge. Verify the `091-oauth-env-bootstrap` branch passes all required CI gates (matrix-CI for 3 secret modes, secret-access check, role-gates check, axe-core AA scan, i18n parity, doc-references staleness if UPD-039 landed); merge to `main`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **W16.0 Setup (T001-T004)**: No blockers; T001 verifies UPD-040 is on `main` (HARD DEPENDENCY — without UPD-040, UPD-041 is blocked).
- **W16A Track A Backend (T005-T036)**: Depends on W16.0 + UPD-040 shipped.
- **W16B Track B UI (T037-T065)**: Depends on Track A T021-T024 (Pydantic schemas) — frontend Zod schemas mirror backend; T037-T056 can begin once schemas land; T057-T065 depend on full Track A + T037-T056.
- **W16C Track C CLI + E2E + journeys (T066-T085)**: Depends on Track A (admin endpoints functional) + Track B (UI button references for Playwright tests).
- **W16D Helm + secret-leak CI (T086-T091)**: Depends on Track A + Track B (env-var convention finalized).
- **W16E SC verification + docs (T092-T105)**: Depends on ALL OTHER PHASES — convergent.

### User Story Dependencies

- **US1 (P1 — GitOps bootstrap)**: T005-T020 (Track A bootstrap) + T037-T065 (Track B source badge + login/signup buttons) + T072-T073 (E2E) + T079 (J01 ext) + T086-T087 (Helm).
- **US2 (P1 — idempotency + FORCE_UPDATE)**: T016 (idempotency logic) + T026, T031 (reseed endpoint + service) + T044 (reseed dialog) + T074 (E2E).
- **US3 (P1 — rotate secret)**: T025, T030 (rotate endpoint + service) + T042 (rotate dialog) + T075 (E2E).
- **US4 (P2 — role mappings + history + rate limits)**: T027-T029, T032-T033 (history + rate-limits endpoints + service) + T045-T051 (role-mappings table + history tab + rate-limits tab) + T078 (E2E).
- **US5 (P2 — export/import)**: T066-T070 (Track C CLI sub-app).

### Within Each Track

- Within Track A: T005-T006 (migration) → T007-T009 (model + repository) → T010-T013 (config block) → T014-T019 (bootstrap module + tests) → T020 (wire into main.py) → T021-T024 (schemas, parallel) → T025-T029 (5 endpoints, parallel after schemas) → T030-T033 (service methods, parallel) → T034 (event payloads) → T035-T036 (integration tests + secret-access check).
- Within Track B: T037 (Tabs refactor) → T038-T044 (per-card-header sub-components, parallel) → T045-T051 (per-tab sub-components, parallel) → T052-T053 (API + Zod schemas) → T054-T056 (i18n) → T057-T058 (Playwright + axe) → T059-T063 (regression checks) → T064-T065 (status endpoint consolidation).
- Within Track C: T066-T069 (CLI sub-app) → T070 (CLI tests) → T071 (E2E conftest) → T072-T078 (8 E2E files, parallel) → T079-T080 (journey tests) → T081-T082 (matrix CI) → T083-T085 (full test runs).
- Within Track D: T086-T087 (Helm) → T088-T089 (CI extension) → T090-T091 (auto-doc verification).
- Within Track E: T092-T093 (SC sweep) → T094-T098 (runbooks + admin/dev guides, parallel) → T099 (release notes) → T100-T105 (final review pass).

### Parallel Opportunities

- **Day 1**: T001-T004 (Setup, all parallel) + T005-T006 (Track A migration) + T037-T038 (Track B Tabs refactor + source badge — can use placeholder schemas).
- **Day 2-3**: Track A T007-T024 mostly sequential; Track B T039-T044 highly parallel (4 dialogs + buttons across multiple devs); Track C T066-T070 (CLI sub-app) parallel.
- **Day 4-5**: Track A T025-T036 (endpoints + service methods + tests) + Track B T045-T065 (tabs + i18n + Playwright) + Track C T071-T080 (E2E + journeys).
- **Day 5-6**: Track D Helm + CI in parallel with E2E test runs; Phase 6 SC sweep starts.
- **Day 7-9**: Phase 6 polish (mostly parallel — many runbook/admin-guide/dev-guide pages can be authored simultaneously).

---

## Implementation Strategy

### MVP First (User Story 1 Only — GitOps Bootstrap)

1. Complete Phase 1 (W16.0) Setup.
2. Complete Phase 2 (W16A) Track A — migration + model + bootstrap module + main.py wire.
3. Complete Phase 5 partial (T086-T087) — Helm values + Deployment.
4. Run T072-T073 (E2E for US1).
5. **STOP and VALIDATE**: a fresh kind cluster with `vault.mode=dev` + `PLATFORM_OAUTH_GOOGLE_ENABLED=true` reaches working state with the Google OAuth provider bootstrapped + login button visible per SC-001 + SC-004.

### Incremental Delivery

1. MVP (US1) → demo GitOps bootstrap on a kind cluster.
2. + US2 (T016, T026, T031, T044, T074) → demo idempotency + FORCE_UPDATE override.
3. + US3 (T025, T030, T042, T075) → demo secret rotation per Rule 44.
4. + US4 (T027-T029, T032-T033, T045-T051, T078) → demo role-mappings + history + rate-limits.
5. + US5 (T066-T070) → demo export/import.
6. Full feature complete after Phase 6 polish.

### Parallel Team Strategy

With 3 devs:

- **Dev A (Track A backend keystone)**: Days 1-3 Track A entire scope; Days 4-5 Track A test fixes + Track D secret-leak CI extension; Days 6-9 Phase 6 SC verification + runbooks.
- **Dev B (Track B UI extensions)**: Day 1 Track B Tabs refactor + source badge (using placeholder schemas); Days 2-4 Track B sub-components + i18n; Days 5-6 Track B Playwright + regression checks; Days 7-9 Phase 6 admin-guide updates.
- **Dev C (Track C CLI + E2E)**: Days 1-3 Track C CLI sub-app + tests; Days 4-5 Track C E2E suite + matrix CI; Days 6-7 Track C journey tests; Days 8-9 Phase 6 polish.

Wall-clock: **5-6 days for MVP** (US1 only); **8-10 days for full feature** with 3 devs in parallel.

---

## Notes

- [P] tasks = different files, no dependencies; safe to parallelize across devs.
- [Story] label maps task to specific user story for traceability (US1-US5).
- [W16X] label maps task to wave-16 sub-track (W16.0 / W16A-E).
- The plan's effort estimate (8-10 dev-days) supersedes the brownfield's 4.5-day understatement; tasks below total ~105 entries, consistent with that estimate.
- Track A is the keystone backend; rushing it risks rework in Track B/C. Plan ≥ 3 dev-days.
- Rule 44 (rotation responses never return the new secret) is enforced at TWO layers: T025 (endpoint returns 204 No Content) + T042 (UI dialog never displays current secret); both must hold.
- Rule 42 (idempotency) is verified by T074 (E2E test for re-run + FORCE_UPDATE override + critical audit emission).
- Rule 43 (OAuth secrets in Vault, never in DB) is enforced by T014 (bootstrap fails fast if Vault unreachable) + T088 (CI deny-list rejects any new code path that writes secrets to a non-Vault location) + T077 (E2E test for Vault unreachability + bootstrap failure).
- The legacy `OAUTH_SECRET_*` env-var fallback at `oauth_service.py:741-746` is REMOVED per spec correction §7 — already handled by UPD-040 task T011 (verified during T001 setup).
- The 5 secret-mounting paths from planning-input (direct env, _FILE, clientSecretRef, clientSecretVaultPath, fail-fast) are all implemented in T015's secret-resolution helper.
- Per-BC ServiceAccount separation for OAuth (each BC's pods having distinct Vault auth roles) is OUT OF SCOPE per UPD-040 design D9; planned as a follow-up feature.
- The `J19 New User Signup` journey test created in T080 may be promoted to a shared journey-suite asset for future signup-touching features per design D9.
- If UPD-039 (Documentation Site) has not landed when UPD-041 begins polish phase, runbook + admin-guide + dev-guide pages live in `specs/091-oauth-env-bootstrap/contracts/` and merge into UPD-039 later per design D10.
