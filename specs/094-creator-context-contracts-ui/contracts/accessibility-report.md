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
- Monaco wrappers expose explicit labels through `SchemaValidatedEditor`.
- The profile preview provenance surface renders source origin, snippet, score,
  included state, and classification without color-only meaning.
- The real-LLM path is behind an explicit opt-in dialog requiring typed
  confirmation.

## Local Scan

No axe browser scan was run in this sandbox. The web Playwright fixture
`apps/web/tests/e2e/creator-uis-pages.spec.ts` was added to cover the core
profile, contract, and template pages with mocked APIs. Full AA verification
still needs a running web app plus the project axe workflow.
