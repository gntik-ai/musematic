# OAuth Providers

OAuth provider settings live in `/admin/settings?tab=oauth`. Platform admins can configure Google and GitHub providers, inspect source and health state, rotate secrets, test connectivity, manage role mappings, review history, and tune per-provider rate limits.

## Source And Status

Each provider shows a source badge:

- `env_var`: created or reseeded from `PLATFORM_OAUTH_*` bootstrap variables.
- `manual`: configured directly by an admin.
- `imported`: applied from `platform-cli admin oauth import`.

The status panel shows last successful authentication, recent auth counts, active linked users, and the latest connectivity result.

## Rotate Secret

The rotate action accepts a new client secret in a write-only field. The API writes a new Vault KV v2 version, flushes the provider cache, emits `auth.oauth.secret_rotated`, and returns `204 No Content`. The current or replacement secret is never displayed.

## Reseed From Environment

Reseed re-reads the running pod's `PLATFORM_OAUTH_GOOGLE_*` or `PLATFORM_OAUTH_GITHUB_*` variables. Without `force_update`, manual changes are preserved. With `force_update=true`, env-var values overwrite existing provider config and a critical `auth.oauth.config_reseeded` audit entry records the override.

## Role Mappings

Google group mappings and GitHub team mappings map upstream group/team names to platform roles. Validation rejects malformed mapping keys and unknown roles. Mapping changes apply to future first-time OAuth logins only; existing user roles are not reconciled automatically.

## History

The history tab lists provider changes with timestamp, admin principal, action, and before/after diff. Use it to confirm bootstrap, reseed, import, rotation, role-mapping, and rate-limit changes.

## Rate Limits

The rate-limits tab controls per-IP, per-user, and global limits for each provider. Per-provider values take precedence over the global OAuth rate-limit defaults.

## Connectivity

Use test connectivity before enabling a provider or after changing redirect URI, client ID, scopes, domain/org allow-lists, or role mappings. Diagnostic messages should identify the failure class without exposing secrets.
