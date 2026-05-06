# E2E Suite Maintenance — Operator Runbook

**Owner**: Platform / DevX
**Feature**: UPD-054 (107) — SaaS pass exit criteria
**Last updated**: 2026-05-05

This runbook covers the day-to-day maintenance of the SaaS-pass E2E
suite (J22–J37) added by UPD-054 on top of the UPD-038 framework.
It assumes you are familiar with `tests/e2e/README.md` (which covers
how to run the suite) and focuses on:

1. Fixture lifecycle and idempotent cleanup.
2. Parallel-runner architecture (`pytest-xdist` workers + serialised hot-spots).
3. Failure-artefact format and triage.
4. How to add a new journey.

---

## 1. Fixture lifecycle

The four UPD-054 fixtures all follow the per-test, idempotent-teardown
pattern documented in `specs/107-saas-e2e-journeys/research.md` § R8.
The cleanup obligation is owned by the fixture, not by the journey.
Every async-context-manager exit is re-runnable; 404 from the API is
treated as success.

| Fixture | Set up via | Teardown |
|---|---|---|
| `tenants.provision_enterprise` | `POST /api/v1/admin/tenants` | Two-phase delete via the public admin API. 404 ok. |
| `users.synthetic_user` | `POST /api/v1/admin/tenants/{slug}/invite` then accept-invite | Cascade with tenant delete. |
| `stripe.StripeTestModeClient` | Lazy customer create on first use | `purge_test_customers()` on session close, filtered by `metadata.musematic_test=true`. |
| `dns.build_dns_test_provider` | Mock by default; live with `RUN_J29=1` | Mock provider warns if records remain at teardown; live provider serializes per-zone deletes. |

If a journey leaks resources (orphan tenant after teardown, orphan
Stripe customer), the soak run picks it up via
`tests/e2e/scripts/verify_no_orphans.py`. Investigate by inspecting
the failed teardown's traceback in the artefact bundle's
`journey-state.log`.

---

## 2. Parallel-runner architecture

`make e2e-saas-suite` invokes `pytest-xdist -n 4` so journeys run
across four workers in parallel. The 30-min wall-clock target
(SC-002) assumes this configuration on a runner with ≥ 8 vCPU /
16 GiB RAM.

Three serialised hot-spots prevent races:

1. **Hetzner DNS zone (live mode)** — `dns.LiveHetznerDnsProvider`
   uses an `asyncio.Lock` per zone id to stay under the 1 req/s
   burst rate-limit.
2. **Stripe Test Clock per customer** — `stripe.advance_test_clock`
   serialises per `stripe_customer_id` because Stripe's clock-advance
   API is single-writer.
3. **Audit-chain verification** — `tools/verify_audit_chain.py` runs
   ONCE at session end (not per-test). The chain is a single global
   ledger and partial verification doesn't add value.

If you need to debug a flake, downgrade to single-worker
(`E2E_JOURNEY_WORKERS=1 make e2e-saas-suite`) — runs ~2 hours but
removes the parallel-execution variable. The `--collect-only` mode
(`pytest --collect-only`) lists every journey without running so you
can confirm the discovery layer.

---

## 3. Failure artefacts

When a journey fails, the suite emits a four-pillar bundle to
`tests/e2e/reports/{run-id}/`:

```text
reports/
├── saas-pass.xml              # JUnit summary
├── playwright/
│   ├── j22-screenshot.png
│   └── j22-network.har
├── audit-chain-dump.jsonl     # filtered to the run's correlation-id range
├── tenant-state-dump.json     # subscriptions, DNS records, K8s Secrets
└── journey-state.log          # one line per fixture lifecycle event
```

CI uploads the directory as `e2e-saas-{run-id}-reports` (30-day
retention). To navigate:

```bash
unzip e2e-saas-12345-reports.zip -d /tmp/saas-fail
# Start with the JUnit summary
cat /tmp/saas-fail/saas-pass.xml | xmlstarlet sel -t -m '//testcase/failure' -v '../@name' -n
# Then the journey-state log to see WHERE the journey broke
tail -50 /tmp/saas-fail/journey-state.log
# UI failures: open the HAR in the browser's "Network" tab, view screenshots
ls /tmp/saas-fail/playwright/
# Backend failures: grep the audit chain
jq -c 'select(.event_type | startswith("tenants.")) | {ts, event_type, tenant_id}' \
  /tmp/saas-fail/audit-chain-dump.jsonl | head -20
# Cleanup-state: confirm fixtures left no orphans
jq '.subscriptions, .dns_records, .secrets' /tmp/saas-fail/tenant-state-dump.json
```

### Common failure signatures

| Signature in `journey-state.log` | Likely cause | Fix |
|---|---|---|
| `TenantProvisioningTimeoutError: dns propagation` | DNS automation hung — usually cert-manager unhealthy | `kubectl -n cert-manager get pods`; redeploy |
| `LiveKeyDetectedError` | Production Stripe key leaked into test-mode Vault path | Re-seed test-mode key; rotate via `vault kv put` |
| `WebhookReplayWindowExceededError` | Test re-running > 7 days against same Stripe event | `trigger_webhook` to get a fresh event id |
| `ProductionZoneRefusedError` | Vault token in dev path scoped to production zone | Issue test-zone-only token; rotate |
| Worker hangs at 8min, then SIGKILL | `pytest-timeout` ceiling hit; stuck fixture | Inspect last fixture lifecycle line in `journey-state.log` |
| Many parallel J22 + J27 fail | Hetzner DNS API rate limit (live mode) | Drop to `-n 2` or run mock-only |

---

## 4. Adding a new journey

Follow the `journey-template.md` contract exactly. Quick-start:

```python
# tests/e2e/journeys/test_j99_my_new_journey.py
"""J99 My New Journey — UPD-NNN (FR-XXX).

Validates {what user value}. Cross-BC links: {bc1} ↔ {bc2}.
"""
from __future__ import annotations
import os
import pytest
from fixtures.tenants import provision_enterprise

pytestmark = [
    pytest.mark.journey,
    pytest.mark.j99,
    pytest.mark.timeout(480),
    pytest.mark.skipif(
        os.environ.get("RUN_J99", "0") != "1",
        reason="...",
    ),
]


@pytest.mark.asyncio
async def test_j99_happy_path(super_admin_client) -> None:
    async with provision_enterprise(super_admin_client=super_admin_client) as tenant:
        ...
```

The `test_helpers_contract.py` smoke test in
`tests/e2e/journeys/` enforces all three required markers. If you
forget one, the suite fails at collection time with a clear message
naming your file.

After adding the journey:

1. Add the file path to the `make e2e-saas-suite` target in the
   root `Makefile` (the glob `journeys/test_jNN_*.py` picks it up
   automatically as long as the prefix matches).
2. Add a status entry to the `journey-tests` job in
   `.github/workflows/ci.yml` if your journey requires a new
   service that the kind-cluster bootstrap doesn't already
   stand up.
3. Document the journey in `specs/107-saas-e2e-journeys/spec.md`
   if it adds an FR; otherwise note it in the spec for the
   feature whose user surface it tests.

---

## 5. Soak run procedure (SC-006)

```bash
# Full soak — 100 iterations of e2e-saas-suite + orphan check
make e2e-saas-soak

# Soak with fewer iterations for local debugging
E2E_SAAS_SOAK_ITERATIONS=10 make e2e-saas-soak
```

The soak workflow `.github/workflows/saas-pass-soak.yml` runs nightly
on `main`. A failure posts a comment to the soak tracking issue (file
under `Issues > Labels > infra: soak-failure`) so the platform team
catches orphan-resource regressions before they accumulate.

---

## 6. Promotion gate (SC-004) — verifying the gate trips

The gate is a step inside the existing `journey-tests (mock)` matrix
entry. To verify on a draft PR that a deliberate failure trips the
status check:

```bash
git checkout -b verify-saas-pass-gate
# Mutate one assertion in test_j22_tenant_provisioning.py to fail.
git commit -am "test: deliberately break J22 to verify gate"
git push -u origin verify-saas-pass-gate
gh pr create --draft --title "VERIFY: SaaS-pass gate trips on failure"
# Wait for CI; observe `journey-tests (mock)` turn red.
git revert HEAD
git push
# Observe the same status turn green on the revert.
```

This is documented as task T033 in
`specs/107-saas-e2e-journeys/tasks.md`. Run once after the suite
ships to validate the gate; afterward it doesn't need re-running.

---

## 7. Related runbooks

- `tests/e2e/README.md` (in the repo root, outside the docs site) — how
  to bring up the dev cluster and run journeys.
- [`docs/operations/hetzner-cluster-provisioning.md`](./hetzner-cluster-provisioning.md)
  — dev / prod cluster bring-up.
- [`docs/operations/wildcard-tls-renewal.md`](./wildcard-tls-renewal.md)
  — cert-manager renewal failure handling (J35 covers this).
- [`docs/operations/cloudflare-pages-status.md`](./cloudflare-pages-status.md)
  — status page push pipeline.
- `specs/107-saas-e2e-journeys/quickstart.md` — operator quickstart for
  the SaaS pass.
