# SC Verification Record - 091 OAuth Env Bootstrap

Generated: 2026-04-30

This record captures the local verification completed during implementation. Cluster-only success criteria remain pending until a live kind or CI matrix run is available.

| SC | Status | Evidence |
| --- | --- | --- |
| SC-001 | Pending cluster | E2E suite scaffolds bootstrap timing checks; no live kind startup timing measured in this workspace. |
| SC-002 | Local coverage | Backend bootstrap tests cover idempotency, manual preservation, and force-update audit behavior. |
| SC-003 | Local coverage | Backend/admin tests cover rotate-secret 204 response, Vault write path, cache flush, and no plaintext response. |
| SC-004 | Local coverage | Frontend regression tests cover OAuth button behavior against enabled provider mocks; live browser smoke on kind is pending. |
| SC-005 | Local coverage | Admin panel tests cover `env_var`, `manual`, and `imported` source badges. Focused axe scan covers the OAuth admin configuration/status/role/history/rate-limit tabs. |
| SC-006 | Local coverage | Admin panel tests cover test-connectivity action and diagnostic rendering. Focused axe scan confirms the shared admin nav link-name regression is fixed. |
| SC-007 | Local coverage | Backend tests cover reseed success and missing env-var 400 response. |
| SC-008 | Local coverage | Admin panel and E2E scaffolding cover role-mapping validation and future-login mapping expectations. |
| SC-009 | Local coverage | Admin panel tests cover history rendering; backend tests cover history endpoint shape. |
| SC-010 | Local coverage | Ops CLI tests verify deterministic export and no secret values. |
| SC-011 | Local coverage | Ops CLI tests verify Vault path validation before apply and missing-path failure. |
| SC-012 | Pending cluster/load | Rate-limit endpoint/UI tests exist; synthetic 100 req/min enforcement run is pending. |
| SC-013 | Local pass | `python scripts/generate-env-docs.py --output docs/configuration/environment-variables.md`; OAuth env vars are documented and secret fields are sensitive. `helm-docs` dry-run diff and aggregated Helm values diff are clean after adding `controlPlane.oauth.*`/`oauth.*` rows. |
| SC-014 | Pending 24h log capture | Secret-access scanner passes locally; 24-hour `kubectl logs` regex sweep requires a live cluster. |
| SC-015 | Pending CI matrix | J01 extension and J19 creation collect locally; full 3-mode matrix run is pending. `kubectl config current-context` reports no current context in this workspace. |
| SC-016 | Local coverage | Audit payloads and service methods emit `auth.oauth.{action}` event names. |
| SC-017 | Local coverage | Bootstrap tests cover Vault unreachability fail-fast behavior. |
| SC-018 | Local coverage | Bootstrap tests cover concurrent bootstrap locking/idempotency behavior. |
| SC-019 | Local pass | Alembic upgrade/downgrade/head cycle completed for `069_oauth_provider_env_bootstrap`. |
| SC-020 | Local pass | Focused OAuth admin/backend regression suites pass; full web unit, typecheck, and lint gates pass locally. |

## Local Commands

- `apps/control-plane/.venv/bin/python -m pytest tests/common/test_oauth_bootstrap_settings.py tests/auth/test_oauth_bootstrap.py tests/auth/test_oauth_admin_endpoints.py -q`
- `apps/ops-cli/.venv/bin/python -m pytest tests/commands/admin/test_oauth.py -q`
- `apps/web/./node_modules/.bin/vitest run components/features/auth/OAuthProviderButtons.test.tsx components/features/auth/OAuthProviderAdminPanel.test.tsx`
- `tests/e2e/.venv/bin/python -m pytest suites/oauth_bootstrap journeys/test_j19_new_user_signup.py journeys/test_j01_admin_bootstrap.py --collect-only -q`
- `python scripts/check-secret-access.py`
- `python scripts/generate-env-docs.py --output docs/configuration/environment-variables.md`

## 2026-04-30 Local Follow-Up

- `apps/control-plane/.venv/bin/python -m pytest apps/control-plane/tests/auth/ -q` -> 21 passed.
- `apps/ops-cli/.venv/bin/python -m pytest apps/ops-cli/tests/commands/admin/ -q` -> 14 passed.
- `tests/e2e/.venv/bin/python -m pytest tests/e2e/suites/oauth_bootstrap/ tests/e2e/journeys/test_j01_admin_bootstrap.py tests/e2e/journeys/test_j19_new_user_signup.py --collect-only -q` -> 33 tests collected.
- `PLAYWRIGHT_BROWSERS_PATH=/tmp/ms-playwright PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 ./node_modules/.bin/playwright test --config tests/a11y/playwright.a11y.config.ts tests/a11y/admin-settings.spec.ts --project=a11y-light-en` -> 6 passed after adding OAuth tab surfaces and fixing `Button asChild` prop forwarding.
- `./node_modules/.bin/vitest run` from `apps/web` -> 161 files / 520 tests passed.
- `./node_modules/.bin/tsc --noEmit` from `apps/web` -> passed.
- `./node_modules/.bin/eslint . --max-warnings=0` from `apps/web` -> passed.
- `python scripts/check-secret-access.py` -> passed.
- `python scripts/check-admin-role-gates.py` -> passed.
- `python scripts/check-doc-references.py` -> passed with informational uncovered-FR output only.
- `python scripts/check-doc-translation-parity.py docs` -> passed with grace-window warnings.
- `python scripts/generate-env-docs.py --output /tmp/musematic-env-vars.md && diff -u docs/configuration/environment-variables.md /tmp/musematic-env-vars.md` -> no diff.
- `GOMODCACHE=/tmp/codex-gomodcache GOCACHE=/tmp/codex-gocache GOENV=off GOSUMDB=off go run github.com/norwoodj/helm-docs/cmd/helm-docs@v1.13.1 --chart-search-root=deploy/helm/platform --dry-run --log-level panic | diff -u deploy/helm/platform/README.md -` -> content matches; dry-run output includes one trailing blank line that was omitted from the committed README so `git diff --check` remains clean.
- `python scripts/aggregate-helm-docs.py | diff -u docs/configuration/helm-values.md -` -> no diff.
- `HELM_CACHE_HOME=/tmp/helmcache HELM_CONFIG_HOME=/tmp/helmconfig HELM_DATA_HOME=/tmp/helmdata helm template platform deploy/helm/platform/ --set controlPlane.oauth.google.enabled=true --set controlPlane.oauth.google.clientId=test.apps.googleusercontent.com --set controlPlane.oauth.google.clientSecretRef.name=google-oauth --set controlPlane.oauth.google.redirectUri=https://app.example.com/auth/oauth/google/callback` -> renders expected `PLATFORM_OAUTH_GOOGLE_*` config and `/etc/secrets/google-client-secret` mount.

Cluster-only evidence still pending:

- `kubectl config current-context` reports `error: current-context is not set`; `kubectl get nodes --request-timeout=5s` falls back to localhost and is refused.
- Kind-cluster OAuth login/signup smoke, 3-mode matrix CI, real J01/J19 journey execution, and 24-hour log secret regex capture were not run locally.
- Platform chart top-level `--set oauth.google.*` does not flow into the aliased `controlPlane` subchart. The verified umbrella command uses `--set controlPlane.oauth.google.*`.
