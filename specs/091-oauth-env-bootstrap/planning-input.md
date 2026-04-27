# UPD-041 — OAuth Provider Environment-Variable Bootstrap and Extended Super Admin UI

## Brownfield Context

**Current state (verified in repo):**
- **OAuth backend is complete and working** (`auth/services/oauth_providers/github.py`, `google.py`, `oauth_service.py`, `router_oauth.py`): authorize, callback, state validation, PKCE for Google, account linking, auto-provisioning.
- **OAuth UI is partially complete** (after UPD-037): login + signup pages use `OAuthProviderButtons`, `/settings/account/connections` for link management, dedicated `/auth/oauth/{provider}/callback` page.
- **No dedicated env vars for OAuth providers exist**. The current `_resolve_secret` fallback uses `OAUTH_SECRET_{ref}` derived from the `client_secret_ref` stored in the database — operators must first create the provider via API, note its ref, and then set the env var. There is no `PLATFORM_OAUTH_GOOGLE_CLIENT_ID` convention.
- **Admin OAuth page** exists in UPD-036 (`/admin/oauth-providers`) with basic CRUD. UPD-037 adds it test-connectivity. But the page does NOT expose: group/team-to-role mappings as a managed table, history tab, source badge (env-var vs manual vs imported), rate limit controls, secret rotation button, or reseed-from-environment action.
- **No GitOps-friendly install path for OAuth**. An operator who wants Google+GitHub auto-configured at install time must write post-install scripts or manual admin actions.

**Extends:**
- FR-448–452 (OAuth2 framework + Google + GitHub).
- UPD-020 (OAuth integration — existing backend).
- UPD-036 (Administrator Workbench — `/admin/oauth-providers` page).
- UPD-037 (Signup and OAuth UI completion — `/signup` OAuth buttons, callback page).
- UPD-040 (Vault integration — client secrets stored in Vault at canonical paths).

**FRs:** FR-639 through FR-648 (section 114 of the FR document).

---

## Summary

UPD-041 closes the last OAuth gap: making Google and GitHub OAuth configurable entirely via environment variables at install time, with no manual admin action required. This enables GitOps deployments, infrastructure-as-code, and reproducible environment promotion (dev → staging → production).

The feature also extends the `/admin/oauth-providers` super admin page to cover the full configuration surface: group/team role mappings, provider history, source badge, secret rotation, rate limit controls, reseed-from-environment action, test connectivity, configuration export/import alignment.

---

## User Scenarios

### User Story 1 — GitOps deployment with pre-configured OAuth (Priority: P1)

An operator deploys Musematic to staging via ArgoCD. Google and GitHub OAuth must be configured and working from the first login, without any manual post-install steps.

**Independent Test:** Install the platform with `PLATFORM_OAUTH_GOOGLE_*` and `PLATFORM_OAUTH_GITHUB_*` env vars pre-populated. Verify providers exist in the registry at first startup, secrets are in Vault, login page shows OAuth buttons, a test OAuth flow succeeds.

**Acceptance:**
1. Install completes with OAuth env vars set; no interactive prompts.
2. Both Google and GitHub providers exist in the database with `source=env_var`.
3. Client secrets are stored in Vault at `secret/data/musematic/staging/oauth/google/client-secret` and `secret/data/musematic/staging/oauth/github/client-secret`.
4. Login page (`/login`) and signup page (`/signup`) show both OAuth buttons.
5. OAuth flow for Google completes end-to-end without any manual configuration.
6. OAuth flow for GitHub completes end-to-end.
7. Admin workbench `/admin/oauth-providers` lists both providers with source badge `env_var`.
8. Audit chain entry records OAuth bootstrap with provider type, enabled status, non-secret metadata only.

### User Story 2 — Idempotent reinstall preserves manual adjustments (Priority: P1)

After initial bootstrap, a super admin adjusts the Google allowed-domains list via the admin UI. The operator later re-applies the Helm chart without changing env vars.

**Independent Test:** Bootstrap Google via env vars, then manually add a domain via admin UI, then re-run `helm upgrade` with unchanged values. Verify the manual domain adjustment is preserved (not overwritten).

**Acceptance:**
1. Initial install sets Google provider with `ALLOWED_DOMAINS=company.com`.
2. Super admin adds `subsidiary.com` via the admin UI; audit entry records change with source `manual`.
3. Re-running `helm upgrade` does not overwrite the domain list because `PLATFORM_OAUTH_GOOGLE_FORCE_UPDATE` is false by default.
4. Admin page shows both domains; source badge reflects the latest change (`manual`).
5. If the operator runs with `PLATFORM_OAUTH_GOOGLE_FORCE_UPDATE=true`, the env-var value replaces the UI-adjusted value with a critical audit chain entry noting the overwrite.

### User Story 3 — Super admin rotates client secret (Priority: P1)

The security team rotates the Google OAuth client secret in the Google Cloud Console. A super admin updates the platform with the new secret.

**Independent Test:** Trigger rotation from the admin page. Verify new secret written as a new Vault version. Verify ongoing OAuth flows continue to use the new secret within the cache TTL. Verify old version is retained for the dual-credential window.

**Acceptance:**
1. Admin page shows a "Rotate client secret" action for each provider.
2. Clicking opens a form accepting the new secret (write-only; the current secret is never displayed).
3. Action writes a new version at the Vault KV v2 path.
4. Cache flush happens immediately after rotation; next OAuth flow uses the new secret.
5. KV v2 retains the previous version for configurable dual-credential window (default 30 minutes) before destruction.
6. Audit chain records rotation with timestamp and admin principal; secret value never appears in any log.

### User Story 4 — Super admin manages group-to-role mappings (Priority: P2)

A super admin configures `admins@company.com` Google Workspace group to map to the `admin` platform role.

**Independent Test:** Configure mapping via the admin UI. Log in with a user in that group. Verify the user is auto-provisioned with the `admin` role.

**Acceptance:**
1. Admin page shows a managed table for group/team-to-role mappings.
2. Add/remove rows validates: group format (email for Google, `org/team` for GitHub), role exists in the platform.
3. Save triggers validation and an audit chain entry with diff.
4. A new user from the mapped group who signs in via OAuth is provisioned with the `admin` role on first login.
5. A user in a non-mapped group is provisioned with the `defaultRole` (e.g., `user`).
6. Changes to the mapping apply only to future logins; existing users retain their current roles unless the admin explicitly reconciles.

### User Story 5 — Configuration export and GitOps promotion (Priority: P2)

A super admin exports the staging environment's configuration (including OAuth providers) to promote it to production.

**Independent Test:** Export config from staging. The bundle references Vault paths for secrets (no inline secrets). Import into production where the corresponding Vault paths already contain production secrets.

**Acceptance:**
1. Configuration export includes OAuth provider configs with secrets referenced by Vault path only.
2. Export YAML is readable and diff-able.
3. Import into a fresh production environment requires: production Vault paths already populated with production secrets.
4. Import produces a diff preview before apply.
5. Apply succeeds; production has Google+GitHub providers with production secrets from its own Vault.

---

### Edge Cases

- **`PLATFORM_OAUTH_GOOGLE_ENABLED=true` but `CLIENT_ID` missing**: installer fails fast with a clear error naming the missing variable.
- **Both `CLIENT_SECRET` and `CLIENT_SECRET_FILE` set**: installer fails with conflict error.
- **`ALLOWED_DOMAINS` or `ALLOWED_ORGS` empty**: installer emits a warning (security best practice is to restrict) but does not fail.
- **Invalid JSON in `GROUP_ROLE_MAPPINGS`**: installer fails with parse error; the existing provider config is not modified.
- **Unknown role in mapping**: installer fails with validation error listing valid roles.
- **Redirect URI not HTTPS in production** (`PLATFORM_ENVIRONMENT=production`): installer blocks unless `ALLOW_INSECURE=true` is also set, aligning with constitution rule 10.
- **Vault not reachable at install time**: installer fails with a clear error pointing to Vault reachability checks; bootstrap is NOT attempted.
- **Reseed action from admin UI when env vars are not present**: action returns a clear error explaining the env vars must be set in the running process.
- **Google provider already exists via IBOR sync**: env-var bootstrap skips to avoid conflict; warning emitted.

---

## Requirements

Summary of FR-639 through FR-648 (full text in the FR document):
- **FR-639**: Env-var seeding for Google and GitHub with complete configuration surface.
- **FR-640**: Idempotency with opt-in `FORCE_UPDATE` override.
- **FR-641**: Validation before persist (HTTPS redirect URI, format checks, JSON parseability).
- **FR-642**: Helm values for OAuth bootstrap with `clientSecretRef` or `clientSecretVaultPath`.
- **FR-643**: Extended super admin page with full surface (status, edit, rotate, test, reseed, source badge, history).
- **FR-644**: Configuration history with diffs.
- **FR-645**: Export/import includes provider config minus inline secrets.
- **FR-646**: Per-provider rate limits configurable via admin UI.
- **FR-647**: CI check for drift between code and documented OAuth env vars.
- **FR-648**: E2E coverage extending J01 and J19 for env-var bootstrap flows.

---

## Installer Changes

### New environment variables

**Google OAuth:**
| Variable | Required (if enabled) | Default | Description |
|---|---|---|---|
| `PLATFORM_OAUTH_GOOGLE_ENABLED` | No | `false` | Enable Google OAuth provider. |
| `PLATFORM_OAUTH_GOOGLE_CLIENT_ID` | Yes (if enabled) | — | Google OAuth client ID ending in `.apps.googleusercontent.com`. |
| `PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET` | No | — | Client secret. Exclusive with `_FILE`. Stored in Vault at canonical path. |
| `PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET_FILE` | No | — | Path to secret file. Exclusive with direct value. |
| `PLATFORM_OAUTH_GOOGLE_REDIRECT_URI` | Yes (if enabled) | — | Full HTTPS redirect URL. |
| `PLATFORM_OAUTH_GOOGLE_ALLOWED_DOMAINS` | No | `""` | Comma-separated Workspace domains. Empty = any. |
| `PLATFORM_OAUTH_GOOGLE_GROUP_ROLE_MAPPINGS` | No | `{}` | JSON mapping group emails to roles. |
| `PLATFORM_OAUTH_GOOGLE_REQUIRE_MFA` | No | `false` | Require platform MFA after OAuth. |
| `PLATFORM_OAUTH_GOOGLE_DEFAULT_ROLE` | No | `user` | Role when no group mapping applies. |
| `PLATFORM_OAUTH_GOOGLE_FORCE_UPDATE` | No | `false` | Overwrite existing config on reinstall. |

**GitHub OAuth:**
Same shape, `GITHUB` prefix: `ENABLED`, `CLIENT_ID`, `CLIENT_SECRET[_FILE]`, `REDIRECT_URI`, `ALLOWED_ORGS`, `TEAM_ROLE_MAPPINGS` (JSON), `REQUIRE_MFA`, `DEFAULT_ROLE`, `FORCE_UPDATE`.

### Helm values

```yaml
# deploy/helm/platform/values.yaml (new section)
oauth:
  google:
    enabled: false
    clientId: ""
    clientSecretRef:
      name: ""
      key: ""
    clientSecretVaultPath: ""     # e.g., secret/data/musematic/production/oauth/google/client-secret
    redirectUri: ""
    allowedDomains: []
    groupRoleMappings: {}
    requireMfa: false
    defaultRole: user
    forceUpdate: false
  github:
    enabled: false
    clientId: ""
    clientSecretRef:
      name: ""
      key: ""
    clientSecretVaultPath: ""
    redirectUri: ""
    allowedOrgs: []
    teamRoleMappings: {}
    requireMfa: false
    defaultRole: user
    forceUpdate: false
```

Precedence at install time:
1. Direct env var (`PLATFORM_OAUTH_*_CLIENT_SECRET`) wins.
2. `*_FILE` path read.
3. Helm `clientSecretRef` (Kubernetes Secret) read and copied to Vault if Vault mode is active.
4. Helm `clientSecretVaultPath` referenced directly (no copy) if Vault mode is active and the path already contains the secret.
5. If none of the above AND `_ENABLED=true`, installer fails with clear error.

## Backend Implementation

### Bootstrap module

Add `apps/control-plane/src/platform/auth/services/oauth_bootstrap.py`:

```python
async def bootstrap_oauth_providers_from_env(
    secret_provider: SecretProvider,
    oauth_repository: OAuthRepository,
    audit_service: AuditService,
    settings: PlatformSettings,
) -> None:
    """
    On startup, provision OAuth providers from PLATFORM_OAUTH_* env vars.
    Idempotent; respects FORCE_UPDATE flag.
    """
    for provider_type in (OAuthProviderType.GOOGLE, OAuthProviderType.GITHUB):
        config = _read_env_config(provider_type)
        if not config.enabled:
            continue
        _validate_config(config)
        existing = await oauth_repository.get_by_type(provider_type)
        if existing and not config.force_update:
            continue
        secret_value = _read_secret_value(config)
        vault_path = f"musematic/{settings.environment}/oauth/{provider_type.value}/client-secret"
        await secret_provider.put(path=vault_path, values={"value": secret_value})
        await _upsert_provider(
            oauth_repository,
            provider_type,
            config,
            client_secret_ref=vault_path,
            source="env_var",
        )
        await audit_service.record(
            event="oauth.provider.bootstrapped",
            metadata={"provider": provider_type.value, "source": "env_var"},
        )
```

Called from platform startup (`main.py`) after database migrations and Vault authentication.

### Extended admin router

Extend `auth/admin_router.py` (from UPD-036) with:
- `POST /api/v1/admin/oauth-providers/{id}/rotate-secret` — writes a new Vault version of the client secret.
- `POST /api/v1/admin/oauth-providers/{id}/test-connectivity` — performs OAuth discovery dry-run.
- `POST /api/v1/admin/oauth-providers/{id}/reseed-from-env` — re-reads env vars and updates provider config.
- `GET /api/v1/admin/oauth-providers/{id}/history` — returns change history with diffs.
- `GET /api/v1/admin/oauth-providers/{id}/rate-limits` / `PUT` — per-provider rate limit config.

## Super Admin UI Changes

Extend the existing `/admin/oauth-providers` page with:
- **Source badge**: `env_var` | `manual` | `imported` rendered per provider card.
- **Status panel**: last successful authentication timestamp, total authentications 24h / 7d / 30d, active linked users count.
- **Rotate secret** action with confirmation dialog; secret input is write-only and obscured.
- **Test connectivity** action (from UPD-037, here made production-grade with detailed diagnostics panel).
- **Reseed from environment** action (super admin only) with confirmation that this may overwrite manual changes.
- **Group/team role mappings** managed table: add, edit, delete rows with validation.
- **History tab**: chronological changes with before/after diffs and admin principal.
- **Rate limits tab**: per-provider rate limit configuration (per-IP, per-user, global).

## Acceptance Criteria

- [ ] All `PLATFORM_OAUTH_*` env vars recognized and parsed at startup.
- [ ] Installer validates env-var configuration before persisting.
- [ ] Google and GitHub providers auto-provisioned on fresh install when enabled.
- [ ] Client secrets written to Vault at canonical paths (UPD-040 compliant).
- [ ] `FORCE_UPDATE=false` preserves manual adjustments on reinstall.
- [ ] `FORCE_UPDATE=true` overwrites with a critical audit chain entry.
- [ ] Login and signup pages show OAuth buttons for enabled providers.
- [ ] OAuth flow end-to-end works for both providers after env-var bootstrap.
- [ ] Admin page displays `source=env_var` badge for bootstrapped providers.
- [ ] Rotate secret action writes a new Vault version and flushes cache.
- [ ] Test connectivity returns success for a valid provider and failure with details for a misconfigured one.
- [ ] Reseed action re-reads env vars and updates config with audit entry.
- [ ] Group/team role mappings editable via admin UI with validation.
- [ ] History tab shows chronological changes with diffs.
- [ ] Configuration export includes providers with Vault path references only (no inline secrets).
- [ ] Configuration import restores providers minus secrets; import blocked if Vault paths missing.
- [ ] Per-provider rate limits enforced server-side.
- [ ] CI check flags drift between code-referenced env vars and documentation.
- [ ] J01 Platform Administrator journey extended to exercise env-var bootstrap.
- [ ] J19 New User Signup journey extended to cover pre-configured OAuth from env vars.
- [ ] No regression in existing manual OAuth configuration path.
