# Success Criteria Verification

Status: partial local verification complete; live measurements pending.

## Local Checks

- Alembic verification passed against a fresh PostgreSQL 16 container on 2026-04-30: `upgrade head` reached `095_status_page_and_scenarios`; targeted `071_workspace_owner_workbench` upgrade added `quota_config`, `dlp_rules`, `residency_config`, and `two_person_approval_challenges`; downgrade back to `070_user_self_service_extensions` removed those three columns and the table.
- Backend UPD-043 tests passed with `pytest tests/two_person_approval tests/workspaces tests/connectors tests/auth` from `apps/control-plane`: 37 passed.
- Additional 2PA unit coverage passed with `pytest tests/unit/two_person_approval`: 6 passed.
- Workspace-owner E2E contract suite passed with `pytest suites/workspace_owner -v` from `tests/e2e`: 12 passed.
- J20 static workspace-owner journey passed with `pytest journeys/test_j20_workspace_owner.py -v`: 1 passed.
- Frontend unit suite passed with `pnpm --dir apps/web test`: 161 files, 520 tests passed.
- Frontend type check passed with `pnpm --dir apps/web type-check` using `/tmp` tool caches.
- Frontend lint passed with `pnpm --dir apps/web lint`.
- i18n parity passed with `pnpm --dir apps/web test:i18n-parity`.
- Rule 33 2PA concurrent approve verification passed against PostgreSQL 16: one co-signer approved, one concurrent co-signer was rejected after row-lock serialization.
- Workspace-owner axe scan passed with `pnpm --dir apps/web exec playwright test --config tests/a11y/playwright.a11y.config.ts tests/a11y/workspace-owner.spec.ts --project=a11y-light-en --reporter=line` against local Next.js at `http://127.0.0.1:3100`.
- Workspace-owner Playwright spec passed with `pnpm --dir apps/web exec playwright test tests/e2e/workspace-owner-pages.spec.ts --project=chromium --reporter=line` against local Next.js at `http://127.0.0.1:3100`.
- Static Rule 45 endpoint-to-UI mapping is documented in `rule45-ui-mapping.md`.
- Playwright and Python E2E scaffolding were added for workspace-owner pages, J20, and J01 IBOR extensions.
- J01 live journey was attempted on 2026-04-30 and blocked before test execution because `http://localhost:8081` had no platform API listener for the session-level seed fixture.

## Pending Live Measurements

- SC-001 dashboard load under 3 seconds with seeded data.
- SC-014 visibility graph render at 500 nodes under 1 second in a browser run.
- Matrix CI in `mock`, `kubernetes`, and `vault` modes.
- 24-hour secret-leak log sweep.
- Full journey execution against kind.
- J01 live journey execution against a running platform API.
