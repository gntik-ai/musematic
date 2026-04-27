# Cross-Feature Dependencies — UPD-041 OAuth Env Bootstrap

Date: 2026-04-27

## UPD-036 Administrator Workbench

- Admin settings tab registration exists at `apps/web/components/features/admin/AdminSettingsPanel.tsx`.
- OAuth tab is imported from `apps/web/components/features/auth/OAuthProviderAdminPanel.tsx`.

## UPD-037 Public Signup OAuth

- Public OAuth buttons exist at `apps/web/components/features/auth/OAuthProviderButtons.tsx`.
- Dedicated callback route exists at `apps/web/app/(auth)/auth/oauth/[provider]/callback/page.tsx`.
- Backend test-connectivity endpoint exists at `apps/control-plane/src/platform/auth/router_oauth.py`.

## UPD-039 Documentation

- `scripts/generate-env-docs.py` exists.
- UPD-041 did not regenerate generated env-var documentation in this backend slice.

## UPD-040 Vault Integration

- UPD-040 merge history is present.
- The actual common SecretProvider implementation does not yet include concrete Vault/Kubernetes provider classes; UPD-041 is wired to the shared Protocol and mock provider available in this branch.
