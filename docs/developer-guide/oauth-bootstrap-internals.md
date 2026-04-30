# OAuth Bootstrap Internals

OAuth bootstrap is implemented in `apps/control-plane/src/platform/auth/services/oauth_bootstrap.py` and runs during control-plane startup after super admin bootstrap.

## Settings

`OAuthBootstrapSettings` hangs off `PlatformSettings.oauth_bootstrap` and resolves to `PLATFORM_OAUTH_GOOGLE_*` and `PLATFORM_OAUTH_GITHUB_*` variables. Provider classes validate client ID shape, HTTPS redirect URI requirements, role mappings, and mutually exclusive secret inputs.

## Secret Flow

Bootstrap resolves one secret input, writes it immediately through `SecretProvider.put`, and stores only the Vault reference on the OAuth provider row. Canonical paths use:

```text
secret/data/musematic/{environment}/oauth/{provider}/client-secret
```

Secret resolution for runtime OAuth callbacks delegates to `SecretProvider.get`.

## Persistence

Migration `069_oauth_provider_env_bootstrap.py` adds `source`, `last_edited_by`, `last_edited_at`, `last_successful_auth_at`, and the `oauth_provider_rate_limits` table. Existing provider rows default to `source=manual`.

## Idempotency

Bootstrap locks the provider row before applying changes. Existing providers are skipped unless `force_update=true`. Force updates emit a critical `auth.oauth.config_reseeded` event before overwriting manual configuration.

## Audit Events

New OAuth events follow the `auth.oauth.{action}` convention:

- `auth.oauth.provider_bootstrapped`
- `auth.oauth.secret_rotated`
- `auth.oauth.config_reseeded`
- `auth.oauth.role_mapping_updated`
- `auth.oauth.rate_limit_updated`
- `auth.oauth.config_imported`
- `auth.oauth.config_exported`

Audit metadata includes changed field names and provider identifiers, not plaintext secrets.

## Helm

The standalone control-plane chart consumes `oauth.*` values. The umbrella platform chart passes dependency values through `controlPlane.oauth.*`; keep top-level `oauth.*` documentation in sync with the dependency block until the umbrella chart stops using an aliased subchart.
