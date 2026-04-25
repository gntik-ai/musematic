# Smoke Checklist: Multi-Channel Notifications

**Feature**: 077-multi-channel-notifications
**Date**: 2026-04-25
**Workspace**: `/home/andrea/WebstormProjects/musematic/.codex-worktrees/077-refresh`

## Execution Context

- Refreshed branch `077-multi-channel-notifications` was rebased on `origin/main` without conflicts.
- A local long-lived control-plane was not listening on `localhost:8081` during this pass, so direct curl replay of the Q-scripts was not possible from the developer workstation.
- The smoke evidence below uses the notifications unit/integration harness plus the PR E2E gate, which starts a local control-plane in the CI kind environment.

## Scenario Matrix

| Quickstart | Coverage | Outcome |
| --- | --- | --- |
| Q1 - Per-user email channel with quiet hours | `test_multi_channel_e2e.py`, `test_channel_router.py`, `test_quiet_hours.py` | Pass |
| Q2 - Workspace outbound webhook | `test_webhook_idempotency.py`, `test_webhook_deliverer_hmac.py`, `test_webhooks_service.py` | Pass |
| Q3 - At-least-once with retries | `test_webhook_retry_worker.py`, `test_webhook_deliverer_hmac.py`, `test_webhook_idempotency.py` | Pass |
| Q4 - Permanent 4xx skips retries | `test_webhook_retry_worker.py`, `test_webhook_deliverer_hmac.py` | Pass |
| Q5 - Dead-letter inspection and replay | `test_dead_letter.py`, `test_api_routers.py`, `test_multi_channel_e2e.py` | Pass |
| Q6 - Slack channel | `test_slack_teams_sms_adapters.py`, `test_deliverers.py` | Pass |
| Q7 - Microsoft Teams channel | `test_slack_teams_sms_adapters.py`, `test_deliverers.py` | Pass |
| Q8 - SMS for critical only | `test_slack_teams_sms_adapters.py`, `test_channel_router.py` | Pass |
| Q9 - Quiet-hours critical bypass | `test_quiet_hours.py`, `test_channel_router.py` | Pass |
| Q10 - DLP redact on outbound | `test_channel_router.py`, `test_webhook_deliverer_hmac.py` | Pass |
| Q11 - Residency block at registration | `test_webhooks_service.py`, `test_webhook_deliverer_hmac.py` | Pass |
| Q12 - Backwards compatibility | `test_channel_router.py`, `test_alert_service.py` | Pass |

## Verification Commands

```bash
ruff check apps/control-plane/src/platform/notifications apps/control-plane/tests/unit/notifications apps/control-plane/tests/integration/notifications
cd apps/control-plane && python -m mypy --strict src/platform/notifications
cd apps/control-plane && python -m pytest tests/unit/notifications tests/integration/notifications -q
```

## Deviations

- `ruff check .` from repository root still reports pre-existing lint debt in migrations/connectors and unrelated tests. The feature-scoped ruff command is clean.
- The task path `tests/control-plane/{unit,integration}/notifications` is historical; actual tests live under `apps/control-plane/tests/{unit,integration}/notifications`.
- Direct curl replay was deferred because no developer workstation control-plane was running; the PR E2E action remains the authoritative local-control-plane smoke gate.

## Final Outcome

Feature smoke checklist: **PASS**, with no code patch required.
