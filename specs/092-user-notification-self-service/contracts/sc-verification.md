# UPD-042 Success Criteria Verification

Status: blocked pending full platform run.

## Required Sweep

The final sweep must verify SC-001 through SC-020 from `spec.md` against a live environment with the control plane, web UI, Redis, PostgreSQL, audit chain, and WebSocket gateway running.

| SC | Measurement |
| --- | --- |
| SC-001 | Bell badge reaches 15 unread alerts within 3 seconds. |
| SC-002 | `/notifications` first paint for 50 alerts is at or below 800 ms p95. |
| SC-003 | Mark-all-read clears the local badge within 2 seconds and other tabs within 5 seconds. |
| SC-004 | Notification preference save completes within 500 ms. |
| SC-005 | Mandatory event toggles cannot disable all channels. |
| SC-006 | API key creation performs MFA step-up when enrolled. |
| SC-007 | API key value is shown once and never appears in list responses. |
| SC-008 | Max 10 personal API keys is enforced. |
| SC-009 | API key revocation propagates within 5 seconds. |
| SC-010 | MFA enrollment displays QR, text secret, and backup codes. |
| SC-011 | Backup-code regeneration shows new one-time codes. |
| SC-012 | MFA disable is refused when admin policy enforces MFA. |
| SC-013 | Session revocation propagates within 60 seconds. |
| SC-014 | 24-hour log scan shows zero secret leaks. |
| SC-015 | Consent revocation takes effect within the configured cache window. |
| SC-016 | DSR self-service creates the same row contract as admin DSR. |
| SC-017 | User activity returns actor-or-subject audit entries. |
| SC-018 | All `/api/v1/me/*` endpoints reject caller-supplied user scope. |
| SC-019 | Accessibility scan shows zero WCAG AA violations on the 9 pages. |
| SC-020 | Existing admin-equivalent surfaces continue to pass. |

## Current Workspace Result

Partial local verification was completed on 2026-04-30:

- SC-018 static scope gate passed: `python scripts/check-me-endpoint-scope.py`.
- SC-019 self-service axe scan passed for the 9 audited pages: `216 passed` via `apps/web/tests/a11y/self-service.spec.ts`.
- Mocked self-service browser coverage passed: `pnpm --dir apps/web test:e2e tests/e2e/self-service-pages.spec.ts --project=chromium` reported `7 passed`.
- Migration compatibility for the four additive columns passed: fresh upgrade to revision `070`, seeded-row upgrade from `069` to `070`, downgrade back to `069`, and upgrade to current `head`.
- Supporting local gates passed: `python scripts/check-secret-access.py`, `python scripts/check-admin-role-gates.py`, `apps/control-plane/.venv/bin/pytest apps/control-plane/tests/me/`, `pnpm --dir apps/web test`, `pnpm --dir apps/web type-check`, `pnpm --dir apps/web lint`, and `pnpm --dir apps/web test:i18n-parity`.
- Live E2E command attempted: `apps/control-plane/.venv/bin/pytest tests/e2e/suites/self_service/ -v` collected 39 tests and failed during setup with `httpx.ConnectError: All connection attempts failed` because no platform API was running.

The full SC-001 through SC-020 sweep remains blocked in this workspace because there is no live platform API, WebSocket gateway, Kubernetes context, matrix CI run, or 24-hour synthetic log source attached to this session.
