# Quickstart — UPD-045 (feature 095)

This guide walks a developer through standing up, exercising, and debugging the public status surface, the in-shell banner, the simulation scenario editor, and the discovery workbench completion locally.

## Prerequisites

- Local kind cluster (per UPD-035 / `tests/e2e/` harness, when available — otherwise docker-compose dev stack).
- `make dev-up` running cleanly (data stores + control-plane runtime profiles).
- `pnpm install` completed at the repo root.
- A second pnpm install at `apps/web-status/` once the Track A scaffold lands.

## 1. Stand up the public status surface

```bash
# Apply the migration
cd apps/control-plane && alembic upgrade head

# Start the control plane (the status_page BC is mounted automatically)
make api-up

# Start the snapshot generator (runs in the same process via APScheduler;
# in production, a separate runtime profile is recommended — see plan §Phase 0 R10)
# Local-mode default: APScheduler runs in-process under the api profile.

# Start the status page UI in dev mode
cd apps/web-status && pnpm dev
# Opens on http://localhost:3001
```

### Smoke test

```bash
# Public status
curl -s http://localhost:8000/api/v1/public/status | jq '.overall_state'
# Should print: "operational"

# RSS feed
curl -s http://localhost:8000/api/v1/public/status/feed.rss | head -20

# Subscribe via email (the local-mode email sink is the dev MinIO bucket;
# see deploy/local/dev-email/)
curl -X POST http://localhost:8000/api/v1/public/subscribe/email \
     -H 'Content-Type: application/json' \
     -d '{"email":"dev@example.com"}'
# Should return 202 with the anti-enumeration response.
```

## 2. Trigger a synthetic incident (J21 setup)

```bash
# Use the existing E2E-mode incident trigger (gated by FEATURE_E2E_MODE)
curl -X POST http://localhost:8000/api/v1/_e2e/incidents/trigger \
     -H 'Content-Type: application/json' \
     -H 'Authorization: Bearer $E2E_ADMIN_TOKEN' \
     -d '{
       "severity":"warning",
       "title":"E2E synthetic — control-plane elevated errors",
       "components_affected":["control-plane-api"],
       "fingerprint":"e2e-synthetic-1"
     }'
```

Within ≤ 5 seconds, observe:
- `<PlatformStatusBanner>` appearing in the in-app shell at `http://localhost:3000/home`.
- The public status page at `http://localhost:3001/` flipping to "Degraded".
- A subscription dispatch row in `subscription_dispatches` for any active email subscriptions.
- A new entry in `/api/v1/public/status/feed.rss`.

Resolve:

```bash
curl -X POST http://localhost:8000/api/v1/_e2e/incidents/resolve \
     -H 'Content-Type: application/json' \
     -H 'Authorization: Bearer $E2E_ADMIN_TOKEN' \
     -d '{"fingerprint":"e2e-synthetic-1"}'
```

All surfaces should clear within ≤ 10 seconds.

## 3. Exercise the maintenance banner

```bash
# Schedule a maintenance window
curl -X POST http://localhost:8000/api/v1/admin/maintenance/windows \
     -H 'Content-Type: application/json' \
     -H 'Authorization: Bearer $ADMIN_TOKEN' \
     -d '{
       "title":"Local dev maintenance",
       "starts_at":"2026-04-28T15:00:00Z",
       "ends_at":"2026-04-28T15:30:00Z",
       "blocks_writes": true,
       "components_affected":["control-plane-api"]
     }'

# Enable it now
curl -X POST http://localhost:8000/api/v1/admin/maintenance/windows/{id}/enable \
     -H 'Authorization: Bearer $ADMIN_TOKEN'
```

Banner upgrades to "warning"; attempt a write action in the UI → `<MaintenanceBlockedAction>` modal appears instead of a 503 error page.

Disable:

```bash
curl -X POST http://localhost:8000/api/v1/admin/maintenance/windows/{id}/disable \
     -H 'Authorization: Bearer $ADMIN_TOKEN'
```

Banner disappears at next render in any open tab.

## 4. Test the static-site fallback (Rule 49 spot check)

```bash
# Stop the control-plane API
docker compose stop api

# Visit http://localhost:3001/ — page should still render with "last known state"
# banner showing the snapshot age. The page should NOT 502/503.
```

Restart the API:

```bash
docker compose start api
# Page hydrates within 60s of next snapshot regeneration.
```

## 5. Author a simulation scenario

1. Open `http://localhost:3000/evaluation-testing/simulations/scenarios`.
2. Click "New scenario".
3. Configure: agents (pick 1+ FQNs), workflow template, mock set (default = mock LLM provider per Rule 50), input distribution, twin fidelity, success criteria.
4. Save → row appears in scenario library.
5. Click "Launch" → confirm N=10 iterations → 10 runs queue.
6. Open any run → digital-twin panel renders with mock/real component lists and divergence summary.

For real-LLM preview during editing:
- Toggle "real LLM" on the preview pane.
- The `<RealLLMOptInDialog>` (UPD-044) appears requiring "USE_REAL_LLM".
- Confirm to enable for the next preview only.

## 6. Walk through the discovery workbench

1. Open `http://localhost:3000/discovery/{session_id}` — tabbed view (overview / hypotheses / experiments / evidence / network).
2. Hypotheses tab → filter by state, sort by confidence.
3. Open a hypothesis → see evidence pointers + related hypotheses + "Launch experiment" button.
4. Click → `/discovery/{session_id}/experiments/new` form.
5. Submit → experiment launched (uses existing backend endpoint).
6. Open evidence → `/discovery/{session_id}/evidence/{evidence_id}` — source links visible.
7. Network tab → existing XYFlow-based `<HypothesisNetworkGraph>` renders unchanged.

## 7. Run the E2E journeys

```bash
# Full visibility loop
pytest tests/e2e/journeys/test_j21_platform_state.py -v

# Evaluator scenario authoring + digital twin
pytest tests/e2e/journeys/test_j07_evaluator.py -v

# Discovery hypotheses + experiments + evidence
pytest tests/e2e/journeys/test_j09_scientific_discovery.py -v

# Component suites
pytest tests/e2e/suites/platform_state/ -v
pytest tests/e2e/suites/simulation_ui/ -v
pytest tests/e2e/suites/discovery_ui/ -v
```

## 8. Accessibility check

```bash
cd apps/web && pnpm test:axe
cd apps/web-status && pnpm test:axe
```

Any serious or critical violation fails the build (Rule 41).

## 9. i18n parity check

```bash
cd apps/web && pnpm i18n:check
```

Expected output: all six FR-620 locales (`en`, `es`, `de`, `fr`, `it`, `zh-CN`) have parity for the `platform-status` and `simulations.scenarios` and `discovery` namespaces. Any drift is reported.

> **Note**: `apps/web/messages/ja.json` is a stale artifact predating UPD-088. It is preserved at parity with `en.json` by this feature but its removal is owned by a follow-up i18n cleanup task (research R3).

## 10. Common dev-time gotchas

- **Banner does not appear**: check that the WebSocket gateway is running (`make ws-up`) and that the user is authenticated. The banner is gated on `/api/v1/me/platform-status` returning a non-operational state OR a `platform-status` WS message.
- **Email subscriptions never confirm**: in dev the email sink is the local MinIO bucket `dev-email/` — open the file in MinIO Console and click the link manually.
- **Public endpoint 401**: confirm `/api/v1/public/...` is in `EXEMPT_PATHS` / `EXEMPT_PREFIXES` of the auth middleware.
- **Status page shows "operational" during a simulated outage**: the snapshot generator may have an unhealthy poller. Check `status:snapshot:current` Redis key TTL and the APScheduler log.
- **Scenario save fails with `plaintext_secret`**: the validator detected what looks like a secret (regex match). Use a placeholder reference instead (e.g., `${SECRET:my-key}`) — the runtime controller will inject the real value at execution time per Principle XI.

---

**End of Quickstart.**
