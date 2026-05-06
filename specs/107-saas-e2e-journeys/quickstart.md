# UPD-054 — Quickstart (operator runbook)

End-to-end run of the SaaS pass (J22–J37) on a developer laptop or CI runner. Total wall-clock target: **≤ 30 minutes** at p95 (SC-002). The full SaaS pass passes when J01–J37 (37 journeys) green-light on the dev cluster.

## Prerequisites

- A working dev cluster (kind cluster or `musematic-dev` Hetzner cluster from UPD-053).
- Stripe CLI installed (`brew install stripe/stripe-cli/stripe` on macOS, GitHub release on Linux). The CI runner installs this in a setup step.
- Vault access from the runner with read on `secret/data/musematic/dev/billing/stripe/*` (test-mode key + webhook secret).
- For optional live-DNS coverage: `secret/data/musematic/dev/dns/hetzner/api-token` populated with a token scoped to the **test zone** (NOT production `musematic.ai`).
- Operator workstation: Python 3.12, `uv` (or `pip`), `pytest-xdist`, Helm ≥ 3.14, kubectl ≥ 1.29.

## 1. Bring up the dev cluster

```bash
make e2e-up
```

This is the existing UPD-038 entry point. It bootstraps a kind cluster, installs cert-manager CRDs, deploys the platform Helm chart against `values.dev.yaml`, and waits for healthchecks.

## 2. Seed the test-mode Stripe credentials

```bash
# One-time, on a fresh runner. Reads from your existing Stripe test-mode account.
vault kv put secret/musematic/dev/billing/stripe/api-key \
  key="$(stripe config --list | awk -F= '/test_mode_api_key/{print $2}')"
vault kv put secret/musematic/dev/billing/stripe/webhook-secret \
  active="$(stripe listen --print-secret)" \
  previous=""
```

The fixture refuses to construct if the key prefix is `sk_live_`; this is the SC-007 safety guarantee.

## 3. Run the full SaaS pass

```bash
make e2e-saas-suite
```

Equivalent to:

```bash
cd tests/e2e
PLATFORM_VAULT_MODE=mock E2E_JOURNEY_WORKERS=4 python -m pytest \
  journeys/test_j22_*.py journeys/test_j23_*.py ... journeys/test_j37_*.py \
  -m journey -n 4 --timeout=480
```

Wall-clock budget: **≤ 30 min p95** with 4 workers on a runner with ≥ 8 vCPU / 16 GiB RAM. Single-worker fall-back is roughly 2 hours (intended for local debugging).

## 4. Run a single journey

```bash
# Example: J28 billing lifecycle, all sub-scenarios
pytest tests/e2e/journeys/test_j28_billing_lifecycle.py -v

# Example: just the trial-to-paid scenario (J33)
pytest tests/e2e/journeys/test_j33_trial_to_paid_conversion.py::test_j33_trial_expires_charges_card -v
```

Single-journey invocations skip the `pytest-xdist` parallel layer; useful when iterating on a fixture.

## 5. Run the full SaaS pass *plus* J01–J21 regression

```bash
make e2e-saas-acceptance
```

This is the canonical "SaaS pass passes" check — runs all 37 journeys back-to-back. Targets ≤ 60 min wall-clock (parallel J22–J37 take 30 min, parallel J01–J21 take ≤ 30 min on the same hardware). Used by the SaaS pass owner to declare exit-criteria met.

## 6. Run with the live Hetzner DNS test zone (optional)

```bash
RUN_J29=1 make e2e-saas-suite
```

Opt-in path that exercises real Hetzner DNS API calls against the **test zone** (resolved from Vault). Adds about 2-3 minutes to the J22 / J27 / J29 / J35 journeys due to real DNS propagation polls; flake risk is non-zero. Run this on a cadence (nightly soak), NOT per-PR.

## 7. Soak (SC-006 — orphan-resource verification)

```bash
make e2e-saas-soak
# Equivalent to running e2e-saas-suite 100x in a tight loop.
# After completion, verify zero orphans:
python tests/e2e/scripts/verify_no_orphans.py
```

The soak target runs nightly on `main` via the `saas-pass-soak.yml` workflow (separate from the per-PR gate so it doesn't slow merges). Operators can run it locally before a release boundary.

## 8. Inspect a failed run

When the gate fails, the artefact bundle is uploaded as `e2e-saas-{run-id}-reports`. Download it and:

```bash
unzip e2e-saas-12345-reports.zip -d /tmp/saas-fail
# 1. Look at the JUnit summary first
cat /tmp/saas-fail/saas-pass.xml | grep -E 'failure|error'
# 2. Then the journey-state log to see which fixture stage broke
tail -50 /tmp/saas-fail/journey-state.log
# 3. Then Playwright screenshots + HAR for UI-driven journeys
ls /tmp/saas-fail/playwright/
# 4. Then the audit-chain slice and tenant-state for backend assertions
jq . /tmp/saas-fail/audit-chain-dump.jsonl | head -40
jq . /tmp/saas-fail/tenant-state-dump.json | jq '.subscriptions, .dns_records'
```

The runbook at `docs/operations/e2e-suite-maintenance.md` walks through common failure signatures and the fastest path to root cause.

## 9. Tear-down

```bash
make e2e-down                 # tears down the kind cluster
python tests/e2e/scripts/verify_no_orphans.py   # confirms zero orphans
```

For Stripe test-mode customer cleanup specifically (not strictly necessary; Stripe purges old test-mode data eventually):

```bash
python -c "from tests.e2e.fixtures.stripe import StripeTestModeClient; \
           import asyncio; \
           asyncio.run(StripeTestModeClient(secret_provider=...).purge_test_customers())"
```

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `LiveKeyDetectedError` at fixture init | A production Stripe key leaked into the test-mode Vault path | Re-seed § 2 with a `sk_test_*` key |
| Many failures with `TenantProvisioningTimeoutError` | DNS propagation didn't complete; usually means cert-manager is unhealthy | Check `kubectl -n cert-manager get pods`; redeploy if needed |
| `WebhookReplayWindowExceededError` in J32 | A test re-running after > 7 days against the same Stripe event | Re-trigger via `trigger_webhook` to get a fresh event id |
| Flake on J29 / J22 in live mode | Hetzner DNS API rate-limited (1 req/s burst per token) | Reduce `pytest-xdist` workers or use mock mode |
| `ProductionZoneRefusedError` | Vault token in the dev path is scoped to production zone | Issue a new token scoped to the test zone only; rotate via `vault kv put` |
| One worker hangs at 8 minutes | Stuck fixture; `pytest-timeout` SIGKILLs at ceiling | Inspect `journey-state.log` in the artefact bundle for the last fixture event |

## CI integration

Once this feature merges, the `journey-tests (saas-pass)` required-status check appears on every PR matching the SaaS path filter (per contract `promotion-gate.md`). A failure blocks merge to `main`. Reverting the gate is a branch-protection edit, NOT a code change.
