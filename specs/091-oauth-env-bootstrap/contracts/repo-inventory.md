# Repo Inventory — UPD-041 OAuth Env Bootstrap

Date: 2026-04-27

## UPD-040 Merge State

- `git log --all --grep "UPD-040"` confirms UPD-040 is present:
  - `e5374bb Merge pull request #90 from gntik-ai/090-hashicorp-vault-integration`
  - `7418f57 fix(UPD-040): restore secret-provider compatibility and docs drift`
  - `d34f219 chore(UPD-040): speckit implement leftovers`

## Secret Provider Surface

- `apps/control-plane/src/platform/common/secret_provider.py` exists.
- Actual on-disk surface at implementation start contained:
  - `SecretProvider` Protocol with `get`, `put`, `delete_version`, `list_versions`, `health_check`
  - `MockSecretProvider`
  - canonical path validation helpers
- The task text expected `VaultSecretProvider` and `KubernetesSecretProvider`, but those classes were not present on disk. UPD-041 was therefore implemented against the canonical `SecretProvider` Protocol and the existing application `app.state.secret_provider` surface.
- UPD-041 adds `flush_cache(path: str | None = None)` to the Protocol and mock provider so rotation can call it without echoing secrets.

## OAuth Backend Surface

- `apps/control-plane/src/platform/auth/services/oauth_service.py` existed with OAuth authorize/callback/link/provision behavior.
- Before UPD-041, `_resolve_secret()` still contained the legacy `OAUTH_SECRET_*` fallback. UPD-041 removes that fallback and resolves via `SecretProvider` when the reference is not `plain:*`.
- `apps/control-plane/src/platform/auth/router_oauth.py` existed with public OAuth endpoints plus admin list/upsert/test-connectivity/audit endpoints.
- The test-connectivity backend endpoint existed with dual-prefix routing.

## Admin UI Surface

- `apps/web/components/features/auth/OAuthProviderAdminPanel.tsx` exists and is 381 lines on disk.
- `apps/web/components/features/admin/AdminSettingsPanel.tsx` registers OAuth as an admin settings tab.
- `OAuthProviderAdminPanel.tsx` had no test-connectivity UI button at implementation start.
