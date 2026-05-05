# Contract — CI Promotion Gate

## Purpose

Block merge to `main` if any single journey in the SaaS pass (J22–J37) fails on the dev cluster. Operationalises SC-004.

## Implementation surface

The gate is **a new matrix entry on the existing `journey-tests` job in `.github/workflows/ci.yml:419`**, NOT a separate workflow file. Per research R5: the existing job already brings up the kind cluster, installs Helm, sets up Stripe-cli, and uploads artefacts; duplicating that machinery in a new workflow file adds maintenance cost without isolation gain.

## Required-status check name

`journey-tests (saas-pass)` — the value chosen so the existing branch-protection rule that requires `journey-tests (mock)` etc. extends with one new required entry instead of being rewritten.

## Trigger conditions

The gate runs on PRs whose `paths-filter` matches **any of**:

- `apps/control-plane/src/platform/tenants/**`
- `apps/control-plane/src/platform/accounts/**`
- `apps/control-plane/src/platform/billing/**`
- `apps/control-plane/src/platform/marketplace/**`
- `apps/control-plane/src/platform/security/abuse_prevention/**`
- `apps/control-plane/src/platform/data_lifecycle/**`
- `apps/control-plane/src/platform/governance/**`
- `apps/web/app/(admin)/**`
- `apps/web/app/(auth)/**`
- `deploy/helm/**`
- `tests/e2e/**`

Outside those paths, the gate is skipped (`status=success` reported automatically) so that pure-docs PRs don't pay the 30-minute cost.

## Step layout

```yaml
- name: Run SaaS pass journeys (J22-J37)
  if: matrix.suite == 'saas-pass'
  working-directory: tests/e2e
  env:
    PLATFORM_VAULT_MODE: kubernetes
    STRIPE_TEST_MODE: 'true'
  run: |
    mkdir -p reports
    python -m pytest \
      journeys/test_j22_*.py \
      journeys/test_j23_*.py \
      journeys/test_j24_*.py \
      journeys/test_j25_*.py \
      journeys/test_j26_*.py \
      journeys/test_j27_*.py \
      journeys/test_j28_*.py \
      journeys/test_j29_*.py \
      journeys/test_j30_*.py \
      journeys/test_j31_*.py \
      journeys/test_j32_*.py \
      journeys/test_j33_*.py \
      journeys/test_j34_*.py \
      journeys/test_j35_*.py \
      journeys/test_j36_*.py \
      journeys/test_j37_*.py \
      -m journey \
      -n "${E2E_JOURNEY_WORKERS:-4}" \
      --dist=loadfile \
      --timeout=480 \
      --junitxml=reports/saas-pass.xml

- name: Verify audit chain integrity
  if: matrix.suite == 'saas-pass' && always()
  run: python tools/verify_audit_chain.py --include-cold-storage

- name: Upload failure artefacts
  if: matrix.suite == 'saas-pass' && failure()
  uses: actions/upload-artifact@v4
  with:
    name: e2e-saas-${{ github.run_id }}-reports
    path: tests/e2e/reports/
    retention-days: 30
```

## Artefact bundle (SC-005)

On any failure, the uploaded artefact contains:

```text
tests/e2e/reports/
├── saas-pass.xml                    # JUnit summary
├── playwright/
│   ├── j22-screenshot.png
│   ├── j22-network.har
│   └── ...                          # per-journey
├── audit-chain-dump.jsonl           # filtered to the run's correlation-id range
├── tenant-state-dump.json           # subscriptions, DNS records, K8s Secrets
└── journey-state.log                # one line per fixture lifecycle event
```

Operators consume the bundle by downloading it from the failed run's "Artifacts" panel; the runbook at `docs/operations/e2e-suite-maintenance.md` explains how to navigate it.

## Performance budget

Per SC-002, the gate MUST complete in ≤ 30 minutes wall-clock at p95. Budget breakdown on the GitHub Actions standard runner (4 vCPU, 16 GiB):

| Phase | Budget |
|---|---|
| Bootstrap kind + Helm install (existing) | 8 min |
| Run J22–J37 in parallel (4 workers) | 18 min |
| Audit-chain integrity check | 1 min |
| Artefact upload + cleanup | 3 min |
| **Total** | **30 min** |

When the suite trends past 25 min p50, the platform team adds a fifth worker AND begins the conversation about journey simplification.

## Soak-run extension (SC-006)

Outside the gate (which runs per-PR), a separate **`saas-pass-soak.yml` workflow** runs the full suite 100x in a tight loop on `main` once a day. This is for orphan-resource detection (zero orphan tenants / DNS / Stripe customers / K8s Secrets after 100 runs). The soak does NOT block PR merges.

## Cross-references

- Existing `journey-tests` job: `.github/workflows/ci.yml:419`.
- Audit chain verifier: `tools/verify_audit_chain.py` (UPD-014).
- Branch protection config lives in repo settings; the new required-status name is added there as part of Phase 1.
