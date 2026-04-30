# Success Criteria Verification

Date: 2026-05-01

## Completed Local Checks

- Local rerun on 2026-05-01 confirmed the same results below. The only warning
  noise was pre-existing React `act(...)` and zero-sized chart test warnings in
  unrelated web tests; all commands exited successfully.
- Backend creator-preview and versioning test files were added for the new
  services.
- Creator UI E2E API suite was added under
  `tests/e2e/suites/creator_uis/`.
- Web Playwright coverage was added at
  `apps/web/tests/e2e/creator-uis-pages.spec.ts`.
- `pnpm lint`, `pnpm type-check`, `pnpm test`, and
  `pnpm test:i18n-parity` passed for `apps/web`.
- `apps/web/tests/e2e/creator-uis-pages.spec.ts` passed on Chromium against a
  local Next.js dev server at `http://127.0.0.1:3000` with 22 passing
  scenarios, including the Monaco keyboard/screen-reader label check.
- `apps/web/tests/a11y/creator-uis.spec.ts` passed on `a11y-light-en` with
  5/5 creator routes passing axe WCAG 2.1 A/AA checks.
- The targeted UPD-044 control-plane tests passed through `uv` with
  29 passing tests.

## Local Commands

```sh
cd apps/control-plane && UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/mock_llm/test_provider.py \
  tests/context_engineering/test_versioning.py \
  tests/context_engineering/test_preview.py \
  tests/trust/test_contract_preview.py \
  tests/trust/test_contract_templates.py \
  tests/trust/test_attach_to_revision.py \
  -q
```

Result: 29 passed.

```sh
cd apps/web && PNPM_HOME=/tmp/pnpm-home XDG_CACHE_HOME=/tmp/xdg-cache pnpm lint
cd apps/web && PNPM_HOME=/tmp/pnpm-home XDG_CACHE_HOME=/tmp/xdg-cache pnpm type-check
cd apps/web && PNPM_HOME=/tmp/pnpm-home XDG_CACHE_HOME=/tmp/xdg-cache pnpm test
cd apps/web && PNPM_HOME=/tmp/pnpm-home XDG_CACHE_HOME=/tmp/xdg-cache pnpm test:i18n-parity
```

Results: lint passed; type-check passed; 161 Vitest files / 520 tests passed;
i18n parity passed for 5 locale catalogs.

```sh
cd apps/web && PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 \
  pnpm exec playwright test tests/e2e/creator-uis-pages.spec.ts --project=chromium
```

Result: 22 passed.

```sh
cd apps/web && PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 \
  pnpm exec playwright test --config tests/a11y/playwright.a11y.config.ts \
  tests/a11y/creator-uis.spec.ts --project=a11y-light-en
```

Result: 5 passed.

## Blocked Checks

- Alembic upgrade/downgrade verification is blocked locally because
  `DATABASE_URL` / `POSTGRES_DSN` is unset. The correct command,
  `UV_CACHE_DIR=/tmp/uv-cache uv run alembic -c migrations/alembic.ini upgrade head`,
  fails at `migrations/env.py` with `RuntimeError: DATABASE_URL or POSTGRES_DSN
  must be set for Alembic migrations.` Docker/testcontainers access is also
  blocked by the current approval policy, and no local PostgreSQL is listening
  on `localhost:5432`.
- `pytest tests/e2e/suites/creator_uis/ -v` and
  `pytest tests/e2e/journeys/test_j02_creator_to_publication.py -v` both stop
  in the shared E2E seed/login fixture because no platform API is listening on
  `http://localhost:8081` (`httpx.ConnectError: All connection attempts
  failed`).
- Matrix-CI verification is blocked because the current branch has no GitHub PR
  and no Actions runs.

## Follow-Up Required In CI

- Run Alembic upgrade/downgrade against a migrated PostgreSQL database.
- Run `pytest tests/e2e/suites/creator_uis/ -v` against a deployed stack.
- Run `pytest tests/e2e/journeys/test_j02_creator_to_publication.py -v`
  against the same stack.
- Open a PR and run the matrix-CI modes (`mock`, `kubernetes`, `vault`).
