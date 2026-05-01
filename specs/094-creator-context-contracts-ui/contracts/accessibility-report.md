# Accessibility Report

Date: 2026-05-01

## Surfaces

UPD-044 adds or extends the following creator UI surfaces:

- `/agent-management/{fqn}/context-profile`
- `/agent-management/{fqn}/context-profile/history`
- `/agent-management/{fqn}/contract`
- `/agent-management/{fqn}/contract/history`
- `/agent-management/contracts/library`
- `ExecutionDrilldown` Context tab
- `CompositionWizard` steps 5-9

## Static Review

- Primary actions use buttons with visible labels and lucide icons.
- Monaco wrappers expose explicit labels through `SchemaValidatedEditor` and
  `YamlJsonEditor` passes an explicit Monaco `ariaLabel` in the form
  `{label} code editor`.
- The profile preview provenance surface renders source origin, snippet, score,
  included state, and classification without color-only meaning.
- The real-LLM path is behind an explicit opt-in dialog requiring typed
  confirmation.

## Local Scan

Commands run against a local Next.js dev server at `http://127.0.0.1:3000`:

```sh
PNPM_HOME=/tmp/pnpm-home XDG_CACHE_HOME=/tmp/xdg-cache \
  PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 \
  pnpm exec playwright test --config tests/a11y/playwright.a11y.config.ts \
  tests/a11y/creator-uis.spec.ts --project=a11y-light-en
```

Result: 5 passed, covering:

- `/agent-management/{fqn}/context-profile`
- `/agent-management/{fqn}/context-profile/history`
- `/agent-management/{fqn}/contract`
- `/agent-management/{fqn}/contract/history`
- `/agent-management/contracts/library`

Keyboard/screen-reader affordance verification:

```sh
PNPM_HOME=/tmp/pnpm-home XDG_CACHE_HOME=/tmp/xdg-cache \
  PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 \
  pnpm exec playwright test tests/e2e/creator-uis-pages.spec.ts \
  --project=chromium -g "Monaco editor surfaces"
```

Result: 1 passed. The test focuses both Monaco editor controls, verifies the
profile and contract editors expose `{label} code editor` accessible names, and
exercises ESC after editor focus.
