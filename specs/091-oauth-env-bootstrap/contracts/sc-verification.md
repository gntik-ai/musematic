# SC Verification Record - 091 OAuth Env Bootstrap

Generated: 2026-04-30

This record captures the local verification completed during implementation. Cluster-only success criteria remain pending until a live kind or CI matrix run is available.

| SC | Status | Evidence |
| --- | --- | --- |
| SC-001 | Pending cluster | E2E suite scaffolds bootstrap timing checks; no live kind startup timing measured in this workspace. |
| SC-002 | Local coverage | Backend bootstrap tests cover idempotency, manual preservation, and force-update audit behavior. |
| SC-003 | Local coverage | Backend/admin tests cover rotate-secret 204 response, Vault write path, cache flush, and no plaintext response. |
| SC-004 | Local coverage | Frontend regression tests cover OAuth button behavior against enabled provider mocks; live browser smoke on kind is pending. |
| SC-005 | Local coverage | Admin panel tests cover `env_var`, `manual`, and `imported` source badges. |
| SC-006 | Local coverage | Admin panel tests cover test-connectivity action and diagnostic rendering. |
| SC-007 | Local coverage | Backend tests cover reseed success and missing env-var 400 response. |
| SC-008 | Local coverage | Admin panel and E2E scaffolding cover role-mapping validation and future-login mapping expectations. |
| SC-009 | Local coverage | Admin panel tests cover history rendering; backend tests cover history endpoint shape. |
| SC-010 | Local coverage | Ops CLI tests verify deterministic export and no secret values. |
| SC-011 | Local coverage | Ops CLI tests verify Vault path validation before apply and missing-path failure. |
| SC-012 | Pending cluster/load | Rate-limit endpoint/UI tests exist; synthetic 100 req/min enforcement run is pending. |
| SC-013 | Local pass | `python scripts/generate-env-docs.py --output docs/configuration/environment-variables.md`; OAuth env vars are documented and secret fields are sensitive. |
| SC-014 | Pending 24h log capture | Secret-access scanner passes locally; 24-hour `kubectl logs` regex sweep requires a live cluster. |
| SC-015 | Pending CI matrix | J01 extension and J19 creation collect locally; full 3-mode matrix run is pending. |
| SC-016 | Local coverage | Audit payloads and service methods emit `auth.oauth.{action}` event names. |
| SC-017 | Local coverage | Bootstrap tests cover Vault unreachability fail-fast behavior. |
| SC-018 | Local coverage | Bootstrap tests cover concurrent bootstrap locking/idempotency behavior. |
| SC-019 | Local pass | Alembic upgrade/downgrade/head cycle completed for `069_oauth_provider_env_bootstrap`. |
| SC-020 | Local pass | Focused OAuth admin/backend regression suites pass; full web gate remains pending. |

## Local Commands

- `apps/control-plane/.venv/bin/python -m pytest tests/common/test_oauth_bootstrap_settings.py tests/auth/test_oauth_bootstrap.py tests/auth/test_oauth_admin_endpoints.py -q`
- `apps/ops-cli/.venv/bin/python -m pytest tests/commands/admin/test_oauth.py -q`
- `apps/web/./node_modules/.bin/vitest run components/features/auth/OAuthProviderButtons.test.tsx components/features/auth/OAuthProviderAdminPanel.test.tsx`
- `tests/e2e/.venv/bin/python -m pytest suites/oauth_bootstrap journeys/test_j19_new_user_signup.py journeys/test_j01_admin_bootstrap.py --collect-only -q`
- `python scripts/check-secret-access.py`
- `python scripts/generate-env-docs.py --output docs/configuration/environment-variables.md`
