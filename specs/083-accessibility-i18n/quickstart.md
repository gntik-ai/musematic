# Accessibility and Localization Quickstart

This walkthrough is the local smoke path for feature 083. It exercises the
implemented backend localization BC, frontend locale/theme wiring, and axe-core
runner. It also calls out the external gates that cannot be completed from a
Linux-only developer workspace.

## Preflight

Run the Speckit prerequisite check with the explicit feature override if the
current branch is a completion branch:

```bash
SPECIFY_FEATURE=083-accessibility-i18n \
  .specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

Check that the local E2E dependencies are available:

```bash
make dev-check
```

## Start the Local Platform

Bring up the kind-backed control plane and web UI:

```bash
make dev-up
```

The default local URLs are:

```text
API: http://localhost:8081
UI:  http://localhost:8080
```

Confirm the API is reachable:

```bash
curl -fsS http://localhost:8081/healthz
```

Seed data is normally applied by the E2E test harness. If manual seeding is
needed, run:

```bash
cd tests/e2e
PLATFORM_API_URL=http://localhost:8081 python3 -m seeders.base --all
cd ../..
```

Then use the seeded superadmin account:

```bash
curl -fsS -X POST http://localhost:8081/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"superadmin@e2e.test","password":"e2e-test-password"}'
```

## Publish and Resolve a Locale

Capture a superadmin token:

```bash
TOKEN="$(
  curl -fsS -X POST http://localhost:8081/api/v1/auth/login \
    -H 'content-type: application/json' \
    -d '{"email":"superadmin@e2e.test","password":"e2e-test-password"}' |
    jq -r '.access_token // .accessToken // .token // .access.token'
)"
```

Publish the Spanish catalogue from the checked-in message file:

```bash
jq -n --slurpfile translations apps/web/messages/es.json \
  '{locale_code:"es", translations:$translations[0], vendor_source_ref:"local-smoke"}' |
  curl -fsS -X POST http://localhost:8081/api/v1/admin/locales \
    -H "authorization: Bearer ${TOKEN}" \
    -H 'content-type: application/json' \
    --data-binary @-
```

Verify locale negotiation precedence:

```bash
curl -fsS -X POST http://localhost:8081/api/v1/locales/resolve \
  -H "authorization: Bearer ${TOKEN}" \
  -H 'content-type: application/json' \
  -d '{"url_hint":"ja","user_preference":"es","accept_language":"fr-FR,fr;q=0.9,en;q=0.8"}'
```

Expected result:

```json
{"locale":"ja","source":"url"}
```

Patch a user's locale and High-Contrast theme preference:

```bash
curl -fsS -X PATCH http://localhost:8081/api/v1/me/preferences \
  -H "authorization: Bearer ${TOKEN}" \
  -H 'content-type: application/json' \
  -d '{"language":"es","theme":"high_contrast","timezone":"Europe/Madrid"}'
```

The response should set both `musematic-locale=es` and
`musematic-theme=high_contrast` cookies.

## Extract and Render a String

For any route or component in `apps/web/app/` or `apps/web/components/`:

1. Add the English key to `apps/web/messages/en.json` under the route namespace.
2. Add matching keys to the five non-English catalogues or route the change
   through the vendor sync flow.
3. Replace the literal with `useTranslations("<namespace>")` and `t("<key>")`.
4. Remove the touched file or route group from the ESLint allowlist in
   `apps/web/eslint.config.mjs`.

Run the lint rule after each extraction:

```bash
cd apps/web
pnpm lint
```

Current implementation note: the rule still allowlists `app/` and
`components/`, so full T032 completion requires removing those allowlist entries
after the route/component extraction wave is finished.

## Run Accessibility Checks

With the UI reachable, run the axe-core suite:

```bash
cd apps/web
PLAYWRIGHT_BASE_URL=http://localhost:8080 pnpm test:a11y
```

The runner covers the audited surfaces across:

```text
themes:  light, dark, system, high_contrast
locales: en, es, fr, de, ja, zh-CN
```

For a narrower local check while iterating:

```bash
cd apps/web
PLAYWRIGHT_BASE_URL=http://localhost:8080 pnpm exec playwright test \
  tests/a11y/preferences.spec.ts \
  --config=tests/a11y/playwright.a11y.config.ts \
  --project=a11y-high_contrast-es
```

## Translation Vendor Sync

Feature 083 is wired for Lokalise:

```bash
cd apps/control-plane
python -m platform.localization.tooling.vendor_sync --vendor lokalise \
  --repo-root ../..
```

Required environment:

```text
LOCALIZATION_VENDOR_API_TOKEN
LOKALISE_PROJECT_ID
```

The CI job resolves the token through the existing SecretProvider path and opens
a translation-sync PR if non-English catalogues change. Provisioning the
Lokalise project and commissioning native-speaker review remain external gates;
see `docs/localization/vendor-onboarding-083.md`.

## Manual Assistive-Technology Pass

axe-core does not replace a real screen-reader pass. Run VoiceOver on macOS and
NVDA on Windows across the audited surfaces before release, and record results
in `docs/accessibility/manual-verification-083.md`.

## Smoke-Run Notes

2026-04-29 local preflight:

- `make dev-check` passed in this workspace.
- `SPECIFY_FEATURE=083-accessibility-i18n ... check-prerequisites.sh` passed and
  resolved `specs/083-accessibility-i18n`.
- A running kind environment was already available, and
  `curl -fsS http://localhost:8081/healthz` returned healthy dependencies.
- `PLATFORM_API_URL=http://localhost:8081 python3 -m seeders.base --all`
  seeded the missing `superadmin@e2e.test` account.
- Locale publish initially failed with Kafka `UnknownTopicOrPartitionError`
  because `localization.events` was missing from the Kafka Helm topic values.
  The chart now includes `localization.events`; the local cluster was patched
  with `localization.events` and `localization.events.dlq` KafkaTopic resources.
- `POST /api/v1/admin/locales` succeeded for `fr` with
  `vendor_source_ref=local-smoke-superadmin`.
- `POST /api/v1/locales/resolve` returned `{"locale":"ja","source":"url"}`.
- `PATCH /api/v1/me/preferences` returned 200 and set
  `musematic-theme=high_contrast` plus `musematic-locale=es`.
- Narrow axe smoke passed:
  `PLAYWRIGHT_BROWSERS_PATH=/tmp/ms-playwright PLAYWRIGHT_BASE_URL=http://localhost:8080 ./node_modules/.bin/playwright test tests/a11y/preferences.spec.ts --config=tests/a11y/playwright.a11y.config.ts --project=a11y-high_contrast-es`.
- `pnpm exec` could not be used in this sandbox because it tried to write under
  `/home/andrea/.local/share/pnpm`; the repo-local Playwright binary worked.
